from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from research_agent.evidence import EvidenceStore
from research_agent.pipeline import PipelineResult
from research_agent.tracing import Tracer
from research_agent.writer import Report
from web.server import create_app

TEXT = "The GIL prevents multiple threads from executing Python bytecodes at once."
QUOTE = "prevents multiple threads from executing Python bytecodes"


class FakePipeline:
    client = SimpleNamespace(name="fake", model="fake-1")
    judge_client = SimpleNamespace(model="fake-judge")

    async def run(self, question: str, *, tracer: Tracer | None = None, **_: Any):
        assert tracer is not None
        with tracer.activate():
            with tracer.span("pipeline", kind="pipeline"):
                with tracer.span("plan", kind="stage") as item:
                    item.attributes["questions"] = [{"question": "What is the GIL?"}]
        store = EvidenceStore()
        store.register_source("https://example.com/gil", TEXT, "Example")
        found = store.add(claim="Only one thread runs bytecode.", quote=QUOTE, url="https://example.com/gil")
        body = f"Bytecode is serialized [{found.id}]."
        report = Report(markdown=f"# GIL\n\n{body}", body=body, cited_ids=[found.id], word_count=4)
        return PipelineResult(question=question, store=store, report=report, trace=tracer)


def test_index_and_config():
    with TestClient(create_app(FakePipeline())) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Ask a question" in page.text
        assert client.get("/static/styles.css").status_code == 200

        config = client.get("/api/config").json()
        assert config["model"] == "fake-1"
        assert config["judge_model"] == "fake-judge"
        assert config["max_seconds"] > 0


def test_question_validation():
    with TestClient(create_app(FakePipeline())) as client:
        too_short = client.post("/api/research", json={"question": "hi"})
        assert too_short.status_code == 422
        too_long = client.post("/api/research", json={"question": "x" * 600})
        assert too_long.status_code == 422


def test_research_streams_sse():
    with TestClient(create_app(FakePipeline())) as client:
        with client.stream(
            "POST", "/api/research", json={"question": "What is the GIL?"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

    assert "event: start" in body
    assert "event: span" in body
    assert "event: report" in body
    assert "event: done" in body
