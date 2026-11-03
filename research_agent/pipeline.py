"""The end-to-end pipeline, as one callable.

Until now the full chain (plan -> research -> verify -> write) only existed inside
`examples/step9_verify.py`. An eval harness cannot import an example, and copying
the wiring would guarantee the two drift apart. So the pipeline moves here and the
examples become thin demos of it.

Failure policy: a stage failure is recorded on the result, not raised. A 30-question
eval where question 7 times out must still return 29 measurements — dropping the
whole run because one sub-agent stalled is how evals get abandoned.

Tracing policy: every run gets a tracer, and the clients are wrapped once so that
*every* model call (planner, reader, extractor, judge, writer) lands in the trace
without a single instrumentation line in those modules.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .evidence import EvidenceStore
from .llm import LLMClient, Usage
from .planning import Plan, Planner
from .subagent import ResearchBatch, ResearchOrchestrator
from .tools.registry import Tool
from .tracing import Tracer, TraceLLMClient
from .verify import VerificationReport, verify_store
from .writer import Report, ReportWriter, WriterError


@dataclass(slots=True)
class PipelineConfig:
    concurrency: int = 2
    max_steps: int = 3
    plan_max_tokens: int = 1200
    writer_max_tokens: int = 1800
    judge_concurrency: int = 4
    check_conflicts: bool = True


@dataclass(slots=True)
class PipelineResult:
    question: str
    plan: Plan | None = None
    batch: ResearchBatch | None = None
    store: EvidenceStore = field(default_factory=EvidenceStore)
    verification: VerificationReport | None = None
    report: Report | None = None
    error: str | None = None
    stage_errors: dict[str, str] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    timings: dict[str, float] = field(default_factory=dict)
    trace: Tracer | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.report is not None and self.report.ok


class ResearchPipeline:
    """One question in, one cited report out, with every stage measured."""

    def __init__(
        self,
        client: LLMClient,
        tools: Sequence[Tool],
        *,
        judge_client: LLMClient | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.tools = tools
        self.config = config or PipelineConfig()
        self.last_trace: Tracer | None = None
        # Wrap once: the wrapper reads the *current* tracer from a ContextVar,
        # so the same wrapper serves every run in a process.
        self.client = TraceLLMClient(client)
        if judge_client is None or judge_client is client:
            self.judge_client = self.client
        else:
            self.judge_client = TraceLLMClient(judge_client)

    async def run(
        self,
        question: str,
        *,
        on_stage: Callable[[str, str], None] | None = None,
        tracer: Tracer | None = None,
    ) -> PipelineResult:
        meta = {
            "provider": self.client.name,
            "model": self.client.model,
            "judge_model": self.judge_client.model,
            "concurrency": self.config.concurrency,
            "max_steps": self.config.max_steps,
        }
        if tracer is None:
            tracer = Tracer(question[:120], attributes=meta)
        else:
            # A caller-supplied tracer (the web UI) already has listeners; fill
            # in the run metadata without overwriting anything it set.
            tracer.attributes = {**meta, **tracer.attributes}
        # A cancelled run (timeout) never returns a result, so the eval needs a
        # handle on the partial trace to explain where the time went.
        self.last_trace = tracer
        result = PipelineResult(question=question, trace=tracer)

        with tracer.activate():
            with tracer.span("pipeline", kind="pipeline"):
                try:
                    return await self._run(question, result, tracer, on_stage)
                except Exception as exc:  # a bug must not escape without a trace
                    return self._fail(tracer, result, "pipeline", exc)

    async def _run(
        self,
        question: str,
        result: PipelineResult,
        tracer: Tracer,
        on_stage: Callable[[str, str], None] | None,
    ) -> PipelineResult:
        cfg = self.config

        def stage(name: str, state: str) -> None:
            if on_stage is not None:
                on_stage(name, state)

        # ---- plan ---------------------------------------------------------- #
        stage("plan", "start")
        started = time.perf_counter()
        with tracer.span("plan", kind="stage") as stage_span:
            try:
                plan, prompt_tokens, completion_tokens = await Planner(
                    self.client, max_tokens=cfg.plan_max_tokens
                ).plan(question)
            except Exception as exc:
                return self._fail(tracer, result, "plan", exc)
            result.plan = plan
            result.usage += Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            stage_span.attributes.update(
                {
                    "restated": plan.restated,
                    "questions": [
                        {
                            "question": sub.question,
                            "search_query": sub.search_query,
                        }
                        for sub in plan.sub_questions
                    ],
                }
            )
        result.timings["plan"] = time.perf_counter() - started
        stage("plan", "done")

        # ---- research ------------------------------------------------------ #
        stage("research", "start")
        started = time.perf_counter()
        with tracer.span("research", kind="stage") as stage_span:
            try:
                batch = await ResearchOrchestrator(
                    self.client,
                    self.tools,
                    concurrency=cfg.concurrency,
                    max_steps=cfg.max_steps,
                ).run(plan.sub_questions)
            except Exception as exc:
                return self._fail(tracer, result, "research", exc)
            result.batch = batch
            result.usage += batch.usage
            stage_span.attributes.update(
                {
                    "questions": len(plan.sub_questions),
                    "findings": len(batch.findings),
                    "sources": len(
                        {
                            url
                            for sub_result in batch.results
                            for url in sub_result.source_texts
                        }
                    ),
                }
            )
        result.timings["research"] = time.perf_counter() - started
        stage("research", "done")

        # ---- evidence ------------------------------------------------------ #
        stage("evidence", "start")
        started = time.perf_counter()
        with tracer.span("evidence", kind="stage") as stage_span:
            for sub_result in batch.results:
                for url, text in sub_result.source_texts.items():
                    result.store.register_source(
                        url, text, sub_result.source_titles.get(url, "")
                    )
            result.store.extend_from_results(batch.results)
            if not result.store.verified_items:
                return self._fail(
                    tracer,
                    result,
                    "evidence",
                    RuntimeError(
                        f"{len(result.store)} finding(s), none traceable to a fetched page"
                    ),
                )
            stage_span.attributes.update(result.store.stats())
        result.timings["evidence"] = time.perf_counter() - started
        stage("evidence", "done")

        # ---- verify -------------------------------------------------------- #
        stage("verify", "start")
        started = time.perf_counter()
        with tracer.span("verify", kind="stage") as stage_span:
            try:
                result.verification = await verify_store(
                    self.judge_client,
                    result.store,
                    check_conflicts=cfg.check_conflicts,
                    concurrency=cfg.judge_concurrency,
                )
            except Exception as exc:
                return self._fail(tracer, result, "verify", exc)
            result.usage += result.verification.usage
            stage_span.attributes.update(
                {
                    "verdicts": result.verification.counts(),
                    "contradictions": len(result.verification.contradictions),
                    "judge_errors": len(result.verification.errors),
                }
            )
        result.timings["verify"] = time.perf_counter() - started
        stage("verify", "done")

        # ---- write --------------------------------------------------------- #
        stage("write", "start")
        started = time.perf_counter()
        gaps = [gap for sub_result in batch.results for gap in sub_result.gaps]
        with tracer.span("write", kind="stage") as stage_span:
            try:
                result.report = await ReportWriter(
                    self.client, max_tokens=cfg.writer_max_tokens
                ).write(question=question, plan=plan, store=result.store, gaps=gaps)
            except WriterError as exc:
                return self._fail(tracer, result, "write", exc)
            except Exception as exc:
                return self._fail(tracer, result, "write", exc)
            result.usage += result.report.usage
            cited_sources = {
                cited.url
                for evidence_id in result.report.cited_ids
                if (cited := result.store.get(evidence_id)) is not None
            }
            stage_span.attributes.update(
                {
                    "words": result.report.word_count,
                    "citations": len(result.report.cited_ids),
                    "cited_sources": len(cited_sources),
                    "repaired": result.report.repaired,
                }
            )
        result.timings["write"] = time.perf_counter() - started
        stage("write", "done")
        # The planner returns raw token counts, so rebuild the cost from the one
        # place that saw every call. Unpriced calls contribute 0 here; the trace
        # summary is what flags them, and the eval refuses a total that hides them.
        result.usage.cost_usd = tracer.usage().cost_usd
        return result

    @staticmethod
    def _fail(
        tracer: Tracer, result: PipelineResult, stage: str, exc: Exception
    ) -> PipelineResult:
        message = f"{type(exc).__name__}: {exc}"
        result.stage_errors[stage] = message
        result.error = f"{stage}: {message}"
        # Inside the stage's `with` block, so this is the span that failed.
        current = tracer.current_span()
        if current is not None:
            current.status = "error"
            current.error = message[:300]
        return result
