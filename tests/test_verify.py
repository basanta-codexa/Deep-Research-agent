from __future__ import annotations

import asyncio
import json

from research_agent.evidence import EvidenceStore
from research_agent.llm import LLMResponse, Message, Usage
from research_agent.verify import (
    ClaimVerifier,
    Contradiction,
    SupportJudgement,
    VerificationReport,
    apply_verification,
    source_tier,
    verify_store,
)

DOC = "https://docs.python.org/3/library/asyncio-task.html"
BLOG = "https://runebook.dev/en/docs/python/library/asyncio-task"
SO = "https://stackoverflow.com/questions/1"


class FakeClient:
    """Scripted LLM client: no network, deterministic order."""

    def __init__(self, replies: list[object]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def chat(self, messages, *, tools=None, temperature=None, max_tokens=None, json_mode=False):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            message=Message.assistant(str(reply)),
            model="fake",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


def make_store() -> EvidenceStore:
    store = EvidenceStore()
    store.register_source(DOC, "The first exception is propagated to the caller.")
    store.register_source(BLOG, "The remaining tasks are cancelled on failure.")
    one = store.add("propagates first exception", "The first exception is propagated to the caller.", DOC)
    two = store.add("cancels remaining tasks", "The remaining tasks are cancelled on failure.", BLOG)
    assert one is not None and two is not None
    return store


def test_source_tier_is_deterministic():
    assert source_tier(DOC) == "primary"
    assert source_tier("https://docs.python.org/3/") == "primary"
    assert source_tier(SO) == "community"
    assert source_tier(BLOG) == "aggregator"
    assert source_tier("https://www.superfastpython.com/x") == "aggregator"
    assert source_tier("https://example.com/x") == "unknown"


def test_judge_parses_json_in_plain_mode():
    client = FakeClient(['{"verdict": "supported", "reason": "says the same thing"}'])
    judgement, usage = asyncio.run(ClaimVerifier(client).judge("claim", "quote"))
    assert judgement.verdict == "supported"
    assert usage.total_tokens == 15
    assert client.calls == 1


def test_judge_retries_when_first_reply_is_not_json():
    client = FakeClient(
        ["I think it is supported!", '{"verdict": "partial", "reason": "close enough"}']
    )
    judgement, _ = asyncio.run(ClaimVerifier(client).judge("claim", "quote"))
    assert judgement.verdict == "partial"
    assert client.calls == 2


def test_verify_items_records_failures_instead_of_crashing():
    store = make_store()
    items = list(store.items)
    client = FakeClient(
        ['{"verdict": "supported", "reason": "ok"}', RuntimeError("network down")]
    )
    report = asyncio.run(ClaimVerifier(client).verify_items(items, concurrency=1))
    assert len(report.judgements) == 1
    assert len(report.errors) == 1


def test_find_conflicts_drops_groups_with_dangling_ids():
    store = make_store()
    items = list(store.items)
    dangling = json.dumps(
        {"conflicts": [{"ids": [items[0].id, "ev_99999999"], "why": "invented"}]}
    )
    client = FakeClient([dangling])
    conflicts, _ = asyncio.run(ClaimVerifier(client).find_conflicts(items))
    assert conflicts == []


def test_find_conflicts_keeps_real_pairs():
    store = make_store()
    items = list(store.items)
    valid = json.dumps(
        {"conflicts": [{"ids": [items[0].id, items[1].id], "why": "opposite"}]}
    )
    client = FakeClient([valid])
    conflicts, _ = asyncio.run(ClaimVerifier(client).find_conflicts(items))
    assert len(conflicts) == 1
    assert conflicts[0].ids == [items[0].id, items[1].id]


def test_apply_verification_fails_closed_on_errors():
    store = make_store()
    items = list(store.items)
    report = VerificationReport(
        judgements={items[0].id: SupportJudgement(verdict="supported", reason="ok")},
        errors={items[1].id: "provider timeout"},
    )
    apply_verification(store, report)
    assert items[0].support == "supported"
    assert items[0].trust == "primary"
    assert items[1].support == "unjudged"
    assert items[1].trust == "aggregator"
    assert items[0] in store.citable()
    assert items[1] not in store.citable()


def test_verify_store_retries_transient_failures_sequentially():
    store = make_store()
    client = FakeClient(
        [
            '{"verdict": "supported", "reason": "ok"}',
            RuntimeError("429"),
            '{"verdict": "partial", "reason": "retried"}',
        ]
    )
    report = asyncio.run(
        verify_store(client, store, check_conflicts=False, concurrency=1)
    )
    assert report.errors == {}
    assert len(report.judgements) == 2
    verdicts = sorted(j.verdict for j in report.judgements.values())
    assert verdicts == ["partial", "supported"]


def test_verify_store_marks_unjudged_when_retry_also_fails():
    store = make_store()
    client = FakeClient(
        [
            '{"verdict": "supported", "reason": "ok"}',
            RuntimeError("429"),
            RuntimeError("429 again"),
        ]
    )
    report = asyncio.run(
        verify_store(client, store, check_conflicts=False, concurrency=1)
    )
    assert len(report.errors) == 1
    unjudged = [item for item in store.items if item.support == "unjudged"]
    assert len(unjudged) == 1
    assert unjudged[0] not in store.citable()


def test_contradiction_dataclass_is_serialisable():
    from dataclasses import asdict

    conflict = Contradiction(ids=["ev_11111111", "ev_22222222"], why="opposite")
    assert asdict(conflict)["ids"] == ["ev_11111111", "ev_22222222"]
