"""Metrics. Pure functions, no model, no network.

The rule that keeps this honest: **a metric that cannot disagree with you is not
a metric.** `citation_precision` is 1.0 by construction (the writer can only cite
ids that passed the gates), so it is reported as an *invariant*, not as a score.
It catches regressions, it does not measure quality. The numbers that can move
are support rate, coverage, keyword recall, cost and latency.

Averages are macro (per question, then averaged) so one 4,000-token outlier
cannot hide ten short failures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

JUDGED_VERDICTS = ("supported", "partial", "unsupported", "contradicted")
BAD_SUPPORT = ("unsupported", "contradicted", "unjudged")


@dataclass(slots=True)
class RunRecord:
    item_id: str
    category: str
    question: str
    ok: bool = False
    error: str | None = None
    duration_s: float = 0.0
    stage_errors: dict[str, str] = field(default_factory=dict)

    evidence_total: int = 0
    evidence_verified: int = 0
    evidence_citable: int = 0
    evidence_cited: int = 0
    evidence_unused: int = 0
    support: dict[str, int] = field(default_factory=dict)
    contradictions: int = 0

    citations: int = 0
    unsupported_citations: int = 0
    words: int = 0
    report_ok: bool = False
    writer_repaired: bool | None = None
    writer_errors: list[str] = field(default_factory=list)

    keyword_hits: list[str] = field(default_factory=list)
    keyword_misses: list[str] = field(default_factory=list)
    misconception_hits: list[str] = field(default_factory=list)

    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "RunRecord":
        known = {f for f in cls.__slots__}
        return cls(**{key: value for key, value in payload.items() if key in known})


# --------------------------------------------------------------------------- #
# per-run metrics
# --------------------------------------------------------------------------- #
def judged(record: RunRecord) -> int:
    return sum(record.support.get(verdict, 0) for verdict in JUDGED_VERDICTS)


def support_rate(record: RunRecord) -> float:
    total = judged(record)
    if total == 0:
        return 0.0
    return (
        record.support.get("supported", 0) + record.support.get("partial", 0)
    ) / total


def verified_rate(record: RunRecord) -> float:
    if record.evidence_total == 0:
        return 0.0
    return record.evidence_verified / record.evidence_total


def citation_precision(record: RunRecord) -> float:
    """Share of cited records that were citable. An invariant, not a score."""
    if record.citations == 0:
        return 0.0
    return (record.citations - record.unsupported_citations) / record.citations


def citation_coverage(record: RunRecord) -> float:
    """Share of citable evidence the writer actually used."""
    if record.evidence_citable == 0:
        return 0.0
    return record.evidence_cited / record.evidence_citable


def keyword_recall(record: RunRecord) -> float:
    total = len(record.keyword_hits) + len(record.keyword_misses)
    if total == 0:
        return 0.0
    return len(record.keyword_hits) / total


def successful(record: RunRecord) -> bool:
    return record.ok and record.report_ok and record.citations > 0


# --------------------------------------------------------------------------- #
# aggregate
# --------------------------------------------------------------------------- #
def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 1]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _rate(records: list[RunRecord], fn) -> float:
    return _mean([1.0 if fn(record) else 0.0 for record in records])


def _repair_rate(records: list[RunRecord]) -> float | None:
    """None when the run predates the field: unknown is not 0%."""
    known = [record for record in records if record.writer_repaired is not None]
    if not known:
        return None
    return _mean([1.0 if record.writer_repaired else 0.0 for record in known])


def _precision(records: list[RunRecord]) -> float | None:
    citations = sum(record.citations for record in records)
    if citations == 0:
        return None
    bad = sum(record.unsupported_citations for record in records)
    return (citations - bad) / citations


def summarize(records: list[RunRecord]) -> dict:
    tokens = [float(record.tokens_total) for record in records]
    seconds = [record.duration_s for record in records]
    summary = {
        "n": len(records),
        "success_rate": _rate(records, successful),
        "error_rate": _rate(records, lambda r: not r.ok),
        "support_rate": _mean([support_rate(record) for record in records]),
        "verified_rate": _mean([verified_rate(record) for record in records]),
        # Micro-averaged on purpose. Precision is a property of the citations,
        # not of the questions: a report that cited nothing has no precision,
        # and averaging a 0.0 for it would report a broken invariant that did
        # not break. Missing citations are visible in success_rate instead.
        "citation_precision": _precision(records),
        "citation_coverage": _mean(
            [citation_coverage(record) for record in records]
        ),
        "keyword_recall": _mean([keyword_recall(record) for record in records]),
        "misconception_rate": _rate(records, lambda r: bool(r.misconception_hits)),
        "repair_rate": _repair_rate(records),
        "mean_words": _mean([float(record.words) for record in records]),
        "mean_tokens": _mean(tokens),
        "p50_tokens": _percentile(tokens, 0.5),
        "p90_tokens": _percentile(tokens, 0.9),
        "mean_seconds": _mean(seconds),
        "total_tokens": int(sum(tokens)),
        "total_seconds": round(sum(seconds), 1),
        "unsupported_citations": sum(r.unsupported_citations for r in records),
        "contradictions": sum(r.contradictions for r in records),
        "verdicts": {
            verdict: sum(r.support.get(verdict, 0) for r in records)
            for verdict in (
                "supported",
                "partial",
                "unsupported",
                "contradicted",
                "unjudged",
            )
        },
        "by_category": _by_category(records),
    }
    return summary


def _by_category(records: list[RunRecord]) -> dict[str, dict]:
    groups: dict[str, list[RunRecord]] = {}
    for record in records:
        groups.setdefault(record.category, []).append(record)
    return {
        category: {
            "n": len(group),
            "success_rate": _rate(group, successful),
            "support_rate": _mean([support_rate(record) for record in group]),
            "mean_tokens": _mean([float(record.tokens_total) for record in group]),
        }
        for category, group in sorted(groups.items())
    }


# --------------------------------------------------------------------------- #
# regression comparison (step 12 uses this)
# --------------------------------------------------------------------------- #
COMPARED = (
    "success_rate",
    "support_rate",
    "verified_rate",
    "citation_coverage",
    "keyword_recall",
    "mean_tokens",
    "mean_seconds",
)


def compare(baseline: dict, candidate: dict) -> dict:
    """Diff two summaries and name the regressions, not just the numbers."""
    rows = []
    for key in COMPARED:
        before = float(baseline.get(key, 0.0))
        after = float(candidate.get(key, 0.0))
        rows.append(
            {
                "metric": key,
                "baseline": round(before, 4),
                "candidate": round(after, 4),
                "delta": round(after - before, 4),
            }
        )

    regressions: list[str] = []
    if candidate.get("unsupported_citations", 0) > 0:
        regressions.append(
            "unsupported citations appeared "
            f"({candidate['unsupported_citations']}): the citation invariant broke"
        )
    if baseline.get("citation_precision", 1.0) is not None and baseline.get(
        "citation_precision", 1.0
    ) >= 0.999 and (candidate.get("citation_precision") or 0.0) < 0.999:
        regressions.append("citation precision fell below 1.0")
    if baseline.get("success_rate", 0) - candidate.get("success_rate", 0) > 0.05:
        regressions.append(
            f"success rate dropped {baseline['success_rate']:.0%} -> "
            f"{candidate['success_rate']:.0%}"
        )
    if baseline.get("support_rate", 0) - candidate.get("support_rate", 0) > 0.03:
        regressions.append(
            f"support rate dropped {baseline['support_rate']:.0%} -> "
            f"{candidate['support_rate']:.0%}"
        )
    return {"rows": rows, "regressions": regressions}


SUMMARY_METRICS = (
    ("success_rate", "success rate", "pct"),
    ("support_rate", "claim support", "pct"),
    ("keyword_recall", "keyword recall", "pct"),
    ("citation_coverage", "citation coverage", "pct"),
    ("citation_precision", "citation precision (invariant)", "pct"),
    ("misconception_rate", "misconception hits", "pct"),
    ("repair_rate", "writer repair turns", "pct"),
    ("mean_words", "words / report", "num"),
    ("mean_tokens", "tokens / question", "num"),
    ("mean_seconds", "seconds / question", "num"),
)


def to_markdown(summary: dict, title: str = "Eval summary") -> str:
    lines = [f"# {title}", ""]
    lines.append(f"- questions: **{summary['n']}**")
    if summary.get("model"):
        lines.append(
            f"- model: `{summary['model']}` (judge: `{summary.get('judge_model', '')}`)"
        )
    lines.append(f"- total tokens: **{summary['total_tokens']:,}**")
    lines.append(f"- total time: **{summary['total_seconds']}s**")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    for key, label, kind in SUMMARY_METRICS:
        value = summary.get(key, 0)
        if value is None:
            lines.append(f"| {label} | n/a |")
            continue
        rendered = f"{value:.1%}" if kind == "pct" else f"{value:.1f}"
        lines.append(f"| {label} | {rendered} |")
    lines.append("")
    verdicts = summary.get("verdicts", {})
    if verdicts:
        lines.append(
            "judged claims: "
            + ", ".join(f"{name} {count}" for name, count in verdicts.items())
        )
        lines.append("")
    lines.append("| category | n | success | support | tokens |")
    lines.append("| --- | --- | --- | --- | --- |")
    for category, row in summary.get("by_category", {}).items():
        lines.append(
            f"| {category} | {row['n']} | {row['success_rate']:.0%} | "
            f"{row['support_rate']:.0%} | {row['mean_tokens']:.0f} |"
        )
    return "\n".join(lines)
