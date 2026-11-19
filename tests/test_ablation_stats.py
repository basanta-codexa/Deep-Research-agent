from __future__ import annotations

import json

from evals.ablation_stats import load, paired
from evals.metrics import RunRecord


def make_record(
    item_id: str,
    *,
    ok: bool = True,
    supported: int = 1,
    unsupported: int = 0,
    duration_s: float = 10.0,
    tokens_total: int = 1000,
    cost_usd: float = 0.001,
) -> RunRecord:
    return RunRecord(
        item_id=item_id,
        category="test",
        question="a question",
        ok=ok,
        report_ok=ok,
        citations=1 if ok else 0,
        support={"supported": supported, "unsupported": unsupported},
        evidence_citable=1,
        evidence_cited=1 if ok else 0,
        keyword_hits=["term"] if ok else [],
        keyword_misses=[] if ok else ["term"],
        duration_s=duration_s,
        tokens_total=tokens_total,
        cost_usd=cost_usd,
    )


def test_load_and_paired_delta_align_questions(tmp_path):
    control = {
        "a": make_record("a", duration_s=10),
        "b": make_record("b", duration_s=20),
    }
    candidate = {
        "a": make_record("a", duration_s=15),
        "b": make_record("b", ok=False, supported=0, unsupported=1, duration_s=30),
    }
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps({"records": [record.to_dict() for record in control.values()]}),
        encoding="utf-8",
    )

    loaded = load(str(path))
    result = paired(control, candidate, "success")
    latency = paired(control, candidate, "seconds")

    assert set(loaded) == {"a", "b"}
    assert result is not None
    delta, low, high, n = result
    assert delta == -0.5
    assert low <= delta <= high
    assert n == 2
    assert latency is not None
    assert latency[0] == 7.5
