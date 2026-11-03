"""Sub-agents: one sub-question each, small context, hard budget, concurrent.

Why not just let one agent research everything?

  * **Context rot.** Every extra page in one conversation dilutes attention. A
    4-question research task produces ~23k chars of evidence; a single agent
    cannot hold that plus its own reasoning.
  * **Latency.** Four independent questions are four independent waits.
  * **Blast radius.** One agent that derails kills the whole run. Four agents
    that each fail independently lose 25%.
  * **Attribution.** "Which sub-question produced the bad claim?" is unanswerable
    in a monolith and trivial here.

Cost of all that: N agents × steps × context, and no shared memory. Step 7 is
how we buy the memory back without the context.

Design note (learned the hard way): a sub-agent is TWO calls, not one loop.

    phase 1  loop: read sources, reply in plain text   (tool contract)
    phase 2  one call: turn notes into JSON findings   (format contract)

Asking one turn to both call tools and emit strict JSON produced truncated
JSON, tool calls instead of answers, and provider 400s. Splitting the contracts
made each half trivial.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Sequence

from pydantic import BaseModel, Field, ValidationError

from .agent import Agent
from .llm import LLMClient, Message, Usage
from .planning import SubQuestion
from .structured import complete_json
from .tools.registry import Tool

_SOURCE_RE = re.compile(r"^URL: (\S+)", re.MULTILINE)
_TITLE_RE = re.compile(r"^TITLE: (.+)$", re.MULTILINE)


def parse_source_output(output: str) -> tuple[str, str, str] | None:
    """Split a `read_source`/`fetch_page` result into (url, title, text)."""
    if not output.startswith("URL: "):
        return None
    url_match = _SOURCE_RE.search(output)
    if url_match is None:
        return None
    _, separator, text = output.partition("\n---\n")
    if not separator:
        return None
    title_match = _TITLE_RE.search(output)
    title = title_match.group(1).strip() if title_match else ""
    return url_match.group(1).strip(), title, text

READER_PROMPT = """You are a reader. You gather evidence for ONE sub-question.

Tool: read_source(query, focus, max_chars) searches the web and returns the text \
of the best page that actually loads, plus its URL.

Rules:
- Call read_source ONCE. Call it a second time only if the first page does not
  address the sub-question at all.
- Then reply in plain text, at most 120 words: what the source says about the
  sub-question, plus the exact URL you read.
- Do not write JSON. Do not write code fences. A separate step formats your notes.
- Never state a fact that is not in the text you read."""

EXTRACT_PROMPT = """You convert research notes into structured findings.

Given a sub-question and the text of the pages a reader fetched, return JSON only:

{"answer": "at most two sentences",
 "findings": [{"claim": "what the source says", "quote": "exact sentence",
               "url": "https://...", "confidence": "high|medium|low"}],
 "gaps": ["what could not be established"]}

