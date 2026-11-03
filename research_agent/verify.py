"""Claim-level verification: does the quote actually say what the claim says?

Step 7 proved quotes are *real*. It could not prove they are *relevant*. The
canonical example sits in this project's own store:

    claim:  gather cancels the other coroutines
    quote:  "The tasks that haven't completed are cancelled, and gather
             re-raises the first exception."
    match:  exact   <- the sentence is really on the page

Mechanically verified, factually wrong: `asyncio.gather` does not cancel the
siblings. A quote can be genuine and still not support the claim, or support it
while being wrong about the world.

So this step asks two different questions:

  1. **Support** — given claim and quote only, does the quote entail the claim?
     One model call per pair, deliberately isolated: a judge that sees other
     evidence starts reasoning about the topic instead of the text.

  2. **Conflict** — do two claims from different sources assert incompatible
     things? One call over all claims, because this is the one judgement that
     cannot be made pairwise in isolation.

Plus a deterministic trust tier from the domain, because "docs.python.org" and
"a 2019 blog post" should not weigh the same in the report.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Literal, Sequence
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from .evidence import Evidence, EvidenceStore
from .llm import LLMClient, Message, Usage

Verdict = Literal["supported", "partial", "unsupported", "contradicted"]

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

JUDGE_PROMPT = """You check whether one quoted sentence supports one claimed statement.

You receive CLAIM and QUOTE. The quote is a real sentence from a real page; your
job is not to fact-check the world, only to decide what the quote itself says.

Verdicts:
- "supported": read literally, the quote states what the claim states.
- "partial": the quote supports part of the claim, or needs an unstated assumption.
- "unsupported": the quote is real and related, but does not state the claim.
- "contradicted": the quote says the opposite of the claim.

Be strict about words the quote does not contain. If the claim says "always",
"never", "cancels", "guarantees" or names a specific version and the quote does
not, that is "partial" at best. A true quote supporting a different point is
"unsupported" for this claim.

Return JSON only:
{"verdict": "supported|partial|unsupported|contradicted", "reason": "one sentence"}"""

CONFLICT_PROMPT = """You find pairs of claims that cannot both be true at the same time.

You receive a list of claims, each with an id, gathered from different sources
about the same question.

A conflict is when one claim asserts something and another asserts the negation
of it about the same action. "X cancels the tasks" and "X does not cancel the
tasks" IS a conflict, even when the wording differs.

NOT a conflict: different Python versions, different functions or libraries, or
one claim being merely narrower than the other.

Return JSON only:
{"conflicts": [{"ids": ["ev_aaaaaaaa", "ev_bbbbbbbb"], "why": "one sentence"}]}

