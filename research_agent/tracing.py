"""Spans: where the seconds and the tokens actually went.

A report tells you *what* the agent concluded. A trace tells you *how it got
there*: which stage was slow, which model burned the budget, which tool returned
a 50 KB page, whether the 40-second request was one call or six retries.

Two design decisions carry this file:

**1. Spans nest through a `ContextVar`, not through arguments.**
Threading `tracer=` through `Planner`, `SubAgent`, `Agent`, `ReportWriter` and
every helper is a tax on every signature, and a tax people stop paying halfway.
`current_span` lives in a context variable, so `with span(...)` attaches to the
right parent automatically. Asyncio copies the context when it creates a task,
which is exactly the semantics we need: four concurrent sub-agents each see the
"research" span as their parent and never see each other.

**2. The trace is data first, picture second.**
`to_dict()` is the artifact (`trace.json`); `to_html()` is a rendering of the
same dict. A viewer that owns the only copy of the data is a viewer you cannot
query six months later.

Usage is attributed to **LLM spans only**, then rolled up to the nearest stage.
Summing every span would double-count: a stage's tokens are its children's
tokens, and the stage span itself never called a model.
"""

from __future__ import annotations

import html
import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .llm import LLMClient, LLMResponse, Message, Usage
from .pricing import apply_cost

# --------------------------------------------------------------------------- #
# current tracer / current span
# --------------------------------------------------------------------------- #
_CURRENT: ContextVar["Tracer | None"] = ContextVar("current_tracer", default=None)


def current_tracer() -> "Tracer | None":
    return _CURRENT.get()


@contextmanager
def span(
    name: str, kind: str = "stage", **attributes: Any
) -> Iterator["Span | None"]:
    """Open a span if a trace is active, otherwise do nothing.

    Instrumentation must be free when tracing is off: a tool registry should not
    need to know whether anyone is watching.
    """
    tracer = _CURRENT.get()
    if tracer is None:
        yield None
        return
    with tracer.span(name, kind=kind, **attributes) as item:
        yield item


# --------------------------------------------------------------------------- #
# data model
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Span:
    id: str
    name: str
    kind: str  # pipeline | stage | subagent | llm | tool
    start_ms: float
    parent_id: str | None = None
    end_ms: float | None = None
    status: str = "ok"  # ok | error
    error: str | None = None
    model: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)

    @property
    def duration_ms(self) -> float:
        if self.end_ms is None:
            return 0.0
        return max(0.0, self.end_ms - self.start_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "model": self.model,
            "attributes": self.attributes,
            "usage": {
                "prompt": self.usage.prompt_tokens,
                "completion": self.usage.completion_tokens,
                "total": self.usage.total_tokens,
                "cost_usd": round(self.usage.cost_usd, 8),
            },
        }


# Called on every span start and end. Used by the live web UI to stream a run
# without knowing anything about the pipeline's internals.
SpanListener = Callable[[str, Span], None]


