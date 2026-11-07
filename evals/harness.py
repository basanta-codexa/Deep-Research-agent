"""Run the pipeline over the dataset and turn results into records.

The harness owns no metric logic (that is `metrics.py`) and no pipeline logic
(that is `research_agent/pipeline.py`). It only measures: timings, counts, and
which keywords the finished report happens to contain.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from research_agent.pipeline import PipelineResult, ResearchPipeline

from .dataset import EvalItem
from .metrics import BAD_SUPPORT, RunRecord

NEGATIONS = (
    "not ",
    "n't ",
    "never ",
    "no ",
    "without ",
    "cannot ",
    "can't ",
    "isn't ",
    "doesn't ",
    "don't ",
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def mentions(text: str, phrase: str, *, window: int = 24) -> bool:
    """Substring match that ignores negated mentions: 'not cancelled' != 'cancelled'.

    Heuristic, deliberately small: only the clause immediately before the match
    is inspected. A wider window makes "does not cancel X ... later it cancels X"
    look negated twice. This is a proxy for coverage, not a truth check.
    """
    haystack = _normalize(text)
    needle = _normalize(phrase)
    if not needle:
        return False
    start = 0
    while (index := haystack.find(needle, start)) != -1:
        prefix = haystack[max(0, index - window) : index]
        for separator in (". ", "; ", "? ", "! ", ": "):
            cut = prefix.rfind(separator)
            if cut != -1:
                prefix = prefix[cut + len(separator) :]
        if not any(negation in prefix for negation in NEGATIONS):
            return True
        start = index + len(needle)
    return False


def record_from_result(
    item: EvalItem, result: PipelineResult, duration_s: float
) -> RunRecord:
    store = result.store
    verified = store.verified_items
    citable = store.citable()
    report = result.report
    trace = result.trace.summary() if result.trace is not None else {}
    trace_tokens = trace.get("tokens") or {}
    # The trace sees every call, including the ones a cancelled run never got to
    # add to `result.usage`; prefer it when it exists.
    prompt_tokens = trace_tokens.get("prompt", result.usage.prompt_tokens)
    completion_tokens = trace_tokens.get("completion", result.usage.completion_tokens)
    total_tokens = trace_tokens.get("total", result.usage.total_tokens)
    cost = trace.get("cost_usd")

    support: dict[str, int] = {}
    for evidence in verified:
        support[evidence.support] = support.get(evidence.support, 0) + 1

    cited_ids = list(report.cited_ids) if report else []
    unsupported = 0
    for evidence_id in cited_ids:
        evidence = store.get(evidence_id)
        if (
            evidence is None
            or not evidence.verified
            or evidence.support in BAD_SUPPORT
        ):
            unsupported += 1

    body = report.body if report else ""
    hits = [term for term in item.must_include if mentions(body, term)]
    misses = [term for term in item.must_include if term not in hits]
    misconceptions = [
        term for term in item.must_not_include if mentions(body, term)
    ]

    return RunRecord(
        item_id=item.id,
        category=item.category,
        question=item.question,
        ok=result.ok,
        error=result.error,
        duration_s=round(duration_s, 2),
        stage_errors=dict(result.stage_errors),
        evidence_total=len(store),
        evidence_verified=len(verified),
        evidence_citable=len(citable),
        evidence_cited=len([i for i in cited_ids if store.get(i) is not None]),
        evidence_unused=len(report.unused_ids) if report else 0,
        support=support,
        contradictions=(
            len(result.verification.contradictions)
            if result.verification is not None
            else 0
        ),
        citations=len(cited_ids),
        cited_ids=cited_ids,
        unsupported_citations=unsupported,
        words=report.word_count if report else 0,
        report_ok=bool(report and report.ok),
        writer_repaired=bool(report and report.repaired),
        writer_errors=[f"{p.code}: {p.detail}" for p in (report.errors if report else [])],
        keyword_hits=hits,
        keyword_misses=misses,
        misconception_hits=misconceptions,
        tokens_prompt=prompt_tokens,
        tokens_completion=completion_tokens,
        tokens_total=total_tokens,
        cost_usd=float(cost) if cost is not None else None,
        unpriced_models=list(trace.get("unpriced_models", [])),
        timings={key: round(value, 2) for key, value in result.timings.items()},
    )


async def run_item(
    pipeline: ResearchPipeline,
    item: EvalItem,
    *,
    timeout: float | None = None,
    on_stage=None,
) -> tuple[RunRecord, PipelineResult]:
    started = time.perf_counter()
    try:
        if timeout:
            result = await asyncio.wait_for(
                pipeline.run(item.question, on_stage=on_stage), timeout=timeout
            )
        else:
            result = await pipeline.run(item.question, on_stage=on_stage)
    except asyncio.TimeoutError:
        # A hung provider call must become a row in the table, not a hung run.
        # Keep the partial trace: it is the only record of where the time went.
        result = PipelineResult(
            question=item.question,
            error=f"timeout after {timeout:.0f}s",
            stage_errors={"pipeline": f"timeout after {timeout:.0f}s"},
            trace=pipeline.last_trace,
        )
    return record_from_result(item, result, time.perf_counter() - started), result


def _write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically so a crash cannot leave a half-written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)


def write_record(folder: Path, record: RunRecord) -> Path:
    path = Path(folder) / "record.json"
    _write_json(path, record.to_dict())
    return path


def load_record(directory: Path, item_id: str) -> RunRecord | None:
    """Load one completed record, or None when the question never finished."""
    path = Path(directory) / item_id / "record.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = RunRecord.from_dict(payload)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"corrupt eval record {path}: {exc}") from exc
    if record.item_id != item_id:
        raise ValueError(
            f"eval record {path} belongs to {record.item_id!r}, not {item_id!r}"
        )
    return record


def write_item(
    directory: Path,
    item: EvalItem,
    result: PipelineResult,
    record: RunRecord | None = None,
) -> None:
    """Persist one question immediately, so an interrupted run keeps its work."""
    folder = directory / item.id
    folder.mkdir(parents=True, exist_ok=True)
    if result.report is not None:
        (folder / "report.md").write_text(result.report.markdown, encoding="utf-8")
    if len(result.store):
        result.store.save(folder / "evidence.json")
    if result.plan is not None:
        (folder / "plan.json").write_text(
            result.plan.model_dump_json(indent=2), encoding="utf-8"
        )
    if result.trace is not None:
        result.trace.save(folder / "trace.json")
        result.trace.save_html(folder / "trace.html")
    if record is not None:
        write_record(folder, record)


def write_artifacts(
    directory: Path,
    items: list[EvalItem],
    records: list[RunRecord],
    results: dict[str, PipelineResult],
    summary: dict,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "records": [record.to_dict() for record in records],
                "dataset": [item.model_dump() for item in items],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    records_by_id = {record.item_id: record for record in records}
    for item in items:
        result = results.get(item.id)
        if result is not None:
            write_item(directory, item, result, records_by_id.get(item.id))
