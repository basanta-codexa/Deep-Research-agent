"""Step 8 demo: a writer that can only cite evidence ids.

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step8_writer

Runs the whole pipeline (plan -> sub-agents -> evidence store -> draft) because
the writer is only meaningful on real evidence. Writes reports/report.md.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from research_agent.config import Settings
from research_agent.evidence import EvidenceStore
from research_agent.llm import create_client
from research_agent.planning import Planner
from research_agent.retrieval.cache import Cache
from research_agent.subagent import ResearchOrchestrator
from research_agent.tools.web import make_subagent_tools
from research_agent.writer import ReportWriter, check_draft

QUESTION = (
    "If asyncio.gather() gets one failing coroutine, what happens to the results "
    "I still care about, and how do I make sure nothing is silently lost?"
)

# A deliberately broken draft, to show the checks are mechanical and not vibes.
BAD_DRAFT = """# Asyncio gather error handling

## Summary
Asyncio gather propagates the first exception to the caller. [ev_deadbeef]

## What happens to the other results
The other coroutines keep running, which is documented at https://example.com/made-up-article.

## Limitations
- Only two sources were read.
"""

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    print(settings.safe_summary())

    section("1. Evidence (same pipeline as step 7)")
    plan, _, _ = await Planner(client, max_tokens=1200).plan(QUESTION)
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    batch = await ResearchOrchestrator(
        client,
        make_subagent_tools(settings, cache=cache),
        concurrency=2,
        max_steps=3,
    ).run(plan.sub_questions)

    urls = sorted({url for r in batch.results for url in r.source_texts})
    full_sources: dict[str, str] = {}
    for url in urls:
        hit = await cache.aget(f"fetch:{url}")
        if hit and hit.get("text"):
            full_sources[url] = hit["text"]

    store = EvidenceStore(full_sources=full_sources)
    store.extend_from_results(batch.results)

    stats = store.stats()
    print(f"  findings {stats['findings_seen']} -> evidence {stats['evidence_kept']}"
          f"   verified {len(store.citable())}/{len(store)}"
          f"   sources {stats['sources']}")

    gaps = [gap for result in batch.results for gap in result.gaps]

    section("2. Write (ids only, no URLs, no page text)")
    writer = ReportWriter(client, max_tokens=1800)
    report = await writer.write(question=QUESTION, plan=plan, store=store, gaps=gaps)

    print(f"  ok        : {report.ok}")
    print(f"  repaired  : {report.repaired}")
    print(f"  sections  : {report.sections}")
    print(f"  words     : {report.word_count}")
    print(f"  citations : {len(report.cited_ids)} distinct ids, "
          f"{len(report.unused_ids)} verified records unused")
    print(f"  tokens    : {report.usage}")
    if report.errors:
        for problem in report.errors:
            print(f"  ERROR {problem.code}: {problem.detail}")

    section("3. The report")
    print(report.markdown)

    section("4. Citation map: every marker resolves to a verified record")
    for evidence_id in report.cited_ids:
        item = store.get(evidence_id)
        if item is None:
            print(f"  {evidence_id}  MISSING")
            continue
        span = (
            f"{item.span_start}-{item.span_end}"
            if item.span_start is not None
            else "-"
        )
        print(f"  {evidence_id}  {item.match:<14} span {span:<12} {item.url}")
        print(f"      {item.claim[:96]}")

    section("5. The checks, on a deliberately bad draft")
    bad = check_draft(BAD_DRAFT, {item.id for item in store.citable()})
    for problem in bad:
        print(f"  [{problem.severity}] {problem.code}: {problem.detail}")
    print(f"\n  {len(bad)} problems. The writer gets one repair turn; if they survive,")
    print("  Report.ok is False and the CLI refuses to publish.")

    section("6. Publish")
    out = Path("reports/report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.markdown, encoding="utf-8")
    meta = Path("reports/report.json")
    meta.write_text(
        json.dumps(
            {
                "question": QUESTION,
                "ok": report.ok,
                "repaired": report.repaired,
                "sections": report.sections,
                "words": report.word_count,
                "cited_ids": report.cited_ids,
                "unused_ids": report.unused_ids,
                "errors": [asdict(p) for p in report.errors],
                "warnings": [asdict(p) for p in report.warnings],
                "usage": {
                    "prompt_tokens": report.usage.prompt_tokens,
                    "completion_tokens": report.usage.completion_tokens,
                },
                "evidence": store.stats(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  {out}")
    print(f"  {meta}")
    print("\nNext: step 9 verifies that each quote actually supports its claim.")


if __name__ == "__main__":
    asyncio.run(main())