Return an empty list only if no pair negates another. Do not invent conflicts."""

PRIMARY_DOMAINS = (
    "docs.python.org",
    "peps.python.org",
    "developer.mozilla.org",
    "learn.microsoft.com",
    "docs.oracle.com",
    "kubernetes.io",
    "postgresql.org",
    "rfc-editor.org",
)
COMMUNITY_DOMAINS = (
    "stackoverflow.com",
    "stackexchange.com",
    "github.com",
    "discuss.python.org",
)
AGGREGATOR_PATTERNS = (
    "runebook.dev",
    "tutorialspoint",
    "geeksforgeeks",
    "w3schools",
    "baeldung",
    "medium.com",
    "dev.to",
    "realpython",
    "superfastpython",
    "pythontutorial",
    "tutorial",
)


def source_tier(url: str) -> str:
    """Deterministic trust tier. No model, no prompt, no argument."""
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    if any(host == domain or host.endswith("." + domain) for domain in PRIMARY_DOMAINS):
        return "primary"
    if any(host == domain or host.endswith("." + domain) for domain in COMMUNITY_DOMAINS):
        return "community"
    if any(pattern in host for pattern in AGGREGATOR_PATTERNS):
        return "aggregator"
    return "unknown"


class SupportJudgement(BaseModel):
    verdict: Verdict
    reason: str = Field(default="", max_length=400)


@dataclass(slots=True)
class Contradiction:
    ids: list[str]
    why: str


@dataclass(slots=True)
class VerificationReport:
    judgements: dict[str, SupportJudgement] = field(default_factory=dict)
    contradictions: list[Contradiction] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)

    def counts(self) -> dict[str, int]:
        counts = {"supported": 0, "partial": 0, "unsupported": 0, "contradicted": 0}
        for judgement in self.judgements.values():
            counts[judgement.verdict] += 1
        return counts


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        match = _JSON_OBJECT.search(text)
        if match is None:
            raise
        return json.loads(match.group(0))


class ClaimVerifier:
    def __init__(
        self,
        client: LLMClient,
        *,
        concurrency: int = 4,
        max_tokens: int = 400,
    ) -> None:
        self.client = client
        self.concurrency = max(1, concurrency)
        self.max_tokens = max_tokens

    async def _structured(self, messages: list[Message], max_tokens: int, parse):
        """Plain completion first; JSON mode only if the text will not parse.

        JSON mode is not free: on some providers/model combinations it stalls
        (observed: 90s timeout on Groq gpt-oss while the same prompt in plain
        mode took 8s) or fails server-side validation outright. The prompt
        already asks for JSON and the parser tolerates fences, so plain mode is
        the fast path and `response_format` is the repair mechanism.
        """
        response = await self.client.chat(
            messages,
            temperature=0.0,
            max_tokens=max_tokens,
            json_mode=False,
        )
        usage = response.usage
        try:
            return parse(response.message.content), usage
        except Exception:
            pass

        # Second attempt: same call, sharper instruction. Cheaper than a
        # provider-side JSON constraint and far more reliable on Groq.
        retry = await self.client.chat(
            messages + [Message.user("Return only the JSON object. No prose, no fences.")],
            temperature=0.0,
            max_tokens=max_tokens,
            json_mode=False,
        )
        usage += retry.usage
        try:
            return parse(retry.message.content), usage
        except Exception:
            pass

        # Last resort: let the provider enforce JSON, even if it is slow.
        strict = await self.client.chat(
            messages,
            temperature=0.0,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return parse(strict.message.content), usage + strict.usage

    async def judge(self, claim: str, quote: str) -> tuple[SupportJudgement, Usage]:
        messages = [
            Message.system(JUDGE_PROMPT),
            Message.user(f"CLAIM: {claim}\n\nQUOTE: {quote}"),
        ]

        def parse(text: str) -> SupportJudgement:
            return SupportJudgement.model_validate(_parse_json(text))

        judgement, usage = await self._structured(messages, self.max_tokens, parse)
        return judgement, usage

    async def verify_items(
        self, items: Sequence[Evidence], *, concurrency: int | None = None
    ) -> VerificationReport:
        report = VerificationReport()
        semaphore = asyncio.Semaphore(concurrency or self.concurrency)

        async def one(item: Evidence) -> None:
            async with semaphore:
                try:
                    judgement, usage = await self.judge(item.claim, item.quote)
                except Exception as exc:  # never lose the batch to one bad call
                    report.errors[item.id] = f"{type(exc).__name__}: {exc}"
                    return
            report.judgements[item.id] = judgement
            report.usage += usage

        await asyncio.gather(*(one(item) for item in items), return_exceptions=True)
        return report

    async def find_conflicts(
        self, items: Sequence[Evidence], *, max_items: int = 24
    ) -> tuple[list[Contradiction], Usage]:
        chosen = list(items)[:max_items]
        if len(chosen) < 2:
            return [], Usage()

        listing = "\n".join(f"[{item.id}] {item.claim}" for item in chosen)
        messages = [
            Message.system(CONFLICT_PROMPT),
            Message.user(f"CLAIMS:\n{listing}"),
        ]

        def parse(text: str) -> dict:
            return _parse_json(text)

        try:
            payload, usage = await self._structured(messages, 500, parse)
        except Exception:
            # A failed conflict scan must not destroy a run that already has
            # support verdicts. Degrade to "no conflicts found, unscanned".
            return [], Usage()

        known = {item.id for item in chosen}
        conflicts: list[Contradiction] = []
        for raw in payload.get("conflicts", []) or []:
            ids = [str(value) for value in raw.get("ids", []) if str(value) in known]
            if len(ids) < 2:
                continue  # hallucinated or dangling id: drop the whole group
            conflicts.append(Contradiction(ids=ids, why=str(raw.get("why", ""))[:300]))
        return conflicts, usage


def apply_verification(
    store: EvidenceStore, report: VerificationReport, *, trust: bool = True
) -> None:
    """Write verdicts back onto the store so the writer sees them."""
    for item in store.items:
        judgement = report.judgements.get(item.id)
        if judgement is not None:
            item.support = judgement.verdict
            item.support_reason = judgement.reason
        elif item.id in report.errors:
            # Fail closed: an item we could not judge is not citable, even though
            # its quote was verified. "Unchecked" would let a 429-shaped hole
            # into the report.
            item.support = "unjudged"
            item.support_reason = report.errors[item.id][:300]
        if trust:
            item.trust = source_tier(item.url)


async def verify_store(
    client: LLMClient,
    store: EvidenceStore,
    *,
    check_conflicts: bool = True,
    concurrency: int = 4,
) -> VerificationReport:
    verifier = ClaimVerifier(client, concurrency=concurrency)
    items = store.verified_items  # judging unverified quotes is wasted money
    report = await verifier.verify_items(items)

    # Free tiers drop calls under burst; retry the failures one at a time before
    # giving up on them.
    if report.errors:
        retry_ids = set(report.errors)
        retry_items = [item for item in items if item.id in retry_ids]
        report.errors.clear()
        second = await verifier.verify_items(retry_items, concurrency=1)
        report.judgements.update(second.judgements)
        report.errors.update(second.errors)
        report.usage += second.usage

    if check_conflicts:
        conflicts, usage = await verifier.find_conflicts(items)
        report.contradictions = conflicts
        report.usage += usage
    apply_verification(store, report)
    return report
