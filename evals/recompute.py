"""Recompute a saved run with the current metric definitions.

Metrics change: a field added in step 10 does not exist in a run recorded before
it. Two wrong answers are to re-run the suite (slow, and the provider is not
stationary) or to leave the old summary in place (then the README quotes numbers
produced by different code). The third answer is to re-derive: the artifacts
contain every per-question `RunRecord`, so the summary is a pure function of
them.

    python -m evals.recompute evals/runs/sample10 --model openai/gpt-oss-120b

Fields the old run never measured stay `None` (rendered "n/a"), because an
unknown value is not zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .metrics import RunRecord, summarize, to_markdown

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CARRIED = ("provider", "model", "judge_model", "concurrency", "max_steps", "timeout_s")


def recompute(payload: dict) -> dict:
    records = [RunRecord.from_dict(row) for row in payload.get("records", [])]
    summary = summarize(records)
    previous = payload.get("summary", {})
    for key in CARRIED:
        if key in previous:
            summary[key] = previous[key]
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute a run's summary.")
    parser.add_argument("run", help="run directory containing summary.json")
    parser.add_argument("--model", default=None)
    parser.add_argument("--judge-model", default=None)
    args = parser.parse_args(argv)

    folder = Path(args.run)
    path = folder / "summary.json"
    if not path.exists():
        raise SystemExit(f"no summary.json in {folder}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = recompute(payload)
    if args.model:
        summary["model"] = args.model
    if args.judge_model:
        summary["judge_model"] = args.judge_model

    payload["summary"] = summary
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown = to_markdown(summary, title=f"Eval run {folder.name}")
    (folder / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
