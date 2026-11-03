from __future__ import annotations

import asyncio
import json

import pytest

from research_agent.llm import LLMResponse, Message, Usage
from research_agent.pricing import (
    Price,
    apply_cost,
    estimate_cost,
    lookup,
)
from research_agent.tracing import Span, Tracer, TraceLLMClient, span


@pytest.fixture(autouse=True)
def no_price_override(monkeypatch):
    monkeypatch.delenv("RA_PRICE_INPUT", raising=False)
    monkeypatch.delenv("RA_PRICE_OUTPUT", raising=False)


# --------------------------------------------------------------------------- #
# pricing
# --------------------------------------------------------------------------- #
def test_provider_default_price_is_used_when_the_model_is_not_listed():
    assert lookup("groq", "openai/gpt-oss-120b") == Price(0.0, 0.0)


def test_model_specific_price_beats_the_provider_default():
    assert lookup("openai", "gpt-4o-mini") == Price(0.15, 0.60)


def test_unknown_provider_is_unpriced_not_free():
    assert lookup("mystery", "some-model") is None


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("RA_PRICE_INPUT", "1.5")
    monkeypatch.setenv("RA_PRICE_OUTPUT", "6")
    assert lookup("groq", "anything") == Price(1.5, 6.0)


def test_half_an_override_is_ignored(monkeypatch):
    monkeypatch.setenv("RA_PRICE_INPUT", "1.5")
    assert lookup("groq", "anything") == Price(0.0, 0.0)


def test_estimate_cost_uses_per_million_pricing():
    price = Price(input_per_mtok=1.0, output_per_mtok=2.0)
    assert estimate_cost(price, 1_000_000, 0) == pytest.approx(1.0)
    assert estimate_cost(price, 0, 500_000) == pytest.approx(1.0)


def test_apply_cost_leaves_cost_at_zero_but_reports_unpriced():
    usage, priced = apply_cost("mystery", "m", Usage(prompt_tokens=10, completion_tokens=5))
    assert priced is False
    assert usage.cost_usd == 0.0


# --------------------------------------------------------------------------- #
# span nesting and concurrency
# --------------------------------------------------------------------------- #
def test_spans_nest_through_the_context_variable():
    tracer = Tracer("nesting")
    with tracer.activate():
        with tracer.span("pipeline", kind="pipeline") as root:
            with tracer.span("plan", kind="stage") as stage:
                with span("llm", kind="llm") as call:
                    assert call is not None
                    call.usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    by_name = {item.name: item for item in tracer.spans}
    assert by_name["plan"].parent_id == root.id
    assert by_name["llm"].parent_id == stage.id
    assert by_name["pipeline"].parent_id is None


def test_concurrent_tasks_each_attach_to_the_same_parent_without_crossing():
    tracer = Tracer("concurrent")

    async def scenario():
        with tracer.activate():
            with tracer.span("research", kind="stage") as parent:
                async def child(name: str, delay: float):
                    with tracer.span(name, kind="subagent") as item:
                        await asyncio.sleep(delay)
                        return item

                a, b = await asyncio.gather(child("a", 0.01), child("b", 0.005))
        return parent, a, b

    parent, a, b = asyncio.run(scenario())
    assert a.parent_id == parent.id
    assert b.parent_id == parent.id
    assert a.id != b.id
    assert all(item.parent_id != a.id for item in tracer.spans if item is not a)


def test_no_active_tracer_makes_span_a_noop():
    with span("anything", kind="llm") as item:
        assert item is None


def test_activate_is_reset_on_exit():
    tracer = Tracer("reset")
    with tracer.activate():
        pass
    from research_agent.tracing import current_tracer

    assert current_tracer() is None


def test_failed_span_is_marked_as_an_error():
    tracer = Tracer("errors")
    with pytest.raises(RuntimeError):
        with tracer.activate():
            with tracer.span("boom", kind="stage"):
                raise RuntimeError("kaboom")
    assert tracer.spans[0].status == "error"
    assert "kaboom" in (tracer.spans[0].error or "")


# --------------------------------------------------------------------------- #
# attribution
# --------------------------------------------------------------------------- #
def make_span(tracer: Tracer, name, kind, parent, start, end, usage=None):
    item = Span(
        id=f"{name}-id",
        name=name,
        kind=kind,
        parent_id=parent,
        start_ms=start,
        end_ms=end,
        usage=usage or Usage(),
    )
    tracer.spans.append(item)
    return item