Rules:
- `quote` must be copied character-for-character from the SOURCES text.
- `url` must be one of the URLs listed in SOURCES.
- Maximum 3 findings. Fewer, better-grounded findings beat many.
- If the sources do not answer the sub-question, return an empty findings list and
  explain in `gaps`. Never invent a source, a number, or a quote."""


class FindingModel(BaseModel):
    claim: str = Field(min_length=3)
    quote: str = Field(min_length=3)
    url: str
    confidence: Literal["high", "medium", "low"] = "medium"


class SubAgentOutput(BaseModel):
    answer: str = ""
    findings: list[FindingModel] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class SubAgentResult:
    question: str
    search_query: str
    answer: str = ""
    findings: list[FindingModel] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    source_texts: dict[str, str] = field(default_factory=dict)
    source_titles: dict[str, str] = field(default_factory=dict)
    ungrounded_urls: list[str] = field(default_factory=list)
    queries_used: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    steps: int = 0
    elapsed_s: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class ResearchBatch:
    results: list[SubAgentResult]
    usage: Usage
    wall_clock_s: float
    concurrency: int

    @property
    def findings(self) -> list[FindingModel]:
        return [f for r in self.results for f in r.findings]

    @property
    def hard_failures(self) -> list[SubAgentResult]:
        return [r for r in self.results if not r.ok]


def parse_output(text: str) -> tuple[SubAgentOutput | None, str | None]:
    """Tolerant JSON parse: models wrap JSON in fences, add preambles, etc."""
    text = (text or "").strip()
    if not text:
        return None, "empty response"

    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error = None
    for candidate in candidates:
        try:
            return SubAgentOutput.model_validate_json(candidate), None
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
    return None, last_error


class SubAgent:
    def __init__(
        self,
        client: LLMClient,
        tools: Sequence[Tool],
        *,
        max_steps: int = 3,
        max_tokens: int = 700,
        text_budget: int = 2600,
        extract_budget: int = 1000,
        temperature: float = 0.2,
    ) -> None:
        self.client = client
        self.tools = tools
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.text_budget = text_budget
        self.extract_budget = extract_budget
        self.temperature = temperature

    async def run(self, sub_question: SubQuestion) -> SubAgentResult:
        started = time.perf_counter()
        result = SubAgentResult(
            question=sub_question.question, search_query=sub_question.search_query
        )

        agent = Agent(
            self.client,
            self.tools,
            system_prompt=READER_PROMPT,
            max_steps=self.max_steps,
            max_tokens=self.max_tokens,
            max_tool_result_chars=self.text_budget,
            temperature=self.temperature,
            repeat_limit=2,
            grace_answer=False,
        )
        prompt = (
            f"Sub-question: {sub_question.question}\n"
            f"Why it matters: {sub_question.why}\n"
            f"Suggested query: {sub_question.search_query}"
        )

        try:
            agent_result = await agent.run(prompt)
        except Exception as exc:  # network, provider — never kill the batch
            result.error = f"{type(exc).__name__}: {exc}"
            result.elapsed_s = time.perf_counter() - started
            return result

        result.usage = agent_result.usage
        result.steps = len(agent_result.steps)
        result.queries_used = [
            str(call.arguments.get("query", ""))
            for step in agent_result.steps
            for call in step.tool_calls
        ]

        # What did this agent actually read? Feeds phase 2 and catches invented URLs.
        blobs: list[str] = []
        sources: set[str] = set()
        for step in agent_result.steps:
            for _, output in step.tool_outputs:
                blobs.append(output)
                parsed = parse_source_output(output)
                if parsed is None:
                    continue
                url, title, text = parsed
                sources.add(url)
                result.source_titles[url] = title
                # Keep the longest window if a URL was read twice.
                if len(text) > len(result.source_texts.get(url, "")):
                    result.source_texts[url] = text
        result.sources = sorted(sources)

        if not blobs:
            result.gaps = ["no source was read"]
            result.answer = agent_result.answer.strip()[:400]
            if agent_result.stopped != "final_answer":
                result.error = f"agent stopped early: {agent_result.stopped}"
            result.elapsed_s = time.perf_counter() - started
            return result

        # Phase 2: format the notes. Always run it — the reader's own text answer
        # is a fallback, not the product.
        out, usage, error = await self._extract(sub_question, blobs)
        result.usage += usage
        result.elapsed_s = time.perf_counter() - started

        if out is None:
            result.answer = agent_result.answer.strip()[:400]
            result.gaps = [f"could not format findings: {error}"]
            return result

        result.answer = out.answer.strip()
        result.findings = out.findings
        result.gaps = out.gaps
        result.ungrounded_urls = sorted(
            {f.url for f in out.findings if f.url not in sources}
        )
        return result

    async def _extract(
        self, sub_question: SubQuestion, blobs: Sequence[str]
    ) -> tuple[SubAgentOutput | None, Usage, str | None]:
        joined = "\n\n".join(blobs)[:7000]
        messages = [
            Message.system(EXTRACT_PROMPT),
            Message.user(
                f"SUB-QUESTION: {sub_question.question}\n\n"
                f"SOURCES:\n{joined}"
            ),
        ]
        def parse(text: str) -> SubAgentOutput:
            output, error = parse_output(text)
            if output is None:
                raise ValueError(error or "unparseable extractor output")
            return output

        try:
            output, usage = await complete_json(
                self.client,
                messages,
                parse=parse,
                max_tokens=self.extract_budget,
                temperature=0.0,
            )
        except Exception as exc:
            # Recover the tokens spent failing: the eval harness bills them.
            burned = getattr(exc, "usage", Usage())
            return None, burned, f"{type(exc).__name__}: {exc}"
        return output, usage, None


class ResearchOrchestrator:
    """Runs one sub-agent per sub-question, at most `concurrency` at a time.

    The semaphore is not about politeness. The real limit is the provider's
    tokens-per-minute (and your own budget), not the number of questions.
    Concurrency above that limit converts speed into 429s.
    """

    def __init__(
        self,
        client: LLMClient,
        tools: Sequence[Tool],
        *,
        concurrency: int = 2,
        max_steps: int = 3,
        max_tokens: int = 700,
        text_budget: int = 2600,
    ) -> None:
        self.client = client
        self.tools = tools
        self.concurrency = max(1, concurrency)
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.text_budget = text_budget

    async def run(
        self,
        sub_questions: Sequence[SubQuestion],
        *,
        on_result: Callable[[SubAgentResult], None] | None = None,
    ) -> ResearchBatch:
        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[SubAgentResult | None] = [None] * len(sub_questions)
        started = time.perf_counter()

        async def one(index: int, sub_question: SubQuestion) -> None:
            async with semaphore:
                result = await SubAgent(
                    self.client,
                    self.tools,
                    max_steps=self.max_steps,
                    max_tokens=self.max_tokens,
                    text_budget=self.text_budget,
                ).run(sub_question)
            results[index] = result
            if on_result is not None:
                on_result(result)

        # return_exceptions=True: a bug in one agent must not cancel its siblings.
        # SubAgent.run already catches, so this is belt-and-braces.
        await asyncio.gather(
            *(one(i, sq) for i, sq in enumerate(sub_questions)),
            return_exceptions=True,
        )
        wall_clock = time.perf_counter() - started

        finished = [r for r in results if r is not None]
        usage = Usage()
        for item in finished:
            usage += item.usage

        return ResearchBatch(
            results=finished,
            usage=usage,
            wall_clock_s=wall_clock,
            concurrency=self.concurrency,
        )
