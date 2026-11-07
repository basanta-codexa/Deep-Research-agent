# 30-question baseline

This directory is the frozen baseline used by the README and by later
ablations. It was produced by the full pipeline on **2026-11-07** with:

| setting | value |
| --- | --- |
| provider | `openrouter` |
| generation model | `openai/gpt-oss-20b` |
| in-run judge | `openai/gpt-oss-20b` (self-judged) |
| independent re-judge | `openai/gpt-oss-120b` |
| config | planner + parallel sub-agents, verify on, cache on |
| questions | 30, all categories |

## Results

The headline is the independent re-judge, not the self-judged number:

| metric | self-judged (20b) | independent (120b) | 95% CI (120b) |
| --- | ---: | ---: | ---: |
| success rate | 80.0% (24/30) | 80.0% | 66.7%-93.3% |
| strict support (supported only) | 81.1% | **73.1%** | 62.7%-82.2% |
| lenient support (supported + partial) | 95.6% | **94.0%** | 86.1%-99.0% |
| keyword recall | 76.7% | 76.7% | 60.0%-90.0% |
| citation coverage | 81.3% | 81.3% | 67.7%-93.0% |
| citation precision | 100.0% (invariant) | 97.5% | 93.6%-100.0% |
| misconception hits | 0.0% | 0.0% | 0.0%-0.0% |

Verdicts:

| judge | supported | partial | unsupported | contradicted | unjudged |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20b self | 122 | 26 | 2 | 0 | 0 |
| 120b re-judge | 113 | 31 | 6 | 0 | 0 |

The independent judge is stricter: 13 claims moved from *supported* to
*partial*, 4 *partial* claims were upgraded to *supported*, and 4 more *partial*
claims fell to *unsupported*. That is why the strict headline is **73.1%**, not
the 81.1% the run reports about itself.

Citation coverage is a generation-time property: the denominator is the evidence
the writer was allowed to cite. Re-judging support must not shrink that
denominator, otherwise coverage can exceed 100% when a cited claim is downgraded.
The re-judge implementation keeps the original denominator for exactly that
reason.

Cost and latency:

| metric | value |
| --- | ---: |
| total tokens | 980,354 |
| tokens / question | 32,678 |
| total wall clock | 4,258 s (71 min) |
| seconds / question | 141.9 |
| total cost | **$0.069** |
| cost / question | $0.0023 |

Citation precision is the one metric that is 100% by construction in a normal
run: the writer can only cite ids that already passed quote-in-page verification.
The 97.5% above is the independent judge saying that 6 of the 150 cited claims
were not supported. Both numbers are kept because they answer different
questions.

## The six failures

24 of 30 reports published. The failures are part of the result, not hidden:

| question | failure | fix |
| --- | --- | --- |
| `asyncio-run-entrypoint` | writer returned an empty draft after two truncated reasoning completions | commit `762051c`: writer requests `reasoning_effort=low`, so hidden reasoning no longer eats the output budget; fixed |
| `k8s-probe-types` | same empty-draft failure | same low-reasoning fix; the rerun then hit an uncited comparison table, so `64fa956` bans markdown tables and requires cited prose; fixed |
| `security-password-hashing` | same empty-draft failure | same low-reasoning fix; fixed |
| `python-iterable-iterator-generator` | same empty-draft failure | same low-reasoning fix; the baseline evidence set also had only iterator/generator records and no definition of *iterable*. `8da9d00` now names sub-questions with no extracted evidence and tells the writer to omit them and record the gap under Limitations. The rerun's uncited table was fixed by `64fa956`; fixed |
| `pytest-fixture-scope` | two uncited paragraphs in synthesis prose | the same `reasoning_effort=low` rerun passes the checks; fixed |
| `http-conditional-get` | pipeline timeout at 600 s while a sub-agent was inside a tool call | commit `762051c`: every tool call is now bounded by `tool_timeout` (60 s); fixed |

`evals.rejudge` skips records with no evidence at all instead of aborting the
whole run. The timed-out question has no `evidence.json`, so its record is left
unchanged and the skip is listed in `rejudge/summary.json`.

## Post-fix rerun

The six failures were re-run on the fixed pipeline. All **6/6** now publish:

| metric | self-judged (20b) | independent (120b) | 95% CI (120b) |
| --- | ---: | ---: | ---: |
| success rate | 100.0% | 100.0% | 100.0%-100.0% |
| strict support | 88.5% | **86.8%** | 73.5%-97.6% |
| lenient support | 98.3% | **96.7%** | 90.0%-100.0% |
| citation coverage | 100.0% | 100.0% | 100.0%-100.0% |
| citation precision | 100.0% (invariant) | 97.1% | 92.9%-100.0% |
| keyword recall | 100.0% | 100.0% | 100.0%-100.0% |

The independent judge saw 30 supported, 4 partial, 2 unsupported, 0 contradicted
of 36 claims. The repair set cost 207,318 tokens, 741.9 s and $0.0143 total
($0.0024 per question).

This is a repair check, not a new baseline: the six questions were selected
because they failed, so their success rate is not comparable to the 30-question
sample. The frozen baseline above is what later ablations compare against.

One Windows-specific artifact bug also surfaced here: writing a record could hit
a transient `PermissionError` while OneDrive had the target file open. Commit
`7fab278` retries the atomic replace, so a completed run cannot lose its summary
on a Windows indexer race.

## Reproduce

```powershell
$env:RA_PROVIDER='openrouter'
$env:RA_MODEL='openai/gpt-oss-20b'
$env:RA_JUDGE_MODEL='openai/gpt-oss-20b'
.\venv\Scripts\python.exe -m evals.run --all --out evals/runs/baseline-30 --concurrency 2 --timeout 600 --verbose
$env:RA_PROVIDER='openrouter'
.\venv\Scripts\python.exe -m evals.rejudge evals/runs/baseline-30 --judge-model openai/gpt-oss-120b
```

The raw run is also kept in the gitignored `evals/runs/baseline-30/` during
development. This directory is the published copy: it contains every
`record.json`, `report.md`, `evidence.json`, `plan.json`, `trace.json`,
`trace.html`, and the separate `rejudge/` output.

## Why this baseline exists

The public number is not "100% citation precision". It is:

> 73.1% of claims were strictly supported by their quote under an independent
> 120b judge, with a 95% interval of 62.7%-82.2%, on a 30-question sample.

The interval is wide, six questions failed, and one exposed a research gap: the
baseline evidence for *iterable* contained only iterator/generator records.
Those are the facts a regression comparison needs.
