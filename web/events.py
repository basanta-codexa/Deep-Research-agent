"""Server-sent events for one research run.

The pipeline already emits spans (step 11). Rather than threading a second set
of callbacks through planning, research, tools and writing, the web layer
*subscribes to the tracer*: every span start/end becomes an SSE event, and the
stage attributes added in ``pipeline.py`` carry the human-readable summaries.

Transport choice: SSE over WebSocket. The client sends one question and then
only listens, so a one-way stream is the right shape — it survives proxies,
reconnects with plain HTTP semantics, and needs no handshake library.

Wire format (one JSON object per ``data:`` line)::

    event: start   {"type":"start","question":...}
    event: span    {"type":"span","phase":"start|end","span":{...}}
    event: report  {"type":"report","data":<payload>}
    event: error   {"type":"error","message":...}
    event: done    {"type":"done","ok":true|false}

The generator has exactly one consumer loop and two sentinels (result/error)
pushed by the runner task. That avoids the classic "is the queue empty because
the run finished or because it is thinking?" race.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from research_agent.pipeline import ResearchPipeline
from research_agent.tracing import Span, Tracer

from .payload import build_payload

DEFAULT_TIMEOUT_S = 360.0


def sse(payload: dict[str, Any]) -> str:
    return (
        f"event: {payload['type']}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
    )


def span_payload(item: Span, phase: str) -> dict[str, Any]:
    attributes = json.loads(json.dumps(item.attributes, default=str))
    return {
        "type": "span",
        "id": item.id,
        "parent_id": item.parent_id,
        "name": item.name[:90],
        "kind": item.kind,
        "phase": phase,
        "start_ms": round(item.start_ms, 1),
        "duration_ms": round(item.duration_ms, 1) if phase == "end" else None,
        "status": item.status,
        "error": item.error,
        "model": item.model,
        "tokens": item.usage.total_tokens if phase == "end" else 0,
        "attributes": attributes,
    }


async def stream_run(
    pipeline: ResearchPipeline,
    question: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def listener(phase: str, item: Span) -> None:
        # Sync, allocation-light and non-blocking: listeners run inside the
        # event loop, sometimes on several sub-agent tasks at once.
        queue.put_nowait(("span", span_payload(item, phase)))

    tracer = Tracer(question[:120], listeners=[listener])
    started = time.perf_counter()

    async def execute() -> None:
        try:
            result = await pipeline.run(question, tracer=tracer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pipeline.run normally swallows these
            queue.put_nowait(("error", exc))
        else:
            queue.put_nowait(("result", result))

    yield sse(
        {
            "type": "start",
            "question": question,
            "trace_id": tracer.trace_id,
            "model": tracer.attributes.get("model", ""),
        }
    )

    result = None
    timed_out = False
    # Created only after the first frame is sent: a client that disconnects
    # during the handshake must not leave a run burning tokens in the
    # background.
    runner = asyncio.create_task(execute())
    try:
        while True:
            remaining = timeout - (time.perf_counter() - started)
            if remaining <= 0:
                timed_out = True
                break
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=min(15.0, remaining)
                )
            except asyncio.TimeoutError:
                # A single slow model call can exceed a proxy's idle timeout.
                # Comment frames keep the connection warm; the client ignores
                # frames without a data line.
                if timeout - (time.perf_counter() - started) <= 0:
                    timed_out = True
                    break
                yield ": keep-alive\n\n"
                continue

            if kind == "span":
                yield sse(payload)
                continue
            if kind == "error":
                yield sse(
                    {
                        "type": "error",
                        "message": f"{type(payload).__name__}: {payload}",
                        "trace": tracer.summary(),
                    }
                )
                yield sse({"type": "done", "ok": False})
                return
            result = payload
            break
    finally:
        if not runner.done():
            runner.cancel()
            try:
                await runner
            except (asyncio.CancelledError, Exception):
                pass

    if timed_out:
        yield sse(
            {
                "type": "error",
                "message": f"run exceeded {timeout:.0f}s and was cancelled",
                # Partial trace, so a timeout is diagnosable from the browser.
                "trace": tracer.summary(),
            }
        )
        yield sse({"type": "done", "ok": False})
        return

    if result is None or result.report is None:
        message = (
            result.error if result is not None and result.error else "no report produced"
        )
        yield sse(
            {
                "type": "error",
                "message": message,
                "stage_errors": result.stage_errors if result is not None else {},
                "trace": tracer.summary(),
            }
        )
        yield sse({"type": "done", "ok": False})
        return

    try:
        payload = build_payload(result)
    except Exception as exc:
        yield sse(
            {"type": "error", "message": f"could not build report: {exc}"}
        )
        yield sse({"type": "done", "ok": False})
        return

    yield sse({"type": "report", "data": payload})
    yield sse({"type": "done", "ok": True})
