"""Re-judge a saved eval run with a different model.

The pipeline's support verdicts come from the judge it was configured with. The
eval reports those same verdicts, which makes the headline "claim support" a
self-judgement. This command replays only the support judgement over the
persisted evidence with a *different* model and writes a separate summary. The
original run is never modified.

    python -m evals.rejudge evals/runs/base --judge-model openai/gpt-oss-120b
    python -m evals.rejudge evals/runs/base --judge-model llama-3.3-70b-versatile \\
        --out evals/runs/base/rejudge-llama

Only verified evidence is sent to the judge. The quote-in-page gate is already
recorded in `evidence.json`; re-judging a quote that was never found would pay
for an opinion about a fabricated span.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from research_agent.config import Settings
from research_agent.evidence import EvidenceStore
from research_agent.llm import Usage, create_client
from research_agent.verify import ClaimVerifier, VerificationReport

from .harness import load_record
from .metrics import BAD_SUPPORT, RunRecord, summarize, to_markdown

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_records(run_dir: Path) -> list[RunRecord]:
    """Load records, preferring the per-question copy written by step 12a."""
    path = run_dir / "summary.json"
    if not path.exists():
        raise SystemExit(f"no summary.json in {run_dir}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: list[RunRecord] = []
    for row in payload.get("records", []):
        record = RunRecord.from_dict(row)
        per_item = load_record(run_dir, record.item_id)
        if per_item is not None:
            record = per_item
        records.append(record)
    if not records:
        raise SystemExit(f"no per-question records in {run_dir}")
    return records


def apply_judgements(
    record: RunRecord, store: EvidenceStore, report: VerificationReport
) -> tuple[RunRecord, dict[str, str]]:
    """Return a copy of the record with support counts from the new verdicts.

    Every verified item gets a verdict. An item the judge could not classify is
    `unjudged`, not silently dropped: a 429-shaped hole must not look like
    support. Cited claims are re-scored only when `cited_ids` was persisted;
    older runs predate that field, so their citation counts stay untouched.
    """
    rejudged = RunRecord.from_dict(record.to_dict())
    verdicts: dict[str, str] = {}
    support: dict[str, int] = {}

    for item in store.verified_items:
        judgement = report.judgements.get(item.id)
        if judgement is not None:
            verdict = judgement.verdict
        else:
            verdict = "unjudged"
        verdicts[item.id] = verdict
        support[verdict] = support.get(verdict, 0) + 1

    rejudged.support = support
    rejudged.evidence_citable = sum(
        1
        for item in store.verified_items
        if verdicts.get(item.id) not in BAD_SUPPORT
    )

    if rejudged.cited_ids:
        rejudged.unsupported_citations = sum(
            1
            for evidence_id in rejudged.cited_ids
            if (item := store.get(evidence_id)) is None
            or not item.verified
            or verdicts.get(evidence_id) in BAD_SUPPORT
        )
    return rejudged, verdicts


async def rejudge_records(
    run_dir: Path, records: list[RunRecord], verifier: ClaimVerifier
) -> tuple[list[RunRecord], dict, dict, Usage]:
    rejudged: list[RunRecord] = []
    details: dict[str, dict] = {}
    errors: dict[str, dict[str, str]] = {}
    usage = Usage()

    for record in records:
        evidence_path = run_dir / record.item_id / "evidence.json"
        if not evidence_path.exists():
            # A timed-out question can finish with no evidence at all. It has
            # nothing to re-judge, but dropping it would silently change the
            # denominator and make the run look better. Keep its original
            # record and surface the skip.
            errors[record.item_id] = {
                "evidence": f"missing evidence, record left unchanged: {evidence_path}"
            }
            details[record.item_id] = {"skipped": "missing evidence"}
            rejudged.append(record)
            continue
        store = EvidenceStore.load(evidence_path)
        report = await verifier.verify_items(store.verified_items)
        new_record, verdicts = apply_judgements(record, store, report)
        rejudged.append(new_record)
        usage += report.usage
        details[record.item_id] = {
            "cited_ids": record.cited_ids,
            "support": new_record.support,
            "verdicts": {
                evidence_id: {
                    "verdict": judgement.verdict,
                    "reason": judgement.reason,
                }
                for evidence_id, judgement in report.judgements.items()
            },
            "errors": report.errors,
        }
        if report.errors:
            errors[record.item_id] = report.errors

    return rejudged, details, errors, usage


def missing_cited_ids(run_dir: Path, records: list[RunRecord]) -> list[str]:
    """Old runs predate record.json; a new failed report has an empty list."""
    return [
        record.item_id
        for record in records
        if not record.cited_ids
        and not (run_dir / record.item_id / "record.json").exists()
    ]


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{float(value):.1%}"


def render_markdown(summary: dict, original: dict) -> str:
    lines = [to_markdown(summary, title="Independent re-judge"), ""]
    lines.append("## Compared with the original run")
    lines.append("")
    lines.append("| | original | re-judged |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| judge model | `{original.get('judge_model', '')}` | "
        f"`{summary.get('judge_model', '')}` |"
    )
    lines.append(
        f"| support rate (supported + partial) | "
        f"{_pct(original.get('support_rate'))} | "
        f"{_pct(summary.get('support_rate'))} |"
    )
    lines.append(
        f"| strict support rate (supported only) | "
        f"{_pct(original.get('strict_support_rate'))} | "
        f"{_pct(summary.get('strict_support_rate'))} |"
    )
    original_verdicts = original.get("verdicts") or {}
    new_verdicts = summary.get("verdicts") or {}
    lines.append(
        "| verdicts | "
        + ", ".join(f"{key} {value}" for key, value in original_verdicts.items())
        + " | "
        + ", ".join(f"{key} {value}" for key, value in new_verdicts.items())
        + " |"
    )
    lines.append("")
    lines.append(
        "Only the support judge was replayed. Reports, citations, and token "
        "counts are unchanged; the re-judge's own token usage is reported "
        "separately."
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-judge a saved eval run.")
    parser.add_argument("run", help="run directory containing summary.json")
    parser.add_argument("--judge-model", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="output directory (default: <run>/rejudge)",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="first N records")
    parser.add_argument(
        "--id", action="append", default=[], help="only these question ids"
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    original_payload = json.loads(
        (run_dir / "summary.json").read_text(encoding="utf-8")
    )
    original = original_payload.get("summary", {})
    records = load_records(run_dir)

    if args.id:
        wanted = set(args.id)
        records = [record for record in records if record.item_id in wanted]
        missing = wanted - {record.item_id for record in records}
        if missing:
            raise SystemExit(f"unknown question id(s): {', '.join(sorted(missing))}")
    if args.limit:
        records = records[: args.limit]

    if args.dry_run:
        for record in records:
            cited = len(record.cited_ids)
            print(f"{record.item_id:<32} cited={cited:<2} {record.question}")
        return 0

    settings = Settings.from_env()
    if args.judge_model:
        judge_settings = replace(
            settings, model=args.judge_model, judge_model=""
        )
    else:
        judge_settings = settings.judge_settings()

    if judge_settings.model == original.get("model"):
        print(
            "warning: the re-judge model equals the run's generation model; "
            "this is not an independent judge",
            file=sys.stderr,
        )
    missing_cited = missing_cited_ids(run_dir, records)
    if missing_cited:
        print(
            "warning: cited ids were not persisted for "
            + ", ".join(missing_cited[:5])
            + (" ..." if len(missing_cited) > 5 else "")
            + "; cited-claim precision was left unchanged for those records",
            file=sys.stderr,
        )

    client = create_client(judge_settings)
    verifier = ClaimVerifier(client, concurrency=args.concurrency)
    try:
        rejudged, details, errors, usage = await rejudge_records(
            run_dir, records, verifier
        )
    finally:
        await client.aclose()

    summary = summarize(rejudged)
    summary["provider"] = original.get("provider")
    summary["model"] = original.get("model")
    summary["judge_model"] = judge_settings.model
    summary["rejudged_from"] = str(run_dir)
    summary["rejudge_usage"] = {
        "prompt": usage.prompt_tokens,
        "completion": usage.completion_tokens,
        "total": usage.total_tokens,
    }
    summary["rejudge_errors"] = errors

    out_dir = Path(args.out) if args.out else run_dir / "rejudge"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "records": [record.to_dict() for record in rejudged],
                "dataset": original_payload.get("dataset", []),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "rejudge.json").write_text(
        json.dumps(
            {
                "generated_at": stamp,
                "source_run": str(run_dir),
                "judge_model": judge_settings.model,
                "original_summary": original,
                "summary": summary,
                "details": details,
                "errors": errors,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(
        render_markdown(summary, original), encoding="utf-8"
    )

    print("\n" + render_markdown(summary, original))
    print(f"\nartifacts: {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
