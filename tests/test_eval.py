from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from evals.dataset import DEFAULT_PATH, EvalItem, category_counts, load_dataset
from evals.harness import mentions, record_from_result, run_item, write_artifacts, write_item
from evals.metrics import (
    RunRecord,
    citation_coverage,
    citation_precision,
    compare,
    keyword_recall,
    support_rate,
    summarize,
    successful,
    to_markdown,
)
from research_agent.evidence import EvidenceStore
from research_agent.llm import Usage
from research_agent.pipeline import PipelineResult
from research_agent.tracing import Tracer

# --------------------------------------------------------------------------- #
# dataset
# --------------------------------------------------------------------------- #
def test_dataset_loads_and_is_big_enough():
    items = load_dataset(DEFAULT_PATH)
    assert len(items) >= 30
    assert len({item.id for item in items}) == len(items)
    assert all(item.must_include for item in items)
    counts = category_counts(items)
    assert len(counts) >= 6
    assert sum(counts.values()) == len(items)


def test_dataset_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "d.jsonl"
    row = (
        '{"id": "a-b", "question": "A long enough question here?", '
        '"category": "test", "must_include": ["term"]}'
    )
    path.write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate id"):
        load_dataset(path)


def test_dataset_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_dataset(path)


# --------------------------------------------------------------------------- #
# keyword proxy
# --------------------------------------------------------------------------- #
def test_mentions_matches_case_and_whitespace():
    assert mentions("Use Return_Exceptions   here", "return_exceptions")
    assert not mentions("nothing relevant", "return_exceptions")


def test_mentions_ignores_a_negated_occurrence():
    text = "gather does not cancel the other tasks"
    assert not mentions(text, "cancel the other tasks")
    assert mentions("gather will cancel the other tasks", "cancel the other tasks")


def test_mentions_finds_a_later_unnegated_occurrence():
    text = "it does not cancel them. later, it will cancel them on timeout"
    assert mentions(text, "cancel them")


# --------------------------------------------------------------------------- #
# record construction
# --------------------------------------------------------------------------- #
def make_item(**overrides) -> EvalItem:
    payload = {
        "id": "t-1",
        "question": "A question long enough to validate?",
        "category": "asyncio",
        "must_include": ["return_exceptions"],
        "must_not_include": ["cancel siblings"],
    }
    payload.update(overrides)
    return EvalItem(**payload)


def test_record_from_result_counts_support_and_unsupported_citations():
    store = EvidenceStore()
    url = "https://docs.python.org/3/library/asyncio-task.html"
    store.register_source(
        url,
        "The first exception is propagated to the caller. "
        "gather does not cancel siblings.",
    )
    good = store.add(
        "propagates the first exception",
        "The first exception is propagated to the caller.",
        url,
    )
    bad = store.add("cancels siblings", "gather does not cancel siblings.", url)
    assert good is not None and bad is not None
    good.support = "supported"
    bad.support = "unsupported"

    result = PipelineResult(
        question="q",
        store=store,
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )
    result.report = SimpleNamespace(
        cited_ids=[good.id, bad.id],
        unused_ids=[bad.id],
        word_count=120,
        ok=True,
        repaired=False,
        errors=[],
        body="Set return_exceptions=True. gather does not cancel siblings.",
        markdown="",
    )

    record = record_from_result(make_item(), result, 1.5)

    assert record.ok is True
    assert record.support == {"supported": 1, "unsupported": 1}
    assert record.citations == 2
    assert record.unsupported_citations == 1
    assert record.keyword_hits == ["return_exceptions"]
    assert record.keyword_misses == []
    assert record.misconception_hits == []  # negated in the prose
    assert record.tokens_total == 150


def test_record_from_result_survives_a_failed_stage():
    result = PipelineResult(question="q", error="plan: boom")
    result.stage_errors["plan"] = "RuntimeError: boom"
    record = record_from_result(make_item(), result, 0.4)
    assert record.ok is False
    assert record.error == "plan: boom"
    assert record.stage_errors == {"plan": "RuntimeError: boom"}
    assert record.citations == 0


class SlowPipeline:
    def __init__(self) -> None:
        self.last_trace = Tracer("slow")

    async def run(self, question, *, on_stage=None):
        await asyncio.sleep(10)
        raise AssertionError("run_item should have timed out first")


def test_run_item_turns_a_hang_into_a_row():
    record, result = asyncio.run(
        run_item(SlowPipeline(), make_item(), timeout=0.01)
    )
    assert record.ok is False
    assert record.error is not None and "timeout" in record.error
    assert result.stage_errors["pipeline"].startswith("timeout")
    # The partial trace survives cancellation and can be inspected.
    assert result.trace is not None


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #
def test_write_item_writes_the_trace(tmp_path):
    result = PipelineResult(question="q", trace=Tracer("q"))
    item = make_item()

    write_item(tmp_path, item, result)

    folder = tmp_path / item.id
    assert (folder / "trace.json").exists()
    assert (folder / "trace.html").exists()


def test_write_item_keeps_the_report_even_if_the_run_dies_later(tmp_path):
    result = PipelineResult(question="q")
    result.report = SimpleNamespace(markdown="# Report\n\nbody [1]")
    write_item(tmp_path, make_item(), result)
    report = tmp_path / "t-1" / "report.md"
    assert report.read_text(encoding="utf-8").startswith("# Report")


def test_write_artifacts_serialises_summary_records_and_dataset(tmp_path):
    item = make_item()
    record = make_record(item_id=item.id)
    summary = summarize([record])
    write_artifacts(tmp_path, [item], [record], {}, summary)
    payload = __import__("json").loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert payload["records"][0]["item_id"] == item.id
    assert payload["dataset"][0]["question"] == item.question
    assert payload["summary"]["n"] == 1


