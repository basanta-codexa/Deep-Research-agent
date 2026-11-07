# Post-fix repair run (6 questions)

This is a targeted rerun of the six questions that failed the frozen
30-question baseline. It is evidence that the fixes worked, **not** a new
baseline: the questions were selected because they failed, so the 100% success
rate is not comparable to the 30-question sample.

| setting | value |
| --- | --- |
| provider | `openrouter` |
| generation model | `openai/gpt-oss-20b` |
| in-run judge | `openai/gpt-oss-20b` |
| independent re-judge | `openai/gpt-oss-120b` |
| questions | `asyncio-run-entrypoint`, `http-conditional-get`, `k8s-probe-types`, `python-iterable-iterator-generator`, `security-password-hashing`, `pytest-fixture-scope` |

## Results

| metric | self-judged (20b) | independent (120b) | 95% CI (120b) |
| --- | ---: | ---: | ---: |
| success rate | 100.0% (6/6) | 100.0% | 100.0%-100.0% |
| strict support | 88.5% | **86.8%** | 73.5%-97.6% |
| lenient support | 98.3% | **96.7%** | 90.0%-100.0% |
| citation coverage | 100.0% | 100.0% | 100.0%-100.0% |
| citation precision | 100.0% (invariant) | 97.1% | 92.9%-100.0% |
| keyword recall | 100.0% | 100.0% | 100.0%-100.0% |
| misconception hits | 0.0% | 0.0% | 0.0%-0.0% |

Verdicts (36 claims):

| judge | supported | partial | unsupported | contradicted | unjudged |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20b self | 31 | 4 | 1 | 0 | 0 |
| 120b re-judge | 30 | 4 | 2 | 0 | 0 |

Cost and latency:

| metric | value |
| --- | ---: |
| total tokens | 207,318 |
| tokens / question | 34,553 |
| total wall clock | 741.9 s |
| seconds / question | 123.6 |
| total cost | $0.0143 |
| cost / question | $0.0024 |

## Fixes exercised

| commit | change |
| --- | --- |
| `762051c` | writer requests `reasoning_effort=low`; every tool call has a 60 s timeout |
| `8da9d00` | writer is told which sub-questions have no extracted evidence and must omit them / record the gap |
| `7fab278` | writer cites list items; eval JSON writes retry a transient Windows `PermissionError` |
| `64fa956` | writer writes cited prose instead of markdown tables |

## Reproduce

```powershell
$env:RA_PROVIDER='openrouter'
.\venv\Scripts\python.exe -m evals.run --resume `
  --id http-conditional-get `
  --id asyncio-run-entrypoint `
  --id k8s-probe-types `
  --id python-iterable-iterator-generator `
  --id security-password-hashing `
  --id pytest-fixture-scope `
  --out evals/runs/fixes-6 --concurrency 2 --timeout 600 --verbose
.\venv\Scripts\python.exe -m evals.rejudge evals/runs/fixes-6 `
  --judge-model openai/gpt-oss-120b
```

The raw run lives in the gitignored `evals/runs/fixes-6/` during development.
This directory is the published copy, including the separate `rejudge/` output.
