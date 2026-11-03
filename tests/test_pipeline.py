from __future__ import annotations

import asyncio

from research_agent.pipeline import PipelineConfig, ResearchPipeline


class BoomClient:
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
