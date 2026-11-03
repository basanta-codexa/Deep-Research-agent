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
| `mean_tokens`, `mean_seconds` | cost and latency per question | price, on a free tier |

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
python -m evals.recompute evals/runs/sample10     # re-derive an old run's summary
python -m evals.compare base/summary.json cand/summary.json
```

`evals.compare` exits 1 on regression: any unsupported citation, citation
precision below 1.0, or a drop in success/support rate. That is the hook for
CI and for the ablations in step 12. `evals.recompute` exists because metrics
change: old artifacts keep their per-question records, so the summary is a pure
function of data you already have — and fields the old run never measured stay
`n/a` instead of becoming a misleading 0.

## Artifacts

```
evals/runs/<run>/
  summary.json          # summary + every RunRecord + the dataset used
  summary.md            # the table a human reads
  <question-id>/
    report.md
    evidence.json       # every claim, quote, span, verdict, trust tier
    plan.json
```

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
  model, and the eval reports those same verdicts. An independent re-judge with
  the stronger model is the obvious next step (see the exercises in step 10).
- **Small n.** 30 questions is enough to see a 10-point regression, not enough
  for a 2-point one. Report confidence intervals before making fine-grained claims.
- **Provider variance.** Groq's free tier changes latency by 10× within an hour.
  Compare success/support across runs, not wall-clock.
- **One language, one domain.** All questions are software engineering in
  English. Nothing here proves the pipeline generalises.
