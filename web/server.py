"""FastAPI app: one page, one streaming endpoint, no build step.

Run it with::

    .\\venv\\Scripts\\python.exe -m web.server
    # or: .\\venv\\Scripts\\uvicorn.exe web.server:app --reload

Design notes
------------
* The app owns one pipeline per process. A run's state lives in the tracer
  supplied per request, so two tabs can run at once; the provider's rate limit
  is the real concurrency cap.
* ``create_app(pipeline=...)`` lets tests inject a fake pipeline and skip the
  provider entirely — no network, no API key, no 90-second wait.
* The SSE endpoint is a POST, not an EventSource GET: the question belongs in
  the request body, and EventSource cannot send one. The client uses fetch +
  ReadableStream, which is ~20 lines.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from research_agent.config import Settings, load_dotenv
from research_agent.llm import create_client
from research_agent.pipeline import PipelineConfig, ResearchPipeline
from research_agent.tools.web import make_subagent_tools

from .events import DEFAULT_TIMEOUT_S, stream_run

STATIC_DIR = Path(__file__).parent / "static"


def _env_timeout() -> float:
    """Wall-clock budget for one run. 6 min by default; RA_WEB_TIMEOUT overrides."""
    load_dotenv()
    raw = os.getenv("RA_WEB_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        return max(30.0, float(raw))
    except ValueError as exc:
        raise ValueError(f"RA_WEB_TIMEOUT must be a number, got {raw!r}") from exc


def build_pipeline(
    settings: Settings, *, concurrency: int = 2, max_steps: int = 3
) -> ResearchPipeline:
    return ResearchPipeline(
        create_client(settings),
        make_subagent_tools(settings),
        judge_client=create_client(settings.judge_settings()),
        config=PipelineConfig(concurrency=concurrency, max_steps=max_steps),
    )


class ResearchRequest(BaseModel):
    question: str = Field(max_length=2000)


def create_app(
    pipeline: ResearchPipeline | None = None,
    *,
    timeout: float | None = None,
) -> FastAPI:
    owned = pipeline is None
    timeout = _env_timeout() if timeout is None else timeout

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pipeline is None:
            settings = Settings.from_env()
            app.state.pipeline = build_pipeline(settings)
            app.state.settings = settings
        else:
            app.state.pipeline = pipeline
            app.state.settings = None

        app.state.timeout = timeout
        app.state.config = {
            "provider": getattr(app.state.pipeline.client, "name", ""),
            "model": getattr(app.state.pipeline.client, "model", ""),
            "judge_model": getattr(app.state.pipeline.judge_client, "model", ""),
            "max_seconds": timeout,
        }
        try:
            yield
        finally:
            if owned:
                await _close(app.state.pipeline)

    app = FastAPI(title="research-agent", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text("utf-8"))

    @app.get("/api/config")
    async def config(request: Request) -> dict[str, Any]:
        return request.app.state.config

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health_alias() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/research")
    async def research(body: ResearchRequest, request: Request) -> StreamingResponse:
        question = " ".join(body.question.split())
        if len(question) < 8:
            raise HTTPException(422, "question must be at least 8 characters")
        if len(question) > 500:
            raise HTTPException(422, "question must be at most 500 characters")

        return StreamingResponse(
            stream_run(
                request.app.state.pipeline,
                question,
                timeout=request.app.state.timeout,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                # nginx buffers text/event-stream by default; turn it off.
                "X-Accel-Buffering": "no",
            },
        )

    return app


async def _close(pipeline: ResearchPipeline) -> None:
    client = getattr(pipeline, "client", None)
    judge = getattr(pipeline, "judge_client", None)
    seen: set[int] = set()
    for candidate in (client, judge):
        inner = getattr(candidate, "inner", candidate)
        if inner is None or id(inner) in seen:
            continue
        seen.add(id(inner))
        aclose = getattr(inner, "aclose", None)
        if aclose is not None:
            result = aclose()
            if asyncio.iscoroutine(result):
                await result


app = create_app()


if __name__ == "__main__":
    import logging

    import uvicorn

    # Without this, our INFO lines go to the root logger's last-resort handler
    # and disappear. Warnings/tracebacks (timeouts, failed runs) still surface.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("web.server:app", host="127.0.0.1", port=8000, reload=False)
