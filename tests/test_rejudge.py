from __future__ import annotations

import asyncio
import json

from evals.harness import write_record
from evals.metrics import RunRecord
from evals.rejudge import (
    apply_judgements,
    load_records,
    main as rejudge_main,
    missing_cited_ids,
    render_markdown,
    rejudge_records,
)
from research_agent.evidence import EvidenceStore
from research_agent.verify import SupportJudgement, VerificationReport


def make_store():
    store = EvidenceStore()
    url = "https://docs.python.org/3/library/asyncio-task.html"
    store.register_source(
        url,
        "Alpha supports the claim. Beta contradicts the claim.",
    )
    alpha = store.add("alpha claim", "Alpha supports the claim.", url)
    beta = store.add("beta claim", "Beta contradicts the claim.", url)
    assert alpha is not None and beta is not None
    return store, alpha, beta


def make_record(**overrides) -> RunRecord:
    payload = {
        "item_id": "q-1",
        "category": "test",
        "question": "A question long enough?",
        "citations": 2,
        "evidence_total": 2,
        "evidence_verified": 2,
        "evidence_citable": 2,
        "support": {"supported": 2},
    }
    payload.update(overrides)
    return RunRecord(**payload)


def test_apply_judgements_replaces_support_and_rescores_cited_claims():
    store, alpha, beta = make_store()
    record = make_record(cited_ids=[alpha.id, beta.id])
    report = VerificationReport(
        judgements={
            alpha.id: SupportJudgement(verdict="supported"),
            beta.id: SupportJudgement(verdict="contradicted"),
        }
    )

    rejudged, verdicts = apply_judgements(record, store, report)

    assert verdicts == {alpha.id: "supported", beta.id: "contradicted"}
    assert rejudged.support == {"supported": 1, "contradicted": 1}
    assert rejudged.unsupported_citations == 1
    assert rejudged.evidence_citable == 1
    # The original record is not mutated.
    assert record.support == {"supported": 2}


def test_apply_judgements_fails_closed_on_judge_errors():
    store, alpha, beta = make_store()
    record = make_record(cited_ids=[alpha.id, beta.id])
    report = VerificationReport(errors={alpha.id: "RuntimeError: 429"})

    rejudged, verdicts = apply_judgements(record, store, report)

    assert verdicts[alpha.id] == "unjudged"
    assert verdicts[beta.id] == "unjudged"
    assert rejudged.support == {"unjudged": 2}
    assert rejudged.unsupported_citations == 2
    assert rejudged.evidence_citable == 0


def test_apply_judgements_counts_a_missing_cited_id_as_unsupported():
    store, alpha, beta = make_store()
    record = make_record(cited_ids=["ev_missing", alpha.id])
    report = VerificationReport(
        judgements={
            alpha.id: SupportJudgement(verdict="supported"),
            beta.id: SupportJudgement(verdict="supported"),
        }
    )

    rejudged, _ = apply_judgements(record, store, report)

    assert rejudged.unsupported_citations == 1


def test_load_records_prefers_the_per_question_copy(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    from_summary = make_record(cited_ids=[])
    (run / "summary.json").write_text(
        json.dumps({"records": [from_summary.to_dict()]}), encoding="utf-8"
    )
    detailed = make_record(cited_ids=["ev_1"])
    write_record(run / detailed.item_id, detailed)

    loaded = load_records(run)

    assert len(loaded) == 1
    assert loaded[0].cited_ids == ["ev_1"]


class FakeVerifier:
    async def verify_items(self, items):
        return VerificationReport(
            judgements={
                item.id: SupportJudgement(verdict="supported") for item in items
            }
        )


def test_rejudge_records_replays_only_the_saved_evidence(tmp_path):
    run = tmp_path / "run"
    item_dir = run / "q-1"
    item_dir.mkdir(parents=True)
    store, alpha, beta = make_store()
    store.save(item_dir / "evidence.json")
    record = make_record(cited_ids=[alpha.id, beta.id])

    rejudged, details, errors, usage = asyncio.run(
        rejudge_records(run, [record], FakeVerifier())
    )

    assert errors == {}
    assert usage.total_tokens == 0
    assert rejudged[0].support == {"supported": 2}
    assert rejudged[0].unsupported_citations == 0
    assert details["q-1"]["verdicts"][alpha.id]["verdict"] == "supported"


def test_rejudge_markdown_reports_an_unjudged_original_as_na():
    summary = {
        "n": 1,
        "total_tokens": 1,
        "total_seconds": 1.0,
        "judge_model": "judge",
        "support_rate": 0.5,
        "strict_support_rate": 0.5,
        "verdicts": {"supported": 1},
    }
    original = {
        "judge_model": "",
        "support_rate": None,
        "strict_support_rate": None,
        "verdicts": {},
    }

    text = render_markdown(summary, original)

    assert "n/a" in text
    assert "| support rate (supported + partial) | n/a | 50.0% |" in text


def test_rejudge_dry_run_does_not_need_a_client(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    record = make_record()
    (run / "summary.json").write_text(
        json.dumps({"records": [record.to_dict()]}), encoding="utf-8"
    )

    assert rejudge_main([str(run), "--dry-run"]) == 0
    assert "q-1" in capsys.readouterr().out


def test_missing_cited_ids_distinguishes_old_runs_from_empty_reports(tmp_path):
    old = make_record(item_id="old", cited_ids=[])
    new_failed = make_record(item_id="new-failed", cited_ids=[])
    write_record(tmp_path / new_failed.item_id, new_failed)

    assert missing_cited_ids(tmp_path, [old, new_failed]) == ["old"]


def test_load_records_falls_back_to_the_summary_for_old_runs(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    record = make_record(cited_ids=[])
    (run / "summary.json").write_text(
        json.dumps({"records": [record.to_dict()]}), encoding="utf-8"
    )

    loaded = load_records(run)

    assert loaded == [record]