# --------------------------------------------------------------------------- #
# tracer
# --------------------------------------------------------------------------- #
class Tracer:
    """Collects spans for one run and turns them into JSON and HTML."""

    def __init__(
        self,
        name: str = "run",
        attributes: dict[str, Any] | None = None,
        listeners: Sequence[SpanListener] | None = None,
    ) -> None:
        self.trace_id = uuid.uuid4().hex[:12]
        self.name = name
        self.attributes = dict(attributes or {})
        self.started_at = datetime.now(timezone.utc)
        self.spans: list[Span] = []
        self._listeners: list[SpanListener] = list(listeners or ())
        self._t0 = time.perf_counter()
        self._stack: ContextVar[tuple[Span, ...]] = ContextVar(
            f"span_stack_{self.trace_id}", default=()
        )

    def add_listener(self, listener: SpanListener) -> None:
        self._listeners.append(listener)

    def _notify(self, phase: str, item: Span) -> None:
        """Broadcast without letting a bad listener kill the run.

        Observability must never be able to break the thing it observes.
        """
        for listener in self._listeners:
            try:
                listener(phase, item)
            except Exception:
                pass

    # -- lifecycle ------------------------------------------------------ #
    def now_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0

    @contextmanager
    def activate(self) -> Iterator["Tracer"]:
        """Make this the tracer that bare `span()` calls attach to."""
        token = _CURRENT.set(self)
        try:
            yield self
        finally:
            _CURRENT.reset(token)

    def current_span(self) -> Span | None:
        stack = self._stack.get()
        return stack[-1] if stack else None

    @contextmanager
    def span(
        self, name: str, kind: str = "stage", **attributes: Any
    ) -> Iterator[Span]:
        parent = self.current_span()
        item = Span(
            id=uuid.uuid4().hex[:8],
            name=name,
            kind=kind,
            parent_id=parent.id if parent else None,
            start_ms=self.now_ms(),
            attributes=dict(attributes),
        )
        self.spans.append(item)
        token = self._stack.set(self._stack.get() + (item,))
        self._notify("start", item)
        try:
            yield item
        except BaseException as exc:  # cancellation is an error for this span
            item.status = "error"
            item.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            item.end_ms = self.now_ms()
            self._notify("end", item)
            self._stack.reset(token)

    # -- aggregation ---------------------------------------------------- #
    def llm_spans(self) -> list[Span]:
        return [item for item in self.spans if item.kind == "llm"]

    def usage(self) -> Usage:
        total = Usage()
        for item in self.llm_spans():
            total += item.usage
        return total

    def _stage_name(self, item: Span, by_id: dict[str, Span]) -> str:
        current = item.parent_id
        while current is not None:
            parent = by_id.get(current)
            if parent is None:
                return "other"
            if parent.kind in {"stage", "pipeline"}:
                return parent.name
            current = parent.parent_id
        return "other"

    def summary(self) -> dict[str, Any]:
        by_id = {item.id: item for item in self.spans}
        llm = self.llm_spans()
        tools = [item for item in self.spans if item.kind == "tool"]
        usage = self.usage()

        by_model: dict[str, dict[str, Any]] = {}
        unpriced: set[str] = set()
        for item in llm:
            model = item.model or "unknown"
            row = by_model.setdefault(
                model,
                {
                    "calls": 0,
                    "prompt": 0,
                    "completion": 0,
                    "total": 0,
                    "cost_usd": 0.0,
                    "priced": True,
                    "duration_ms": 0.0,
                },
            )
            row["calls"] += 1
            row["prompt"] += item.usage.prompt_tokens
            row["completion"] += item.usage.completion_tokens
            row["total"] += item.usage.total_tokens
            row["cost_usd"] += item.usage.cost_usd
            row["duration_ms"] += item.duration_ms
            if not item.attributes.get("priced", True):
                row["priced"] = False
                unpriced.add(model)
        for row in by_model.values():
            row["cost_usd"] = round(row["cost_usd"], 8)
            row["duration_ms"] = round(row["duration_ms"], 1)

        by_stage: dict[str, dict[str, Any]] = {}
        for item in llm:
            stage = self._stage_name(item, by_id)
            row = by_stage.setdefault(
                stage,
                {"calls": 0, "prompt": 0, "completion": 0, "total": 0, "cost_usd": 0.0},
            )
            row["calls"] += 1
            row["prompt"] += item.usage.prompt_tokens
            row["completion"] += item.usage.completion_tokens
            row["total"] += item.usage.total_tokens
            row["cost_usd"] += item.usage.cost_usd
        for row in by_stage.values():
            row["cost_usd"] = round(row["cost_usd"], 8)

        by_kind: dict[str, dict[str, Any]] = {}
        for item in self.spans:
            row = by_kind.setdefault(
                item.kind, {"count": 0, "duration_ms": 0.0, "errors": 0}
            )
            row["count"] += 1
            row["duration_ms"] += item.duration_ms
            if item.status == "error":
                row["errors"] += 1
        for row in by_kind.values():
            row["duration_ms"] = round(row["duration_ms"], 1)

        slowest = sorted(llm, key=lambda item: item.duration_ms, reverse=True)[:5]

        return {
            "duration_ms": round(self.now_ms(), 1),
            "span_count": len(self.spans),
            "llm_calls": len(llm),
            "tool_calls": len(tools),
            "errors": sum(1 for item in self.spans if item.status == "error"),
            "tokens": {
                "prompt": usage.prompt_tokens,
                "completion": usage.completion_tokens,
                "total": usage.total_tokens,
            },
            # None, not 0.0: a total that silently drops unpriced calls is a lie.
            "cost_usd": None if unpriced else round(usage.cost_usd, 8),
            "unpriced_models": sorted(unpriced),
            "by_model": by_model,
            "by_stage": by_stage,
            "by_kind": by_kind,
            "slowest": [
                {
                    "name": item.name,
                    "kind": item.kind,
                    "model": item.model,
                    "duration_ms": round(item.duration_ms, 1),
                }
                for item in slowest
            ],
            "critical_path": [
                {
                    "id": item.id,
                    "name": item.name,
                    "kind": item.kind,
                    "duration_ms": round(item.duration_ms, 1),
                }
                for item in self.critical_path()
            ],
        }

    def critical_path(self) -> list[Span]:
        """The chain of spans that determines the wall clock.

        With parallel sub-agents the answer is not "the slowest call", it is the
        slowest *chain*. At each level, follow the child that ends last.
        """
        children: dict[str | None, list[Span]] = {}
        for item in self.spans:
            children.setdefault(item.parent_id, []).append(item)
        roots = children.get(None, [])
        if not roots:
            return []
        current = max(roots, key=lambda item: item.end_ms or 0.0)
        path = [current]
        while children.get(current.id):
            current = max(children[current.id], key=lambda item: item.end_ms or 0.0)
            path.append(current)
        return path

    # -- export --------------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "attributes": self.attributes,
            "spans": [
                item.to_dict()
                for item in sorted(self.spans, key=lambda item: item.start_ms)
            ],
            "summary": self.summary(),
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    def save_html(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html(), encoding="utf-8")
        return path

    # -- rendering ------------------------------------------------------ #
    def to_html(self) -> str:
        data = self.to_dict()
        summary = data["summary"]
        spans = data["spans"]

        end_ms = max((item["start_ms"] + item["duration_ms"] for item in spans), default=0.0)
        # Normalise to the earliest span: the tracer is created a hair before the
        # root span opens, and a waterfall that starts at 1% looks broken.
        origin = min((item["start_ms"] for item in spans), default=0.0)
        total = max(end_ms - origin, 1.0)
        by_id = {item["id"]: item for item in spans}

        def depth_of(item: dict[str, Any]) -> int:
            depth = 0
            parent = item.get("parent_id")
            seen: set[str] = set()
            while parent is not None and parent in by_id and parent not in seen:
                seen.add(parent)
                depth += 1
                parent = by_id[parent].get("parent_id")
            return depth

        rows: list[str] = []
        for item in spans:
            depth = depth_of(item)
            left = (item["start_ms"] - origin) / total * 100
            width = max(item["duration_ms"] / total * 100, 0.25)
            label = html.escape(item["name"])
            raw_model = item.get("model") or ""
            model = html.escape(raw_model) if raw_model else ""
            tokens = item["usage"]["total"]
            bits = [
                f"{item['duration_ms']:.0f} ms",
                f"{tokens:,} tok" if tokens else "",
            ]
            attributes = item.get("attributes") or {}
            title = " · ".join(
                part
                for part in [
                    item["kind"],
                    raw_model,
                    item.get("error") or "",
                    json.dumps(attributes, ensure_ascii=False)[:300] if attributes else "",
                ]
                if part
            )
            rows.append(
                f'<div class="row k-{html.escape(item["kind"])}'
                f'{" is-error" if item["status"] == "error" else ""}">'
                f'<div class="label" style="padding-left:{depth * 14}px" title="{html.escape(title)}">'
                f"{label}"
                + (f'<span class="model">{model}</span>' if model else "")
                + "</div>"
                f'<div class="track"><div class="bar" style="left:{left:.3f}%;'
                f'width:{width:.3f}%"></div></div>'
                f'<div class="ms">{" · ".join(b for b in bits if b)}</div>'
                "</div>"
            )

        def stage_rows() -> str:
            out = []
            for stage, row in sorted(
                summary["by_stage"].items(), key=lambda kv: -kv[1]["total"]
            ):
                out.append(
                    "<tr>"
                    f"<td>{html.escape(stage)}</td>"
                    f"<td>{row['calls']}</td>"
                    f"<td>{row['prompt']:,}</td>"
                    f"<td>{row['completion']:,}</td>"
                    f"<td>{row['total']:,}</td>"
                    f"<td>{money(row['cost_usd'])}</td>"
                    "</tr>"
                )
            return "".join(out) or '<tr><td colspan="6">no calls</td></tr>'

        def model_rows() -> str:
            out = []
            for model, row in sorted(
                summary["by_model"].items(), key=lambda kv: -kv[1]["total"]
            ):
                flag = "" if row["priced"] else " (unpriced)"
                out.append(
                    "<tr>"
                    f"<td>{html.escape(model)}{flag}</td>"
                    f"<td>{row['calls']}</td>"
                    f"<td>{row['prompt']:,}</td>"
                    f"<td>{row['completion']:,}</td>"
                    f"<td>{row['total']:,}</td>"
                    f"<td>{money(row['cost_usd']) if row['priced'] else 'n/a'}</td>"
                    "</tr>"
                )
            return "".join(out) or '<tr><td colspan="6">no calls</td></tr>'

        slowest = "".join(
            "<div>"
            + html.escape(item["name"])
            + (f" · {html.escape(item['model'])}" if item.get("model") else "")
            + f" — {item['duration_ms'] / 1000:.2f}s</div>"
            for item in summary["slowest"]
        ) or "<div>—</div>"
        critical = " → ".join(
            html.escape(item["name"]) for item in summary["critical_path"]
        ) or "—"
        errors = summary["errors"]

        cost = money(summary["cost_usd"]) if summary["cost_usd"] is not None else "n/a"
        unpriced = ""
        if summary["unpriced_models"]:
            unpriced = (
                '<p class="warn">unpriced models: '
                + html.escape(", ".join(summary["unpriced_models"]))
                + "</p>"
            )

        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>trace · {html.escape(self.name)[:80]}</title>
