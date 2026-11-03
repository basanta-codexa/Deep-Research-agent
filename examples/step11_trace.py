"""Step 11 demo: where did the seconds and the tokens go?

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step11_trace

Runs one question through the full pipeline, prints the attribution tables, and
writes a trace you can open:

    reports/trace.json    the data (spans, parent ids, usage, cost)
    reports/trace.html    a self-contained waterfall — double-click it
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.pipeline import PipelineConfig, ResearchPipeline
from research_agent.retrieval.cache import Cache
from research_agent.tools.web import make_subagent_tools

QUESTION = (
    "Why is time.perf_counter() the right clock for measuring elapsed time, and "
    "when does time.time() mislead you?"
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    judge_client = create_client(settings.judge_settings())
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)

    print(settings.safe_summary())
    pipeline = ResearchPipeline(
        client,
        make_subagent_tools(settings, cache=cache),
        judge_client=judge_client,
        config=PipelineConfig(concurrency=2, max_steps=3),
    )

    section("1. Run, with stages")
    result = await pipeline.run(
        QUESTION, on_stage=lambda name, state: print(f"  {name:<9} {state}")
    )
    if result.trace is None:
        print("no trace: the pipeline did not start")
        return

    section("2. Where the time went")
    summary = result.trace.summary()
    print(f"  wall clock : {summary['duration_ms'] / 1000:.1f}s")
    print(f"  llm calls  : {summary['llm_calls']}")
    print(f"  tool calls : {summary['tool_calls']}")
    print(f"  tokens     : {summary['tokens']['prompt']:,} in / "
          f"{summary['tokens']['completion']:,} out / "
          f"{summary['tokens']['total']:,} total")
    cost = summary["cost_usd"]
    print(f"  cost       : {'n/a (unpriced)' if cost is None else f'${cost:.4f}'}")
    if summary["unpriced_models"]:
        print(f"  unpriced   : {', '.join(summary['unpriced_models'])}")

    section("3. Where the tokens went")
    for stage, row in sorted(
        summary["by_stage"].items(), key=lambda pair: -pair[1]["total"]
    ):
        print(
            f"  {stage:<12} {row['calls']:>2} calls  "
            f"{row['prompt']:>7,} in  {row['completion']:>6,} out  "
            f"{row['total']:>7,} total"
        )

    section("4. The long pole")
    print("  critical path:")
    for span in result.trace.critical_path():
        model = f"  [{span.model}]" if span.model else ""
        print(f"    {span.duration_ms / 1000:>7.2f}s  {span.kind:<9} {span.name}{model}")
    print("\n  slowest calls:")
    for call in summary["slowest"]:
        print(f"    {call['duration_ms'] / 1000:>7.2f}s  {call['name']} "
              f"({call['model'] or 'no model'})")

    section("5. Publish")
    out = Path("reports")
    out.mkdir(exist_ok=True)
    trace_json = result.trace.save(out / "trace.json")
    trace_html = result.trace.save_html(out / "trace.html")
    print(f"  {trace_json}")
    print(f"  {trace_html}   <- open this")


if __name__ == "__main__":
    asyncio.run(main())
