"""Step 7 demo: turn a pile of findings into a verifiable evidence store.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step7_evidence

Costs about 4 sub-agent runs (~70s). Writes reports/evidence.json and .md.
"""

from __future__ import annotations

import asyncio
import sys

from research_agent.config import Settings
from research_agent.evidence import EvidenceStore
from research_agent.llm import create_client
from research_agent.planning import Planner
from research_agent.retrieval.cache import Cache
from research_agent.subagent import ResearchOrchestrator
from research_agent.tools.web import make_subagent_tools

QUESTION = (
    "If asyncio.gather() gets one failing coroutine, what happens to the results "
    "I still care about, and how do I make sure nothing is silently lost?"
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    print(settings.safe_summary())

    section("1. Collect (plan + parallel sub-agents)")
    plan, _, _ = await Planner(client, max_tokens=1200).plan(QUESTION)
    # One cache instance, shared by the tools and by the verifier below.
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    batch = await ResearchOrchestrator(
        client,
        make_subagent_tools(settings, cache=cache),
        concurrency=2,
        max_steps=3,
    ).run(plan.sub_questions)

    print(f"sub-agents: {len(batch.results)}   findings: {len(batch.findings)}   "
          f"wall clock: {batch.wall_clock_s:.1f}s   tokens: {batch.usage}")
    for result in batch.results:
        print(f"  {len(result.findings):2d} findings  {len(result.gaps):2d} gaps  "
              f"{result.question[:66]}")

    section("2. Store: deduplicate, locate, verify")
    urls = sorted({url for r in batch.results for url in r.source_texts})
    full_sources: dict[str, str] = {}
    for url in urls:
        hit = await cache.aget(f"fetch:{url}")
        if hit and hit.get("text"):
            full_sources[url] = hit["text"]
    print(f"windows read: {len(urls)}   full pages available: {len(full_sources)}")

    store = EvidenceStore(full_sources=full_sources)
    store.extend_from_results(batch.results)

    stats = store.stats()
    for key, value in stats.items():
        print(f"  {key:<20} {value}")

    retention = (
        stats["evidence_kept"] / stats["findings_seen"] * 100
        if stats["findings_seen"]
        else 0
    )
    print(f"\n  retention: {retention:.0f}% of findings were novel "
          f"({stats['duplicates_exact']} exact + {stats['duplicates_near']} near duplicates removed)")

    section("3. Coverage: which sub-questions are actually supported?")
    for question, count in store.coverage(
        [sq.question for sq in plan.sub_questions]
    ).items():
        flag = "  <-- UNCOVERED" if count == 0 else ""
        print(f"  {count:2d}  {question[:70]}{flag}")

    section("4. Evidence table")
    print(store.to_markdown())

    section("4b. Dedupe: same quote twice, then a reworded claim")
    if store.items:
        first = store.items[0]
        before = len(store)
        store.add(
            claim=first.claim,
            quote=first.quote.replace(" ", "  ", 1),  # whitespace-only difference
            url=first.url,
            sub_question="duplicate test",
        )
        print(f"  exact duplicate (extra whitespace) -> evidence {before} -> {len(store)}")
        store.add(
            claim=first.claim,
            quote=first.quote[:-8] + " (rephrased)",  # different quote, same claim
            url=first.url,
            sub_question="near-duplicate test",
        )
        print(f"  near duplicate (same claim, new quote) -> evidence {len(store)}")
        print(f"  counters: exact={store.duplicates} near={store.near_duplicates}")

    section("5. Proof: reopen the source and read the span")
    for item in store.items:
        if item.match != "exact" or item.span_start is None:
            continue
        text = store.source_text(item.url)
        start = max(0, item.span_start - 90)
        end = min(len(text), (item.span_end or 0) + 90)
        print(f"\n  {item.id}  {item.url}")
        print(f"  claim: {item.claim[:100]}")
        print(f"  span : chars {item.span_start}-{item.span_end} (match={item.match})")
        print(f"  page : ...{text[start:end].replace(chr(10), ' ')}...")
        break

    section("6. Quotes that did not survive verification")
    for item in store.items:
        if item.verified:
            continue
        print(f"\n  {item.id}  match={item.match}  {item.url}")
        print(f"  claim: {item.claim[:110]}")
        print(f"  quote: {item.quote[:125]}")
        if item.match == "outside_window":
            print("  -> the sentence IS in the page, but outside the 2,600-char window")
            print("     the agent was shown. Real quote, unread provenance: not citable.")
        else:
            print("  -> not in the page at all: fabricated, or edited beyond recognition.")

    section("6b. A real quote the agent never read (reproducible)")
    if full_sources:
        url = next(iter(full_sources))
        page = full_sources[url]
        window = store.source_text(url)
        sentence = next(
            (
                part.strip()
                for part in page.split(". ")
                if len(part.strip()) >= 70 and part.strip() not in window
            ),
            None,
        )
        if sentence:
            probe = store.add(
                claim="provenance probe: sentence exists in the page, outside the window",
                quote=sentence,
                url=url,
                sub_question="provenance probe",
            )
            if probe is not None:
                print(f"  match           : {probe.match}")
                print(f"  verified        : {probe.verified}")
                print(f"  exists_in_source: {probe.exists_in_source}")
                print(f"  quote: {sentence[:110]}")
                print("  -> a real sentence the model never saw. Not citable: the")
                print("     provenance is unread, even though the words are true.")

    section("7. A planted hallucination, to prove the check is real")
    fake = store.add(
        claim="asyncio.gather cancels all sibling coroutines immediately by default",
        quote="When any coroutine raises, gather immediately cancels all remaining tasks.",
        url=next((item.url for item in store.items), ""),
        sub_question="planted test",
        confidence="high",
    )
    if fake is not None:
        print(f"  id      : {fake.id}")
        print(f"  match   : {fake.match}   verified: {fake.verified}")
        print(f"  span    : {fake.span_start}-{fake.span_end}")
        print("  -> stored, but marked unverifiable. Step 9 refuses to publish it.")
    print(f"\n  unverified after planting: {store.unverified}")

    section("8. Publish")
    json_path = store.save("reports/evidence.json")
    md_path = json_path.with_suffix(".md")
    md_path.write_text(store.to_markdown(), encoding="utf-8")
    print(f"  {json_path}")
    print(f"  {md_path}")
    print("\nNext: step 8 writes prose that may only cite these ids.")


if __name__ == "__main__":
    asyncio.run(main())
