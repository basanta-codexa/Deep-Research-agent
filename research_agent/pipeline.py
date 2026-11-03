"""The end-to-end pipeline, as one callable.

Until now the full chain (plan -> research -> verify -> write) only existed inside
`examples/step9_verify.py`. An eval harness cannot import an example, and copying
the wiring would guarantee the two drift apart. So the pipeline moves here and the
examples become thin demos of it.

Failure policy: a stage failure is recorded on the result, not raised. A 30-question
eval where question 7 times out must still return 29 measurements — dropping the
whole run because one sub-agent stalled is how evals get abandoned.
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
        self.client = client
        self.judge_client = judge_client or client
        self.tools = tools
        self.config = config or PipelineConfig()

    async def run(
        self,
        question: str,
        *,
        on_stage: Callable[[str, str], None] | None = None,
    ) -> PipelineResult:
        cfg = self.config
        result = PipelineResult(question=question)

        def stage(name: str, state: str) -> None:
            if on_stage is not None:
                on_stage(name, state)

        # ---- plan ---------------------------------------------------------- #
        stage("plan", "start")
        started = time.perf_counter()
        try:
            plan, prompt_tokens, completion_tokens = await Planner(
                self.client, max_tokens=cfg.plan_max_tokens
            ).plan(question)
        except Exception as exc:
            return self._fail(result, "plan", exc)
        result.plan = plan
        result.usage += Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        result.timings["plan"] = time.perf_counter() - started
        stage("plan", "done")

        # ---- research ------------------------------------------------------ #
        stage("research", "start")
        started = time.perf_counter()
        try:
            batch = await ResearchOrchestrator(
                self.client,
                self.tools,
                concurrency=cfg.concurrency,
                max_steps=cfg.max_steps,
            ).run(plan.sub_questions)
        except Exception as exc:
            return self._fail(result, "research", exc)
        result.batch = batch
        result.usage += batch.usage
        result.timings["research"] = time.perf_counter() - started
        stage("research", "done")

        # ---- evidence ------------------------------------------------------ #
        stage("evidence", "start")
        started = time.perf_counter()
        for sub_result in batch.results:
            for url, text in sub_result.source_texts.items():
                result.store.register_source(
                    url, text, sub_result.source_titles.get(url, "")
                )
        result.store.extend_from_results(batch.results)
        result.timings["evidence"] = time.perf_counter() - started
        stage("evidence", "done")
        if not result.store.verified_items:
            return self._fail(
                result,
                "evidence",
                RuntimeError(
                    f"{len(result.store)} finding(s), none traceable to a fetched page"
                ),
            )

        # ---- verify -------------------------------------------------------- #
        stage("verify", "start")
        started = time.perf_counter()
        try:
            result.verification = await verify_store(
                self.judge_client,
                result.store,
                check_conflicts=cfg.check_conflicts,
                concurrency=cfg.judge_concurrency,
            )
        except Exception as exc:
            return self._fail(result, "verify", exc)
        result.usage += result.verification.usage
        result.timings["verify"] = time.perf_counter() - started
        stage("verify", "done")

        # ---- write --------------------------------------------------------- #
        stage("write", "start")
        started = time.perf_counter()
        gaps = [gap for sub_result in batch.results for gap in sub_result.gaps]
        try:
            result.report = await ReportWriter(
                self.client, max_tokens=cfg.writer_max_tokens
            ).write(question=question, plan=plan, store=result.store, gaps=gaps)
        except WriterError as exc:
            return self._fail(result, "write", exc)
        except Exception as exc:
            return self._fail(result, "write", exc)
        result.usage += result.report.usage
        result.timings["write"] = time.perf_counter() - started
        stage("write", "done")
        return result

    @staticmethod
    def _fail(result: PipelineResult, stage: str, exc: Exception) -> PipelineResult:
        message = f"{type(exc).__name__}: {exc}"
        result.stage_errors[stage] = message
        result.error = f"{stage}: {message}"
        return result
