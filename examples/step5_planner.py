"""Step 5 demo: plan first, then measure whether the plan buys coverage.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step5_planner

Uses whatever provider is configured in .env (groq by default here).
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlsplit

from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.planning import Planner, Plan
from research_agent.retrieval import Cache, DuckDuckGoBackend, fetch
from research_agent.retrieval.search import CachedSearch, SearchResult

QUESTION = (
    "If asyncio.gather() gets one failing coroutine, what happens to the results "
    "I still care about, and how do I make sure nothing is silently lost?"
)
NAIVE_QUERY = "asyncio.gather exception behavior"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


def domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def show_plan(plan: Plan) -> None:
    print(f"restated   : {plan.restated}")
    for note in plan.assumptions:
        print(f"assumes    : {note}")
    print()
    for i, sq in enumerate(plan.sub_questions, 1):
        print(f"[{i}] {sq.question}")
        print(f"    query : {sq.search_query}")
        print(f"    why   : {sq.why}")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    backend = CachedSearch(DuckDuckGoBackend(settings.request_timeout), cache)

    print(settings.safe_summary())

    # ---------------------------------------------------------------- #
    section("1. Plan")
    planner = Planner(client, max_tokens=1200)
    try:
        plan, prompt_tokens, completion_tokens = await planner.plan(QUESTION)
    finally:
        await client.aclose()

    show_plan(plan)
    print(
        f"\nplan cost: {prompt_tokens} in / {completion_tokens} out tokens, "
        f"{len(plan.sub_questions)} sub-questions"
    )

    # ---------------------------------------------------------------- #
    section("2. Coverage: does one query find the same sources as the plan?")
    baseline = await backend.search(NAIVE_QUERY, 5)
    baseline_domains = {domain(r.url) for r in baseline}

    planned: dict[str, list[SearchResult]] = {}
    for sq in plan.sub_questions:
        planned[sq.search_query] = await backend.search(sq.search_query, 4)

    planned_results = [r for rows in planned.values() for r in rows]
    planned_domains = {domain(r.url) for r in planned_results}

    print(f"naive single query : {len(baseline):2d} results, "
          f"{len(baseline_domains):2d} unique domains  ({NAIVE_QUERY!r})")
    print(f"planned queries    : {len(planned_results):2d} results, "
          f"{len(planned_domains):2d} unique domains  ({len(plan.sub_questions)} queries)")
    print(f"domains only the plan found: {sorted(planned_domains - baseline_domains)}")
    print(f"domains both found        : {sorted(planned_domains & baseline_domains)}")

    for query, rows in planned.items():
        print(f"\n  {query!r}")
        for r in rows[:3]:
            print(f"    - {r.title[:70]}")
            print(f"      {r.url}")

    # ---------------------------------------------------------------- #
    section("3. What the plan actually retrieves (one page per sub-question)")
    seen: set[str] = set()
    total_chars = 0
    for sq in plan.sub_questions:
        rows = planned[sq.search_query]
        if not rows:
            print(f"\n  {sq.search_query!r}: no results")
            continue
        target = next((r for r in rows if r.url not in seen), rows[0])
        seen.add(target.url)
        print(f"\n  sub-question: {sq.question}")
        print(f"  fetching    : {target.url}")
        try:
            doc = await fetch(target.url, cache=cache, timeout=settings.request_timeout)
        except Exception as exc:
            print(f"  FAILED      : {exc}")
            continue
        total_chars += len(doc.text)
        print(f"  title       : {doc.title[:70]}")
        print(f"  chars       : {len(doc.text):,}")
        print(f"  excerpt     : {doc.text[:240].replace(chr(10), ' ')}...")

    print(f"\nraw evidence gathered: {len(seen)} pages, {total_chars:,} chars")
    print("step 6 reads these in PARALLEL sub-agents; step 7 compresses them to")
    print("claims + quotes so they fit in context without losing the good parts.")


if __name__ == "__main__":
    asyncio.run(main())
