# Evals

The pipeline already checks itself: quotes are located in the fetched page, claims
are judged against those quotes, and the writer can only cite ids that passed
both gates. So why measure anything else?

Because those checks answer *"is this report internally consistent"*, not *"did
the system answer this question well, at what cost, and did my last change make
it worse"*. A single successful run is an anecdote. Thirty runs are a
distribution, and a distribution is what a regression test can compare against.

## What is measured, and what each metric can and cannot tell you

| Metric | Definition | What it cannot tell you |
| --- | --- | --- |
| `success_rate` | report published, checks passed, ≥1 citation | whether the answer is any good |
| `support_rate` | (supported + partial) ÷ judged claims | one judge's opinion; partial counts as support |
| `verified_rate` | quotes found in the fetched page ÷ findings | relevance: a real quote can still be off-topic |
| `citation_precision` | citable citations ÷ all citations, micro-averaged | **nothing** — it is 1.0 by construction; it is an invariant |
| `citation_coverage` | cited evidence ÷ citable evidence | whether the *right* evidence was used |
| `keyword_recall` | expected terms present ÷ expected terms | correctness: term present ≠ claim true |
| `misconception_rate` | questions whose report contains a known-wrong phrase | crude negation handling; phrase lists are incomplete |
| `repair_rate` | runs where the writer needed a constraint-driven rewrite | quality: a repair can still be a good report |
| `mean_tokens`, `mean_seconds` | token spend and latency per question | where the tokens went (see the trace) |
| `mean_cost_usd` | dollars per question from `research_agent/pricing.py` | what you *paid* — a free tier is genuinely `$0` |

Two consequences of that table:

1. **`citation_precision` is a tripwire, not a score.** Reporting "100% citation
   precision" as an achievement would be dishonest — the writer *cannot* emit a
   bad citation. It is in the summary to catch the day that stops being true.
2. **`keyword_recall` is a proxy.** The dataset stores the terms a competent
   answer would use, not the answer. It is cheap, deterministic and honest about
   being shallow. The per-claim support judge is the deeper signal.

## Dataset

`dataset.jsonl`, 30 questions across 8 categories (asyncio, http, databases,
python, testing, security, containers, performance). Each row:

```json
{"id": "asyncio-gather-failure",
 "question": "When one coroutine passed to asyncio.gather() raises ...",
 "category": "asyncio",
 "must_include": ["return_exceptions"],
 "must_not_include": ["all tasks are cancelled"],
 "notes": "The canonical misconception: gather propagates ..."}
```

`must_not_include` is matched with a small negation guard: only the clause
immediately before the phrase is inspected, so *"does not cancel"* does not count
as *"cancel"*. It is a heuristic, and `tests/test_eval.py` pins its behaviour.

## Running

```bash
python -m evals.run --dry-run                     # inspect the set, no API calls
python -m evals.run --sample 10 --seed 7          # reproducible random sample
python -m evals.run --all                         # full set (long, costs tokens)
python -m evals.run --category asyncio            # one category
python -m evals.run --id perf-benchmark-clock     # re-run one known failure
python -m evals.run --resume --out evals/runs/sample10   # keep finished rows
python -m evals.run --resume --keep-failures --out evals/runs/sample10
python -m evals.recompute evals/runs/sample10     # re-derive an old run's summary
python -m evals.rejudge evals/runs/sample10 --judge-model openai/gpt-oss-120b
python -m evals.compare base/summary.json cand/summary.json
```

A resumed run reuses every `record.json` whose question still matches. Failed
rows are re-run by default because free-tier failures are usually transient;
`--keep-failures` keeps them instead. `--resume` requires an explicit `--out`
so a typo cannot silently create a new run.

`evals.compare` exits 1 on regression: any unsupported citation, citation
precision below 1.0, or a drop in success/support rate. That is the hook for
CI and for the ablations in step 12. `evals.recompute` exists because metrics
change: old artifacts keep their per-question records, so the summary is a pure
function of data you already have — and fields the old run never measured stay
`n/a` instead of becoming a misleading 0.

`evals.rejudge` is the honesty check the default run cannot provide. It loads
the saved `evidence.json`, sends every verified claim/quote pair to a different
model, and writes a new summary under `<run>/rejudge/`. It never overwrites the
original run, never regenerates a report, and keeps the re-judge's own token
usage separate from generation cost. It replays support only, not the conflict
scan. If the re-judge model is the same as the generation model it warns: that
is still a self-judgement.

## Artifacts

```
evals/runs/<run>/
  summary.json          # summary + every RunRecord + the dataset used
  summary.md            # the table a human reads
  <question-id>/
    record.json         # RunRecord: status, support counts, cited ids, tokens
    report.md
    evidence.json       # every claim, quote, span, verdict, trust tier
    plan.json
    trace.json          # span tree: stages, sub-agents, LLM calls, tools
    trace.html          # self-contained waterfall; open it in a browser
  rejudge/              # optional: independent re-judge output
    summary.json
    summary.md
    rejudge.json        # per-question verdicts and reasons
```

`record.json` is written as soon as a question finishes, before `summary.json`.
That is what makes `--resume` possible, and it is what an offline re-judge will
use: `cited_ids` is persisted, so the cited claims can be scored again without
re-running the pipeline.

`trace.json` is the data and `trace.html` is a rendering of it. The HTML is the
fast way to answer "why did this question take 90 seconds": the waterfall shows
which sub-agent was still running while the others finished, and the token table
shows which stage actually spent the budget. Cost comes from the price table;
a model that is not in it is reported as *unpriced* (`n/a`), never as `$0`.

Each question is written as soon as it finishes, so an interrupted run keeps its
work. `--timeout` (default 300s) turns a hung provider call into a failed row
instead of a hung harness.

## Case study: the bug the first run found

The first 10-question run published 9 reports with valid citations and one with
**zero**. That report used full-width brackets (`【ev_…】`) instead of `[ev_…]`.
The extractor was ASCII-only, so it saw no ids; the writer renumbered nothing and
emitted an empty reference list. `check_draft` still passed, because its
"paragraph is cited" rule matched the bare `ev_` prefix rather than a bracketed
reference.

Three fixes, all regression-tested: look-alike brackets are normalised at the
boundary, an id-less draft is a hard `no_citations` error, and the eval gained
`--id` so a single failure can be re-run without paying for the whole suite.
This is the concrete argument for an eval harness: every unit test passed on the
day that report shipped.

## Known limits

- **Self-judging.** The pipeline's support verdicts come from the cheap judge
  model, and a normal run reports those same verdicts. Use `evals.rejudge` with
  a different model before treating the support rate as independent; the
  re-judge is only as independent as the second model.
- **Small n.** 30 questions is enough to see a 10-point regression, not enough
  for a 2-point one. Report confidence intervals before making fine-grained claims.
- **Provider variance.** Groq's free tier changes latency by 10× within an hour.
  Compare success/support across runs, not wall-clock.
- **One language, one domain.** All questions are software engineering in
  English. Nothing here proves the pipeline generalises.