# --------------------------------------------------------------------------- #
# metric arithmetic
# --------------------------------------------------------------------------- #
def make_record(**overrides) -> RunRecord:
    payload = {
        "item_id": "t-1",
        "category": "asyncio",
        "question": "q",
        "ok": True,
        "report_ok": True,
        "support": {"supported": 3, "partial": 1, "unsupported": 1, "contradicted": 0},
        "evidence_total": 6,
        "evidence_verified": 5,
        "evidence_citable": 4,
        "evidence_cited": 2,
        "citations": 4,
        "unsupported_citations": 0,
        "keyword_hits": ["a"],
        "keyword_misses": ["b"],
        "tokens_total": 1000,
        "duration_s": 10.0,
    }
    payload.update(overrides)
    return RunRecord(**payload)


def test_support_rate_counts_partial_as_supported():
    record = make_record()
    assert support_rate(record) == pytest.approx(0.8)


def test_support_rate_is_zero_when_nothing_was_judged():
    assert support_rate(make_record(support={})) == 0.0


def test_citation_precision_penalises_bad_citations():
    assert citation_precision(make_record()) == 1.0
    assert citation_precision(make_record(unsupported_citations=1)) == pytest.approx(0.75)
    assert citation_precision(make_record(citations=0, unsupported_citations=0)) == 0.0


def test_citation_coverage_is_cited_over_citable():
    assert citation_coverage(make_record()) == pytest.approx(0.5)


def test_cost_total_is_na_if_any_record_was_not_priced():
    priced = make_record(cost_usd=0.0)
    unknown = make_record(item_id="t-2", cost_usd=None)

    summary = summarize([priced])
    assert summary["total_cost_usd"] == 0.0
    assert summary["mean_cost_usd"] == 0.0

    summary = summarize([priced, unknown])
    assert summary["total_cost_usd"] is None
    assert summary["mean_cost_usd"] is None


def test_an_unpriced_model_makes_the_total_unknown():
    summary = summarize(
        [make_record(cost_usd=0.0, unpriced_models=["mystery-model"])]
    )
    assert summary["total_cost_usd"] is None
    assert summary["unpriced_models"] == ["mystery-model"]
    assert citation_coverage(make_record(evidence_citable=0)) == 0.0


def test_keyword_recall():
    assert keyword_recall(make_record()) == pytest.approx(0.5)
    assert keyword_recall(make_record(keyword_hits=[], keyword_misses=[])) == 0.0


def test_success_requires_ok_report_and_a_citation():
    assert successful(make_record())
    assert not successful(make_record(report_ok=False))
    assert not successful(make_record(citations=0))


def test_run_record_round_trip_ignores_unknown_keys():
    record = make_record()
    payload = record.to_dict()
    payload["future_field"] = "ignored"
    assert RunRecord.from_dict(payload) == record


# --------------------------------------------------------------------------- #
# aggregation and comparison
# --------------------------------------------------------------------------- #
def test_summary_is_a_macro_average():
    short = make_record(tokens_total=100, duration_s=1.0)
    long = make_record(tokens_total=900, duration_s=3.0, support={}, citations=0)
    summary = summarize([short, long])
    assert summary["n"] == 2
    assert summary["success_rate"] == pytest.approx(0.5)
    assert summary["mean_tokens"] == pytest.approx(500)
    assert summary["mean_seconds"] == pytest.approx(2.0)
    assert summary["total_tokens"] == 1000


def test_summary_percentiles():
    records = [
        make_record(tokens_total=n) for n in (100, 200, 300, 400)
    ]
    summary = summarize(records)
    assert summary["p50_tokens"] == pytest.approx(250)
    assert summary["p90_tokens"] == pytest.approx(370)


def test_summary_groups_categories():
    records = [
        make_record(category="asyncio"),
        make_record(category="http", tokens_total=2000),
    ]
    summary = summarize(records)
    assert summary["by_category"]["asyncio"]["n"] == 1
    assert summary["by_category"]["http"]["mean_tokens"] == pytest.approx(2000)


def test_summary_precision_is_micro_averaged_over_citations():
    clean = make_record(citations=10, unsupported_citations=0)
    broken = make_record(citations=10, unsupported_citations=1)
    summary = summarize([clean, broken])
    assert summary["citation_precision"] == pytest.approx(0.95)


def test_summary_precision_is_none_when_the_run_cited_nothing():
    summary = summarize([make_record(citations=0, unsupported_citations=0)])
    assert summary["citation_precision"] is None
    assert "n/a" in to_markdown(summary)


def test_repair_rate_is_unknown_not_zero_when_the_run_predates_the_field():
    summary = summarize([make_record()])
    assert summary["repair_rate"] is None
    assert "n/a" in to_markdown(summary)


def test_repair_rate_counts_only_runs_that_recorded_it():
    summary = summarize(
        [
            make_record(writer_repaired=True),
            make_record(writer_repaired=False),
            make_record(writer_repaired=None),
        ]
    )
    assert summary["repair_rate"] == pytest.approx(0.5)


def test_compare_flags_a_broken_invariant_first():
    baseline = summarize([make_record()])
    candidate = summarize([make_record(unsupported_citations=2, citations=4)])
    result = compare(baseline, candidate)
    assert any("unsupported citations" in line for line in result["regressions"])
    assert any("precision" in line for line in result["regressions"])


def test_compare_reports_improvements_without_flags():
    baseline = summarize([make_record(support={"supported": 1, "partial": 0, "unsupported": 1, "contradicted": 0})])
    candidate = summarize([make_record()])
    result = compare(baseline, candidate)
    assert result["regressions"] == []
    deltas = {row["metric"]: row["delta"] for row in result["rows"]}
    assert deltas["support_rate"] > 0
