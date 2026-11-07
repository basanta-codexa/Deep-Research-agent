"""Paired bootstrap for two eval runs over the same questions.

Usage:
    python -m evals.ablation_stats evals/runs/control/summary.json \
        evals/runs/single-agent/summary.json

The per-run summary already has cluster-bootstrap intervals. This script adds
the quantity those intervals cannot give you: a paired delta that resamples the
same question ids in both runs, so shared question difficulty cancels out.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from statistics import mean

from evals.metrics import (
    RunRecord,
    citation_coverage,
    judged,
    keyword_recall,
    strict_support_rate,
    successful,
    support_rate,
)


def load(path: str) -> dict[str, RunRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["item_id"]: RunRecord.from_dict(r) for r in payload["records"]}


def value(record: RunRecord, metric: str) -> float | None:
    if metric == "success":
        return 1.0 if successful(record) else 0.0
    if metric == "strict":
        return strict_support_rate(record) if judged(record) else None
    if metric == "lenient":
        return support_rate(record) if judged(record) else None
    if metric == "coverage":
        return citation_coverage(record) if record.evidence_citable else None
    if metric == "keyword":
        return (
            keyword_recall(record)
            if record.keyword_hits or record.keyword_misses
            else None
        )
    if metric == "seconds":
        return float(record.duration_s)
    if metric == "tokens":
        return float(record.tokens_total)
    if metric == "cost":
        return float(record.cost_usd) if record.cost_usd is not None else None
    raise ValueError(metric)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def paired(
    control: dict[str, RunRecord],
    candidate: dict[str, RunRecord],
    metric: str,
    *,
    iterations: int = 2000,
    seed: int = 7,
) -> tuple[float, float, float, int] | None:
    ids = [item_id for item_id in control if item_id in candidate]
    diffs = []
    a_values = []
    b_values = []
    for item_id in ids:
        a = value(control[item_id], metric)
        b = value(candidate[item_id], metric)
        if a is None or b is None:
            continue
        a_values.append(a)
        b_values.append(b)
        diffs.append(b - a)
    if not diffs:
        return None
    rng = random.Random(seed)
    boot = []
    for _ in range(iterations):
        sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        boot.append(mean(sample))
    return (
        mean(diffs),
        percentile(boot, 0.025),
        percentile(boot, 0.975),
        len(diffs),
    )


METRICS = [
    ("success", "success", "pp"),
    ("strict", "strict support", "pp"),
    ("lenient", "lenient support", "pp"),
    ("coverage", "citation coverage", "pp"),
    ("keyword", "keyword recall", "pp"),
    ("seconds", "seconds / question", "pct"),
    ("tokens", "tokens / question", "pct"),
    ("cost", "cost / question", "pct"),
]


def main(control_path: str, candidate_path: str) -> int:
    control = load(control_path)
    candidate = load(candidate_path)
    print(f"control: {control_path} ({len(control)} questions)")
    print(f"candidate: {candidate_path} ({len(candidate)} questions)")
    print()
    print("| metric | control | candidate | paired delta | 95% CI | n |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for metric, label, kind in METRICS:
        result = paired(control, candidate, metric)
        if result is None:
            print(f"| {label} | — | — | — | — | 0 |")
            continue
        delta, lo, hi, n = result
        a_values = [value(control[i], metric) for i in control if i in candidate]
        b_values = [value(candidate[i], metric) for i in candidate if i in control]
        a_values = [v for v in a_values if v is not None]
        b_values = [v for v in b_values if v is not None]
        a_mean = mean(a_values)
        b_mean = mean(b_values)
        if kind == "pp":
            print(
                f"| {label} | {a_mean:.1%} | {b_mean:.1%} | "
                f"{delta * 100:+.1f} pp | {lo * 100:+.1f} to {hi * 100:+.1f} pp | {n} |"
            )
        else:
            digits = 4 if metric == "cost" else 1
            print(
                f"| {label} | {a_mean:.{digits}f} | {b_mean:.{digits}f} | "
                f"{delta / a_mean * 100:+.1f}% | "
                f"{lo / a_mean * 100:+.1f} to {hi / a_mean * 100:+.1f}% | {n} |"
            )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: ablation_stats.py control-summary candidate-summary")
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
