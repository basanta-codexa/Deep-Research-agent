"""Step 6 demo: plan once, then run one sub-agent per sub-question in parallel.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step6_subagents
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlsplit

from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.planning import Planner
from research_agent.subagent import ResearchBatch, SubAgentResult, ResearchOrchestrator
from research_agent.tools.web import make_subagent_tools

QUESTION = (
    "If asyncio.gather() gets one failing coroutine, what happens to the results "
    "I still care about, and how do I make sure nothing is silently lost?"
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def print_result(result: SubAgentResult) -> None:
    flag = "+" if result.ok else "x"
    print(
        f"\n[{flag}] {result.question[:78]}\n"
        f"    {result.elapsed_s:5.1f}s  {result.steps} steps  "
        f"{len(result.findings)} findings  {result.usage}"
    )
    if result.error:
        print(f"    ERROR: {result.error}")
    if result.answer:
        print(f"    answer: {result.answer[:240]}")
    for finding in result.findings:
        print(f"    - [{finding.confidence}] {finding.claim[:100]}")
        print(f"      \"{finding.quote[:110]}\"")
        print(f"      {finding.url}")
    for gap in result.gaps:
        print(f"    gap: {gap}")
    if result.ungrounded_urls:
        print(f"    !! cited but never read: {result.ungrounded_urls}")


def summarize(batch: ResearchBatch) -> None:
    section("Batch summary")
    sequential = sum(r.elapsed_s for r in batch.results)
    speedup = sequential / batch.wall_clock_s if batch.wall_clock_s else 0.0

    print(f"sub-agents        : {len(batch.results)}")
    print(f"concurrency       : {batch.concurrency}")
    print(f"sum of individual : {sequential:6.1f} s  (if run one by one)")
    print(f"wall clock        : {batch.wall_clock_s:6.1f} s  (actual)")
    print(f"speedup           : {speedup:6.2f}x")
    print(f"tokens            : {batch.usage}")
    print(f"hard failures     : {len(batch.hard_failures)}")

    findings = batch.findings
    urls = {f.url for f in findings}
    ungrounded = {u for r in batch.results for u in r.ungrounded_urls}
    domains = {urlsplit(u).netloc.lower().removeprefix("www.") for u in urls}

    print(f"\nfindings          : {len(findings)}")
    print(f"distinct sources  : {len(urls)} across {len(domains)} domains")
    print(f"domains           : {sorted(domains)}")
    print(f"ungrounded cites  : {len(ungrounded)} {sorted(ungrounded) if ungrounded else ''}")

    print("\nper-agent coverage:")
    for result in batch.results:
        print(
            f"  {result.steps} steps  {len(result.findings)} findings  "
            f"{len(result.gaps)} gaps  {result.question[:60]}"
        )


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    print(settings.safe_summary())

    section("1. Plan")
    plan, prompt_tokens, completion_tokens = await Planner(
        client, max_tokens=1200
    ).plan(QUESTION)
    print(f"restated: {plan.restated}")
    for i, sq in enumerate(plan.sub_questions, 1):
        print(f"[{i}] {sq.question}")
        print(f"    query: {sq.search_query}")
    print(f"\nplanner tokens: {prompt_tokens} in / {completion_tokens} out")

    section("2. Sub-agents (results print as they finish, not in plan order)")
    orchestrator = ResearchOrchestrator(
        client,
        make_subagent_tools(settings),
        concurrency=2,
        max_steps=3,
        max_tokens=700,
        text_budget=2600,
    )
    batch = await orchestrator.run(plan.sub_questions, on_result=print_result)

    summarize(batch)
    print("\nNext: step 7 turns these findings into one shared evidence store,")
    print("deduplicated by URL+claim, with the quote's position in the page kept")
    print("so step 9 can re-open the source and verify the quote is real.")


if __name__ == "__main__":
    asyncio.run(main())
