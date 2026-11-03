"""Step 9 demo: does the quote actually support the claim?

Run from the repo root:

    .\\venv\\Scripts\\python.exe -m examples.step9_verify

Runs the pipeline once, then judges every quote/claim pair, looks for
contradictions between sources, and rewrites the report with the support gate on.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from research_agent.config import Settings
from research_agent.evidence import Evidence, EvidenceStore
from research_agent.llm import create_client
from research_agent.planning import Planner
from research_agent.retrieval.cache import Cache
from research_agent.subagent import ResearchOrchestrator
from research_agent.tools.web import make_subagent_tools
from research_agent.verify import ClaimVerifier, source_tier, verify_store
from research_agent.writer import ReportWriter, domain

QUESTION = (
    "If asyncio.gather() gets one failing coroutine, what happens to the results "
    "I still care about, and how do I make sure nothing is silently lost?"
)

# Curated pairs: the expected verdict is known in advance, so this doubles as a
# regression test for the judge itself.
CURATED = [
    (
        "contradicted",
        "asyncio.gather cancels the other coroutines when one of them raises",
        "If return_exceptions is False (default), the first raised exception is "
        "immediately propagated to the caller. Other awaitables in the aws "
        "sequence won't be cancelled and will continue to run.",
    ),
    (
        "supported",
        "Setting return_exceptions=True returns exceptions as results instead of "
        "raising them",
        "If return_exceptions is True, exceptions are treated the same as "
        "successful results, and aggregated in the result list.",
    ),
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


async def main() -> None:
    settings = Settings.from_env()
    client = create_client(settings)
    print(settings.safe_summary())

    section("1. Evidence")
    cache = Cache(settings.cache_path, ttl_s=settings.cache_ttl_s)
    artifact = Path("reports/evidence.json")
    plan = None
    gaps: list[str] = []

    if artifact.exists():
        # Stages talk through the store, not through each other. Reusing the
        # artifact makes this demo 10x faster and proves the decoupling.
        store = EvidenceStore.load(artifact)
        print(f"  loaded {len(store)} records from {artifact}")
        print("  (delete that file to run the research phase from scratch)")
        print(f"  verified: {len(store.verified_items)}   citable: {len(store.citable())}")
    else:
        plan, _, _ = await Planner(client, max_tokens=1200).plan(QUESTION)
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
        gaps = [gap for result in batch.results for gap in result.gaps]
        print(f"  findings {store.findings_seen} -> evidence {len(store)}")

    for item in store.items:
        print(f"    {item.id}  {item.match:<14} {item.claim[:70]}")

    section("2. Judge every verified quote against its claim")
    # Classification work goes to the cheap model. This is routing by job, not
    # by "best model": 20B answers these in <1s, 120B took 15-40s and stalled.
    judge_client = create_client(settings.judge_settings())
    print(f"  judge model: {settings.judge_settings().model}")
    report = await verify_store(judge_client, store)
    counts = report.counts()
    print(f"  verdicts: {counts}   errors: {len(report.errors)}   "
          f"tokens: {report.usage}")
    for item in store.verified_items:
        judgement = report.judgements.get(item.id)
        if judgement is None:
            print(f"  {item.id}  ERROR {report.errors.get(item.id, '')}")
            continue
        print(f"\n  {item.id}  {judgement.verdict.upper():<13} trust={item.trust}")
        print(f"    claim : {item.claim[:96]}")
        print(f"    reason: {judgement.reason[:110]}")

    section("3. The judge on curated pairs (known answers)")
    verifier = ClaimVerifier(judge_client)
    for expected, claim, quote in CURATED:
        judgement, _ = await verifier.judge(claim, quote)
        mark = "ok " if judgement.verdict == expected else "MISMATCH"
        print(f"\n  [{mark}] expected={expected:<13} got={judgement.verdict}")
        print(f"    claim : {claim[:92]}")
        print(f"    reason: {judgement.reason[:110]}")

    section("4. Contradictions between sources")
    planted = [
        Evidence(
            id="ev_00000001",
            claim="gather cancels the remaining coroutines when one fails",
            quote="",
            url="https://example.com/a",
        ),
        Evidence(
            id="ev_00000002",
            claim="gather does not cancel the remaining coroutines when one fails",
            quote="",
            url="https://example.com/b",
        ),
    ]
    conflicts, _ = await verifier.find_conflicts(planted)
    print("  planted pair (must be flagged):")
    for conflict in conflicts:
        print(f"    {conflict.ids}: {conflict.why[:100]}")
    if not conflicts:
        print("    none flagged - the conflict detector missed an obvious pair")

    print("\n  real store:")
    if report.contradictions:
        for conflict in report.contradictions:
            print(f"    {conflict.ids}: {conflict.why[:110]}")
    else:
        print("    none found (a valid answer: these sources mostly agree)")

    section("5. Effect of the support gate")
    print("  trust tier by domain (pure function, no model):")
    for url in (
        "https://docs.python.org/3/library/asyncio-task.html",
        "https://stackoverflow.com/questions/1",
        "https://runebook.dev/en/docs/python/library/asyncio-task",
        "https://example.com/blog/post",
    ):
        print(f"    {source_tier(url):<11} {domain(url)}")

    citable = store.citable()
    dropped = [item for item in store.verified_items if item not in citable]
    print(f"  verified: {len(store.verified_items)}   citable now: {len(citable)}")
    for item in dropped:
        print(f"  dropped {item.id}  support={item.support}  {item.support_reason[:80]}")

    section("6. Rewrite the report under the gate")
    writer = ReportWriter(client, max_tokens=1800)
    draft = await writer.write(question=QUESTION, store=store, plan=plan, gaps=gaps)

    print(f"  ok={draft.ok}  repaired={draft.repaired}  words={draft.word_count}  "
          f"citations={len(draft.cited_ids)}  unused={len(draft.unused_ids)}")
    for problem in draft.initial_errors:
        print(f"  first draft {problem.code}: {problem.detail}")
    for problem in draft.errors:
        print(f"  ERROR {problem.code}: {problem.detail}")
    bad = [
        evidence_id
        for evidence_id in draft.cited_ids
        if store.get(evidence_id) is not None
        and store.get(evidence_id).support in {"unsupported", "contradicted"}
    ]
    print(f"  citations pointing at unsupported evidence: {len(bad)}")
    for evidence_id in draft.cited_ids:
        item = store.get(evidence_id)
        if item is not None:
            print(f"    {evidence_id}  support={item.support:<11} trust={item.trust}")

    section("7. Publish")
    Path("reports").mkdir(exist_ok=True)
    verification = Path("reports/verification.json")
    verification.write_text(
        json.dumps(
            {
                "counts": counts,
                "judgements": {
                    evidence_id: judgement.model_dump()
                    for evidence_id, judgement in report.judgements.items()
                },
                "contradictions": [asdict(c) for c in report.contradictions],
                "errors": report.errors,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    draft_path = Path("reports/report_verified.md")
    draft_path.write_text(draft.markdown, encoding="utf-8")
    print(f"  {verification}")
    print(f"  {draft_path}")

    print("\nNext: step 10 measures all of this over N runs instead of one.")


if __name__ == "__main__":
    asyncio.run(main())
