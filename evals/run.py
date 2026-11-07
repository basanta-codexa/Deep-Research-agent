"""Run the eval set.

    .\\venv\\Scripts\\python.exe -m evals.run --dry-run
    .\\venv\\Scripts\\python.exe -m evals.run --limit 3
    .\\venv\\Scripts\\python.exe -m evals.run --category asyncio
    .\\venv\\Scripts\\python.exe -m evals.run --all --out evals/runs/full

Every run writes `summary.json` (machine) and `summary.md` (human) plus one
folder per question with the report, the evidence store and the plan. The
artifact is the point: a number you cannot re-derive from files is a rumour.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from research_agent.config import Settings
from research_agent.llm import create_client
from research_agent.pipeline import PipelineConfig, PipelineResult, ResearchPipeline
from research_agent.retrieval.cache import NullCache
from research_agent.tools.web import make_subagent_tools

from .dataset import EvalItem, category_counts, load_dataset
from .harness import load_record, run_item, write_artifacts, write_item
from .metrics import RunRecord, summarize, to_markdown

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the research eval set.")
    parser.add_argument("--dataset", default=None, help="path to dataset.jsonl")
    parser.add_argument("--limit", type=int, default=3, help="first N questions (0 = all)")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="random N questions across all categories (reproducible with --seed)",
    )
    parser.add_argument("--seed", type=int, default=7, help="sampling seed")
    parser.add_argument("--all", action="store_true", help="run the whole dataset")
    parser.add_argument("--category", default=None, help="only this category")
    parser.add_argument(
        "--id",
        action="append",
        default=[],
        help="only these question ids (repeatable)",
    )
    parser.add_argument("--out", default=None, help="output directory")
    parser.add_argument("--concurrency", type=int, default=2, help="sub-agents in flight")
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds per question")
    parser.add_argument("--model", default=None, help="override the generation model")
    parser.add_argument("--judge-model", default=None, help="override the support judge")
    parser.add_argument("--no-verify", action="store_true", help="skip support judging")
    parser.add_argument(
        "--single-agent",
        action="store_true",
        help="skip the planner; one research thread for the whole question",
    )
    parser.add_argument("--no-cache", action="store_true", help="disable retrieval cache")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, no API calls")
    parser.add_argument("--verbose", action="store_true", help="print each pipeline stage")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse successful per-question records in --out; rerun failures/missing",
    )
    parser.add_argument(
        "--keep-failures",
        action="store_true",
        help="with --resume, keep failed records instead of rerunning them",
    )
    return parser.parse_args(argv)


def select_items(items: list[EvalItem], args: argparse.Namespace) -> list[EvalItem]:
    chosen = items
    if args.id:
        wanted = set(args.id)
        chosen = [item for item in chosen if item.id in wanted]
        missing = wanted - {item.id for item in chosen}
        if missing:
            raise SystemExit(f"unknown question id(s): {', '.join(sorted(missing))}")
    if args.category:
        chosen = [item for item in chosen if item.category == args.category]
        if not chosen:
            raise SystemExit(f"no questions in category {args.category!r}")
    if args.sample:
        # Random across the whole set, not the first N: the dataset is grouped by
        # category, so `--limit` alone would measure asyncio and nothing else.
        rng = random.Random(args.seed)
        chosen = list(chosen)
        rng.shuffle(chosen)
        return chosen[: args.sample]
    if not args.all and args.limit:
        chosen = chosen[: args.limit]
    return chosen


def apply_settings_overrides(
    settings: Settings, args: argparse.Namespace
) -> Settings:
    """Apply `--model` / `--judge-model` without mutating the environment."""
    if args.model:
        settings = replace(settings, model=args.model)
    if args.judge_model:
        settings = replace(settings, judge_model=args.judge_model)
    return settings


def make_pipeline(settings: Settings, args: argparse.Namespace) -> ResearchPipeline:
    client = create_client(settings)
    judge_client = create_client(settings.judge_settings())
    cache = NullCache() if args.no_cache else None
    return ResearchPipeline(
        client,
        make_subagent_tools(settings, cache=cache),
        judge_client=judge_client,
        config=PipelineConfig(
            concurrency=args.concurrency,
            max_steps=args.max_steps,
            verify=not args.no_verify,
            single_agent=args.single_agent,
        ),
    )


def reusable_record(
    directory: Path, item: EvalItem, *, keep_failures: bool = False
) -> RunRecord | None:
    """Return an existing record that can be reused by a resumed run.

    A failed row is re-run by default: free-tier failures are usually transient,
    and a baseline with holes is not a baseline. A question whose text changed
    never matches an old answer, even when the id did not change.
    """
    record = load_record(directory, item.id)
    if record is None or record.question != item.question:
        return None
    if record.ok or keep_failures:
        return record
    return None


def print_record(
    index: int, total: int, record: RunRecord, *, status: str | None = None
) -> None:
    support = record.support
    judged = sum(
        support.get(key, 0)
        for key in ("supported", "partial", "unsupported", "contradicted")
    )
    good = support.get("supported", 0) + support.get("partial", 0)
    rate = f"{good}/{judged}" if judged else "-"
    keywords = f"{len(record.keyword_hits)}/{len(record.keyword_hits) + len(record.keyword_misses)}"
    label = status or ("ok  " if record.ok else "FAIL")
    cost = (
        "cost n/a"
        if record.unpriced_models or record.cost_usd is None
        else f"${record.cost_usd:.4f}"
    )
    print(
        f"[{index:>2}/{total}] {record.item_id:<32} {label:<4} "
        f"support {rate:<5} cite {record.citations:<2} "
        f"kw {keywords:<4} {record.tokens_total:>6,} tok {cost:>9} "
        f"{record.duration_s:>6.1f}s",
        flush=True,
    )
    if not record.ok and record.error:
        print(f"        {record.error[:140]}", flush=True)


async def run(args: argparse.Namespace) -> int:
    items = select_items(load_dataset(args.dataset) if args.dataset else load_dataset(), args)

    print(f"dataset: {len(items)} question(s)")
    for category, count in category_counts(items).items():
        print(f"  {category:<12} {count}")

    if args.dry_run:
        for item in items:
            print(f"\n{item.id}  [{item.category}]")
            print(f"  {item.question}")
            if item.must_include:
                print(f"  must mention: {', '.join(item.must_include)}")
        return 0

    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path(args.out) if args.out else Path("evals/runs") / stamp
    if args.keep_failures and not args.resume:
        raise SystemExit("--keep-failures requires --resume")
    if args.resume:
        if not args.out:
            raise SystemExit("--resume requires --out <run directory>")
        if not out_dir.exists():
            raise SystemExit(f"--resume: {out_dir} does not exist")

    settings = apply_settings_overrides(Settings.from_env(), args)
    judge_model = settings.judge_settings().model
    print(f"\nprovider={settings.provider} model={settings.model} "
          f"judge={judge_model}")
    if judge_model == settings.model:
        print("warning: judge model equals generation model; support is self-judged")
    print(
        f"config: verify={not args.no_verify} "
        f"single_agent={args.single_agent} cache={not args.no_cache}"
    )

    pipeline = make_pipeline(settings, args)
    records: list[RunRecord] = []
    results: dict[str, PipelineResult] = {}
    skipped = 0

    def on_stage(item_id: str):
        if not args.verbose:
            return
        return lambda stage, state: print(
            f"        {item_id}: {stage} {state}", flush=True
        )

    started = time.perf_counter()
    try:
        for index, item in enumerate(items, 1):
            existing = (
                reusable_record(out_dir, item, keep_failures=args.keep_failures)
                if args.resume
                else None
            )
            if existing is not None:
                records.append(existing)
                skipped += 1
                print_record(index, len(items), existing, status="skip")
                continue
            record, result = await run_item(
                pipeline, item, timeout=args.timeout, on_stage=on_stage(item.id)
            )
            records.append(record)
            results[item.id] = result
            print_record(index, len(items), record)
            write_item(out_dir, item, result, record)
    finally:
        await pipeline.client.aclose()
        if pipeline.judge_client is not pipeline.client:
            await pipeline.judge_client.aclose()

    elapsed = time.perf_counter() - started
    summary = summarize(records)
    summary["provider"] = settings.provider
    summary["model"] = settings.model
    summary["judge_model"] = settings.judge_settings().model
    summary["concurrency"] = args.concurrency
    summary["max_steps"] = args.max_steps
    summary["timeout_s"] = args.timeout
    summary["resumed"] = skipped
    summary["verify"] = not args.no_verify
    summary["single_agent"] = args.single_agent
    summary["cache"] = not args.no_cache

    write_artifacts(out_dir, items, records, results, summary)
    (out_dir / "summary.md").write_text(
        to_markdown(summary, title=f"Eval run {stamp}"), encoding="utf-8"
    )

    print("\n" + to_markdown(summary, title="Summary"))
    if args.resume:
        print(f"resumed:     {skipped} kept, {len(records) - skipped} run")
    print(f"\nwall clock: {elapsed:.1f}s")
    print(f"artifacts:  {out_dir}")
    print(f"traces:     {out_dir}\\<question-id>\\trace.html")
    return 0 if summary["success_rate"] > 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
