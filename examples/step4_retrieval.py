"""Step 4 demo: search, fetch, extract, cache, SSRF guard, then the agent.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step4_retrieval

Parts 1-5 hit the network once each; part 6 runs the real agent.
"""

from __future__ import annotations

import asyncio
import sys

from research_agent.agent import Agent, Step
from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.retrieval import Cache, DuckDuckGoBackend, FetchError, fetch
from research_agent.retrieval.search import CachedSearch
from research_agent.tools.builtin import calculator
from research_agent.tools.registry import ToolRegistry
from research_agent.tools.web import make_web_tools

QUERY = "asyncio.gather python documentation"
QUESTION = (
    "Using web_search and fetch_page: what does asyncio.gather do, and what "
    "happens to exceptions by default? Answer in 3 sentences and cite the URL."
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def print_step(step: Step) -> None:
    print(f"\n-- step {step.index} -- ({step.latency_ms:.0f} ms)")
    if step.text.strip():
        print(f"   think : {step.text.strip()[:220]}")
    for call in step.tool_calls:
        args = str(call.arguments)
        print(f"   call  : {call.name}({args[:120]})")
    for _, output in step.tool_outputs:
        flat = " ".join(output.split())
        print(f"   result: {flat[:260]}")
    if not step.tool_calls:
        print("   (no tool call -> final answer)")


async def main() -> None:
    settings = Settings.from_env()
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    backend = CachedSearch(DuckDuckGoBackend(settings.request_timeout), cache)

    # ---------------------------------------------------------------- #
    section("1. Search returns structured results, not text")
    started = asyncio.get_running_loop().time()
    results = await backend.search(QUERY, 3)
    elapsed = (asyncio.get_running_loop().time() - started) * 1000
    print(f"backend={backend.name}  query={QUERY!r}  ({elapsed:.0f} ms)\n")
    for r in results:
        print(f"[{r.rank}] {r.title}")
        print(f"    {r.url}")
        print(f"    {r.snippet[:140]}")

    if not results:
        print("no results; aborting")
        return

    target = results[0].url

    # ---------------------------------------------------------------- #
    section("2. Fetch + extract readable text")
    doc = await fetch(target, cache=cache, timeout=settings.request_timeout)
    print(f"url        : {doc.final_url}")
    print(f"title      : {doc.title}")
    print(f"content    : {doc.content_type}  status={doc.status}")
    print(f"text chars : {len(doc.text):,}")
    print(f"fetch time : {doc.elapsed_ms:.0f} ms")
    print("\nfirst 600 chars of extracted text:")
    print(doc.text[:600])

    # ---------------------------------------------------------------- #
    section("3. Second fetch of the same URL is free")
    again = await fetch(target, cache=cache, timeout=settings.request_timeout)
    print(f"from_cache : {again.from_cache}")
    print(f"fetch time : {again.elapsed_ms:.0f} ms")
    print(f"identical  : {again.text == doc.text}")
    print(f"cache stats: {cache.stats()}")

    # ---------------------------------------------------------------- #
    section("4. SSRF guard: the model picks the URL, so we validate it")
    for bad in [
        "http://localhost:11434/api/tags",
        "http://169.254.169.254/latest/meta-data/",
        "file:///C:/Windows/win.ini",
        "http://10.0.0.5/admin",
    ]:
        try:
            await fetch(bad, timeout=5)
            print(f"  {bad:<46} UNEXPECTEDLY ALLOWED")
        except FetchError as exc:
            print(f"  {bad:<46} blocked: {exc}")

    # ---------------------------------------------------------------- #
    section("5. What the model sees when a fetch fails")
    registry = ToolRegistry([*make_web_tools(settings, cache=cache), calculator])
    print(await registry.execute("fetch_page", {"url": "http://127.0.0.1:8080/"}))
    print(await registry.execute("web_search", {"query": "x"}))  # too short

    # ---------------------------------------------------------------- #
    section("6. The agent, with real retrieval")
    client = create_client(settings)
    agent = Agent(client, registry, max_steps=4, max_tokens=300, on_step=print_step)
    print(f"provider={client.name}  model={client.model}  num_ctx={settings.num_ctx}")
    print(f"question: {QUESTION}")
    try:
        result = await agent.run(QUESTION)
    finally:
        await client.aclose()

    print(f"\nanswer     : {result.answer or '(empty)'}")
    print(f"stopped    : {result.stopped}   steps: {len(result.steps)}")
    print(f"tokens     : {result.usage}")
    print(f"wall clock : {result.elapsed_s:.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