def test_usage_counts_llm_spans_only_to_avoid_double_counting():
    tracer = Tracer("usage")
    make_span(tracer, "pipeline", "pipeline", None, 0, 100)
    make_span(tracer, "research", "stage", "pipeline-id", 0, 90)
    make_span(
        tracer,
        "llm1",
        "llm",
        "research-id",
        0,
        40,
        Usage(prompt_tokens=100, completion_tokens=10, total_tokens=110),
    )
    make_span(
        tracer,
        "llm2",
        "llm",
        "research-id",
        40,
        90,
        Usage(prompt_tokens=50, completion_tokens=5, total_tokens=55),
    )

    assert tracer.usage().total_tokens == 165
    summary = tracer.summary()
    assert summary["tokens"]["total"] == 165
    assert summary["llm_calls"] == 2


def test_tokens_are_attributed_to_the_nearest_stage():
    tracer = Tracer("stages")
    make_span(tracer, "pipeline", "pipeline", None, 0, 100)
    make_span(tracer, "plan", "stage", "pipeline-id", 0, 20)
    make_span(tracer, "write", "stage", "pipeline-id", 20, 100)
    make_span(
        tracer,
        "llm-plan",
        "llm",
        "plan-id",
        0,
        20,
        Usage(prompt_tokens=30, completion_tokens=5, total_tokens=35),
    )
    make_span(
        tracer,
        "llm-write",
        "llm",
        "write-id",
        20,
        100,
        Usage(prompt_tokens=200, completion_tokens=50, total_tokens=250),
    )

    by_stage = tracer.summary()["by_stage"]
    assert by_stage["plan"]["total"] == 35
    assert by_stage["write"]["total"] == 250
    assert by_stage["write"]["calls"] == 1


def test_critical_path_follows_the_branch_that_ends_last():
    tracer = Tracer("critical")
    make_span(tracer, "root", "pipeline", None, 0, 300)
    make_span(tracer, "fast", "stage", "root-id", 0, 100)
    make_span(tracer, "slow", "stage", "root-id", 0, 300)
    make_span(tracer, "fast-child", "llm", "fast-id", 0, 100)
    make_span(tracer, "slow-child", "llm", "slow-id", 100, 300)

    assert [item.name for item in tracer.critical_path()] == [
        "root",
        "slow",
        "slow-child",
    ]
    summary_path = tracer.summary()["critical_path"]
    assert [entry["name"] for entry in summary_path] == ["root", "slow", "slow-child"]
    assert summary_path[0]["id"] == "root-id"


# --------------------------------------------------------------------------- #
# the tracing client
# --------------------------------------------------------------------------- #
class FakeInner:
    name = "openai"
    model = "gpt-4o-mini"

    def __init__(self, usage: Usage, model: str | None = None) -> None:
        self.usage = usage
        self.reply_model = model or self.model
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        return LLMResponse(
            message=Message.assistant("ok"),
            model=self.reply_model,
            usage=self.usage,
            latency_ms=12.5,
            finish_reason="stop",
        )

    async def aclose(self) -> None:
        return None


def test_tracing_client_records_usage_and_cost():
    inner = FakeInner(Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500))
    client = TraceLLMClient(inner)
    tracer = Tracer("client")

    with tracer.activate():
        response = asyncio.run(client.chat([Message.user("hi")]))

    assert response.message.content == "ok"
    assert inner.calls == 1
    llm = [item for item in tracer.spans if item.kind == "llm"][0]
    assert llm.usage.total_tokens == 1500
    assert llm.usage.cost_usd == pytest.approx(0.00015 + 0.0003)
    assert llm.attributes["priced"] is True
    assert llm.attributes["latency_ms"] == 12.5


def test_unpriced_calls_make_the_total_unknown_not_zero():
    inner = FakeInner(Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
    inner.name = "mystery"
    tracer = Tracer("priced?")
    with tracer.activate():
        asyncio.run(TraceLLMClient(inner).chat([Message.user("hi")]))

    summary = tracer.summary()
    assert summary["cost_usd"] is None
    assert summary["unpriced_models"] == ["gpt-4o-mini"]


def test_tracing_client_works_without_a_tracer():
    inner = FakeInner(Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    client = TraceLLMClient(inner)
    response = asyncio.run(client.chat([Message.user("hi")]))
    assert response.message.content == "ok"


# --------------------------------------------------------------------------- #
# artifacts
# --------------------------------------------------------------------------- #
def test_trace_json_has_the_expected_shape(tmp_path):
    tracer = Tracer("shape")
    with tracer.activate():
        with tracer.span("pipeline", kind="pipeline"):
            with tracer.span("plan", kind="stage"):
                pass

    path = tracer.save(tmp_path / "trace.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == "shape"
    assert len(payload["spans"]) == 2
    assert payload["summary"]["llm_calls"] == 0
    assert payload["spans"][0]["kind"] == "pipeline"


def test_html_escapes_model_output_and_embeds_the_data():
    tracer = Tracer("<script>alert(1)</script>")
    with tracer.activate():
        with tracer.span("pipeline", kind="pipeline"):
            pass

    page = tracer.to_html()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert 'id="trace-data"' in page
    assert "Waterfall" in page
