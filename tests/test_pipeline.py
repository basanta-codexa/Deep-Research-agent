from __future__ import annotations

import asyncio

from research_agent.pipeline import PipelineConfig, ResearchPipeline


class BoomClient:
    name = "boom"
    model = "boom"

    async def chat(self, *args, **kwargs):
        raise RuntimeError("no network")

    async def aclose(self) -> None:
        return None


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
