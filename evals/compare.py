"""Compare two eval runs and refuse to hide a regression.

    .\\venv\\Scripts\\python.exe -m evals.compare evals/runs/baseline/summary.json evals/runs/candidate/summary.json

Exit code 1 when a regression is found, so this can be a CI gate. The point of
an eval is not the dashboard: it is that a prompt change has to argue with a
number before it ships.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .metrics import compare

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_summary(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("summary", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two eval summaries.")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args(argv)

    baseline = load_summary(args.baseline)
    candidate = load_summary(args.candidate)
    result = compare(baseline, candidate)

    print(f"{'metric':<20} {'baseline':>10} {'candidate':>10} {'delta':>10}")
    for row in result["rows"]:
        delta = row["delta"]
        marker = "" if abs(delta) < 1e-9 else ("  +" if delta > 0 else "  -")
        print(
            f"{row['metric']:<20} {row['baseline']:>10.4f} "
            f"{row['candidate']:>10.4f} {delta:>10.4f}{marker}"
        )

    if result["regressions"]:
        print("\nREGRESSIONS")
        for line in result["regressions"]:
            print(f"  - {line}")
        return 1

    print("\nno regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
