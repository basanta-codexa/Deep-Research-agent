from __future__ import annotations

import asyncio

import research_agent.pipeline as pipeline_module
from research_agent.llm import Usage
from research_agent.pipeline import (
    PipelineConfig,
    ResearchPipeline,
    single_agent_plan,
)
from research_agent.planning import Plan, SubQuestion
from research_agent.retrieval.cache import NullCache
from research_agent.subagent import (
    EXTRACT_PROMPT,
    FindingModel,
    ResearchBatch,
    SubAgentResult,
)
from research_agent.writer import Report


class BoomClient:
    name = "boom"
    model = "boom"

    async def chat(self, *args, **kwargs):
        raise RuntimeError("no network")

    async def aclose(self) -> None:
        return None


class FakePlanner:
    def __init__(self, client, *, max_tokens: int = 1200) -> None:
        self.client = client

    async def plan(self, question: str):
        plan = Plan(
            restated=question,
            sub_questions=[
                SubQuestion(
                    question=f"Part {index} of {question}",
                    search_query=f"part {index}",
                    why="test evidence",
                )
                for index in range(3)
            ],
        )
        return plan, 0, 0


class ExplodingPlanner:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("the planner must not run in single-agent mode")


class FakeOrchestrator:
    def __init__(self, client, tools, *, concurrency=2, max_steps=3) -> None:
        self.client = client
        self.tools = tools

    async def run(self, sub_questions, **kwargs):
        url = "https://example.com/fact"
        text = "A fact that supports the claim."
        finding = FindingModel(
            claim="the claim", quote=text, url=url, confidence="high"
        )
        result = SubAgentResult(
            question=sub_questions[0].question,
            search_query=sub_questions[0].search_query,
            findings=[finding],
            source_texts={url: text},
            source_titles={url: "Example"},
        )
        return ResearchBatch(
            results=[result], usage=Usage(), wall_clock_s=0.0, concurrency=1
        )


class FakeWriter:
    def __init__(self, client, *, max_tokens: int = 1800) -> None:
        self.client = client

    async def write(self, *, question, plan, store, gaps):
        item = store.verified_items[0]
        return Report(
            markdown="# Report\n\nA fact [1].",
            body="A fact that supports the claim.",
            cited_ids=[item.id],
            word_count=5,
        )


def fake_stages(monkeypatch):
    monkeypatch.setattr(pipeline_module, "Planner", FakePlanner)
    monkeypatch.setattr(pipeline_module, "ResearchOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(pipeline_module, "ReportWriter", FakeWriter)


def test_plan_failure_is_recorded_not_raised():
    pipeline = ResearchPipeline(BoomClient(), tools=[], config=PipelineConfig())
    result = asyncio.run(pipeline.run("Does a failing planner crash the harness?"))
    assert result.ok is False
    assert result.error is not None and result.error.startswith("plan:")
    assert "RuntimeError" in result.stage_errors["plan"]
    assert result.report is None
    assert result.timings == {}


def test_failed_run_still_reports_the_question():
    pipeline = ResearchPipeline(BoomClient(), tools=[])
    result = asyncio.run(pipeline.run("Another question"))
    assert result.question == "Another question"


def test_a_failed_run_still_produces_a_trace():
    pipeline = ResearchPipeline(BoomClient(), tools=[])
    result = asyncio.run(pipeline.run("Trace the failure"))

    assert result.trace is not None
    spans = {item.name: item for item in result.trace.spans}
    assert spans["pipeline"].kind == "pipeline"
    assert spans["plan"].status == "error"
    assert (spans["plan"].error or "").startswith("RuntimeError")
    # The failed model call is still a span, and still an error.
    summary = result.trace.summary()
    assert summary["llm_calls"] >= 1
    assert summary["errors"] >= 1


def test_single_agent_plan_is_deliberately_one_sub_question():
    plan = single_agent_plan("A question that normally needs decomposition?")

    assert plan.restated == "A question that normally needs decomposition?"
    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].question == plan.restated


def test_single_agent_skips_the_planner_but_still_writes(monkeypatch):
    fake_stages(monkeypatch)
    monkeypatch.setattr(pipeline_module, "Planner", ExplodingPlanner)
    question = "Does one research thread still produce a cited report?"
    pipeline = ResearchPipeline(
        BoomClient(),
        tools=[],
        config=PipelineConfig(single_agent=True, verify=False),
    )

    result = asyncio.run(pipeline.run(question))

    assert result.ok is True
    assert result.plan is not None
    assert len(result.plan.sub_questions) == 1
    assert result.report is not None and result.report.cited_ids
    assert result.trace is not None
    assert result.trace.attributes["single_agent"] is True
    spans = {item.name: item for item in result.trace.spans}
    assert spans["plan"].attributes["skipped"] is True


def test_verify_can_be_disabled_without_losing_citations(monkeypatch):
    fake_stages(monkeypatch)
    calls: list[bool] = []

    async def must_not_run(*args, **kwargs):
        calls.append(True)
        raise AssertionError("verify_store must not run when verify=False")

    monkeypatch.setattr(pipeline_module, "verify_store", must_not_run)
    pipeline = ResearchPipeline(
        BoomClient(),
        tools=[],
        config=PipelineConfig(verify=False),
    )

    result = asyncio.run(pipeline.run("Can verification be skipped?"))

    assert result.ok is True
    assert result.verification is None
    assert result.report is not None and result.report.cited_ids
    assert calls == []
    assert result.trace is not None
    assert result.trace.attributes["verify"] is False
    spans = {item.name: item for item in result.trace.spans}
    assert spans["verify"].attributes["skipped"] is True
    assert "verify" in result.timings


def test_extractor_prompt_requires_atomic_claims():
    assert "ONE atomic statement" in EXTRACT_PROMPT
    assert "narrower claim" in EXTRACT_PROMPT


def test_null_cache_never_stores_anything():
    async def check() -> None:
        cache = NullCache()
        await cache.aset("key", {"value": 1})
        assert await cache.aget("key") is None
        assert cache.stats()["enabled"] is False

    asyncio.run(check())