<style>
:root {{
  --ink:#1f2933; --muted:#6b7785; --line:#e4e7eb; --bg:#f8f9fb;
  --stage:#4c6ef5; --llm:#12b886; --tool:#f59f00; --subagent:#7950f2; --pipeline:#343a40;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:32px; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
h2 {{ font-size:15px; margin:28px 0 10px; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.meta {{ color:var(--muted); margin:0; font-size:13px; }}
.tiles {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:20px; }}
.tile {{ background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:10px 16px; min-width:120px; }}
.tile span {{ display:block; font-size:11px; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.tile strong {{ font-size:18px; font-weight:600; }}
.panel {{ background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; }}
.row {{ display:grid; grid-template-columns:360px 1fr 130px; gap:12px;
  align-items:center; padding:2px 0; font-size:13px; }}
.row.head {{ color:var(--muted); font-size:11px; text-transform:uppercase;
  letter-spacing:.06em; border-bottom:1px solid var(--line); padding-bottom:6px;
  margin-bottom:6px; }}
.label {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.model {{ color:var(--muted); margin-left:8px; font-size:11px; }}
.track {{ position:relative; height:14px; background:#eef1f4; border-radius:4px; }}
.bar {{ position:absolute; top:0; bottom:0; border-radius:4px; background:#adb5bd; }}
.k-pipeline .bar {{ background:var(--pipeline); }}
.k-stage .bar {{ background:var(--stage); }}
.k-subagent .bar {{ background:var(--subagent); }}
.k-llm .bar {{ background:var(--llm); }}
.k-tool .bar {{ background:var(--tool); }}
.is-error .bar {{ background:#e03131; }}
.is-error .label {{ color:#c92a2a; }}
.ms {{ color:var(--muted); text-align:right; font-variant-numeric:tabular-nums; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:right; padding:6px 8px; border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums; }}
th:first-child, td:first-child {{ text-align:left; }}
th {{ color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase;
  letter-spacing:.06em; }}
.legend {{ display:flex; gap:16px; flex-wrap:wrap; margin:10px 0 0; font-size:12px;
  color:var(--muted); }}
.swatch {{ display:inline-block; width:10px; height:10px; border-radius:3px;
  margin-right:6px; vertical-align:middle; }}
.note {{ color:var(--muted); font-size:12px; }}
.warn {{ color:#c92a2a; font-size:12px; margin:8px 0 0; }}
code {{ background:#eef1f4; padding:1px 5px; border-radius:4px; font-size:12px; }}
</style>
</head>
<body>
<h1>{html.escape(self.name)}</h1>
<p class="meta">trace {html.escape(self.trace_id)} · {html.escape(self.started_at.strftime("%Y-%m-%d %H:%M:%S UTC"))} · {len(spans)} spans</p>
<section class="tiles">
  <div class="tile"><span>wall clock</span><strong>{summary['duration_ms'] / 1000:.1f}s</strong></div>
  <div class="tile"><span>llm calls</span><strong>{summary['llm_calls']}</strong></div>
  <div class="tile"><span>tool calls</span><strong>{summary['tool_calls']}</strong></div>
  <div class="tile"><span>tokens</span><strong>{summary['tokens']['total']:,}</strong></div>
  <div class="tile"><span>cost</span><strong>{cost}</strong></div>
  <div class="tile"><span>errors</span><strong>{errors}</strong></div>
</section>
{unpriced}
<h2>Waterfall</h2>
<div class="panel">
  <div class="row head"><div>span</div><div>timeline</div><div>duration</div></div>
  {''.join(rows)}
  <div class="legend">
    <span><i class="swatch" style="background:var(--pipeline)"></i>pipeline</span>
    <span><i class="swatch" style="background:var(--stage)"></i>stage</span>
    <span><i class="swatch" style="background:var(--subagent)"></i>sub-agent</span>
    <span><i class="swatch" style="background:var(--llm)"></i>llm call</span>
    <span><i class="swatch" style="background:var(--tool)"></i>tool</span>
  </div>
</div>
<h2>Where the tokens went</h2>
<div class="panel"><table>
  <tr><th>stage</th><th>calls</th><th>in</th><th>out</th><th>total</th><th>cost</th></tr>
  {stage_rows()}
</table></div>
<h2>By model</h2>
<div class="panel"><table>
  <tr><th>model</th><th>calls</th><th>in</th><th>out</th><th>total</th><th>cost</th></tr>
  {model_rows()}
</table></div>
<h2>Attribution</h2>
<div class="panel">
  <p><strong>Critical path:</strong> {critical}</p>
  <p><strong>Slowest calls</strong></p>
  {slowest}
  <p class="note">Critical path follows the child that ends last at each level — with
  parallel sub-agents, the long pole is a chain, not a single call. Per-call
  latency includes transport retries (429 backoff shows up here).</p>
</div>
<script type="application/json" id="trace-data">{payload}</script>
</body>
</html>
"""


def money(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value == 0:
        return "$0.0000"
    if abs(value) < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


# --------------------------------------------------------------------------- #
# LLM client wrapper
# --------------------------------------------------------------------------- #
class TraceLLMClient(LLMClient):
    """Wraps any client and records one span per logical call.

    Wrapping the *client* rather than each caller is what makes this cheap:
    planner, reader, extractor, judge and writer all go through `chat`, so they
    are traced without a single line of instrumentation in those modules.
    """

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model

    async def chat(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        with span(
            "llm",
            kind="llm",
            model=self.model,
            messages=len(messages),
            tools=len(tools) if tools else 0,
            json_mode=json_mode,
            max_tokens=max_tokens,
        ) as item:
            response = await self.inner.chat(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            usage, priced = apply_cost(
                self.name, response.model or self.model, response.usage
            )
            if item is not None:
                item.usage = usage
                item.model = response.model or self.model
                item.attributes.update(
                    {
                        "finish_reason": response.finish_reason,
                        "truncated": response.truncated,
                        "latency_ms": round(response.latency_ms, 1),
                        "priced": priced,
                    }
                )
            return response

    async def aclose(self) -> None:
        await self.inner.aclose()
