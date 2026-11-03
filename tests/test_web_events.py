from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from research_agent.evidence import EvidenceStore
from research_agent.pipeline import PipelineResult
from research_agent.tracing import Tracer
from research_agent.writer import Report
from web.events import sse, span_payload, stream_run

URL = "https://example.com/gil"
TEXT = "The GIL prevents multiple threads from executing Python bytecodes at once."
QUOTE = "prevents multiple threads from executing Python bytecodes"


def make_result(question: str = "What is the GIL?") -> PipelineResult:
    store = EvidenceStore()
    store.register_source(URL, TEXT, "Example")
    item = store.add(claim="The GIL serializes bytecode.", quote=QUOTE, url=URL)
    assert item is not None
    item.support = "supported"
    item.trust = "community"
    body = f"Only one thread runs bytecode [{item.id}]."
    report = Report(
        markdown=f"# GIL\n\n{body}\n",
        body=body,
        cited_ids=[item.id],
        word_count=4,
    )
    return PipelineResult(question=question, store=store, report=report)


class FakePipeline:
    client = SimpleNamespace(name="fake", model="fake-1")
    judge_client = SimpleNamespace(model="fake-judge")

    def __init__(self, result: PipelineResult | None = None, delay: float = 0.0) -> None:
        self.result = result
        self.delay = delay

    async def run(self, question: str, *, tracer: Tracer | None = None, **_: Any):
        if self.delay:
            await asyncio.sleep(self.delay)
        assert tracer is not None
        with tracer.activate():
            with tracer.span("pipeline", kind="pipeline"):
                with tracer.span("plan", kind="stage") as item:
                    await asyncio.sleep(0)
                    item.attributes["questions"] = [{"question": "What is the GIL?"}]
        return self.result if self.result is not None else make_result(question)


async def collect(pipeline: FakePipeline, timeout: float = 5.0) -> list[str]:
    return [frame async for frame in stream_run(pipeline, "What is the GIL?", timeout=timeout)]


def parse(frames: list[str]) -> list[tuple[str, dict[str, Any] | None]]:
    events = []
    for frame in frames:
        event = "message"
        data = ""
        for line in frame.strip().split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        events.append((event, json.loads(data) if data else None))
    return events


def test_sse_format():
    frame = sse({"type": "ping", "value": 1})
    assert frame.startswith("event: ping\n")
    assert frame.endswith("\n\n")
    assert json.loads(frame.split("data: ", 1)[1]) == {"type": "ping", "value": 1}


def test_span_payload_has_phase_and_safe_attributes():
    tracer = Tracer("test")
    with tracer.activate():
        with tracer.span("plan", kind="stage", note="x") as item:
            item.attributes["questions"] = [{"question": "q"}]
    start = span_payload(item, "start")
    end = span_payload(item, "end")
    assert start["phase"] == "start"
    assert start["duration_ms"] is None
    assert end["duration_ms"] is not None
    assert end["attributes"]["questions"] == [{"question": "q"}]


def test_stream_runs_start_to_done():
    frames = asyncio.run(collect(FakePipeline()))
    events = parse(frames)
    types = [event for event, _ in events]

    assert types[0] == "start"
    assert types[-1] == "done"
    assert events[-1][1] == {"type": "done", "ok": True}

    assert "span" in types
    spans = [payload for event, payload in events if event == "span"]
    assert any(payload["phase"] == "start" for payload in spans)
    plan_end = [p for p in spans if p["phase"] == "end" and p["attributes"].get("questions")]
    assert plan_end and plan_end[0]["attributes"]["questions"][0]["question"] == "What is the GIL?"

    report = next(payload for event, payload in events if event == "report")["data"]
    assert report["sources"][0]["passages"][0]["span"] is not None
    assert report["stats"]["cited_passages"] == 1


def test_result_with_error_sends_error_and_done():
    failed = PipelineResult(question="What is the GIL?", error="planner exploded")
    events = parse(asyncio.run(collect(FakePipeline(failed))))
    types = [event for event, _ in events]
    assert "error" in types
    assert events[-1][1] == {"type": "done", "ok": False}
    error = next(payload for event, payload in events if event == "error")
    assert "planner exploded" in error["message"]


def test_timeout_cancels_the_run():
    frames = asyncio.run(collect(FakePipeline(delay=5.0), timeout=0.05))
    events = parse(frames)
    error = next(payload for event, payload in events if event == "error")
    assert "cancelled" in error["message"]
    assert "trace" in error
    assert events[-1][1] == {"type": "done", "ok": False}


def test_runner_exception_becomes_an_error_event():
    class Exploding(FakePipeline):
        async def run(self, question: str, *, tracer: Tracer | None = None, **_: Any):
            raise RuntimeError("boom")

    events = parse(asyncio.run(collect(Exploding())))
    error = next(payload for event, payload in events if event == "error")
    assert "RuntimeError" in error["message"]
    assert events[-1][1]["ok"] is False


def test_listener_failure_does_not_break_the_run():
    def bad_listener(phase: str, item) -> None:
        raise RuntimeError("listener bug")

    tracer = Tracer("test", listeners=[bad_listener])
    with tracer.activate():
        with tracer.span("plan", kind="stage"):
            pass
    assert len(tracer.spans) == 1
    assert tracer.spans[0].status == "ok"


@pytest.mark.parametrize("phase", ["start", "end"])
def test_span_payload_keeps_tool_args(phase: str):
    tracer = Tracer("test")
    with tracer.activate():
        with tracer.span("read_source", kind="tool", args='{"query": "gil"}'):
            pass
    payload = span_payload(tracer.spans[0], phase)
    assert json.loads(payload["attributes"]["args"])["query"] == "gil"
