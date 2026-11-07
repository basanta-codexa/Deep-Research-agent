# Ablations

The baseline answers *"does it work?"*. Ablations answer *"which part is doing
the work?"* Each configuration runs the same 30 questions, with the same
provider, model, timeout and question-level judge. The only deliberate
difference is the feature under test.

## Design

| run | command | question |
| --- | --- | --- |
| control | `evals.run --all` | current full pipeline |
| single-agent | `--single-agent` | does planning + parallel sub-agents beat one research thread? |
| no-verify | `--no-verify` | what does claim verification cost, and what does it buy? |
| no-cache | `--no-cache` | how much of the latency is retrieval caching? |

The model-override ablation is reported separately because it changes the judge
as well as the generator; a same-model judge cannot be called independent.

All runs use OpenRouter and `openai/gpt-oss-20b` unless stated otherwise. The
control and the cached ablations share the warm retrieval cache; `--no-cache`
bypasses it. Support verdicts are replayed with `openai/gpt-oss-120b` so the
comparison is not self-judged. The no-verifier run skips generation-time
verification but is still re-judged offline, so it has a quality number; what it
lacks is the verifier's feedback to the writer, not a measurement.

The control is generated with the post-fix code, not the frozen baseline. The
baseline's writer could return empty drafts and its tables/lists were harder to
audit; comparing ablations to it would mix the feature effect with those fixes.
The frozen baseline remains the historical reference, while these runs isolate
one feature at a time against the same code.

One run per configuration is enough to expose a large effect, not to estimate a
small one. These are 30-question point estimates with intervals; treat a
non-overlapping interval as suggestive and a paired delta as the stronger
evidence. The LLM itself is stochastic, so a single rerun is not a variance
study.

## Metrics

- success rate: published, machine-checked report with at least one citation
- strict support: supported claims / judged claims (partial is not a pass)
- lenient support: (supported + partial) / judged claims
- citation coverage: cited evidence / evidence the writer was allowed to cite
- keyword recall: expected terms present in the report
- cost and latency per question

Intervals are 95% cluster-bootstrap intervals over questions (2,000 resamples,
seed 7). An overlap between two intervals is not a significance test; paired
deltas are computed over the same questions and reported when they are useful.

## Run plan

```powershell
$env:RA_PROVIDER='openrouter'
$env:RA_MODEL='openai/gpt-oss-20b'
$env:RA_JUDGE_MODEL='openai/gpt-oss-20b'

.\venv\Scripts\python.exe -m evals.run --all --out evals/runs/full-postfix --concurrency 2 --timeout 600
.\venv\Scripts\python.exe -m evals.run --all --single-agent --out evals/runs/single-agent --concurrency 2 --timeout 600
.\venv\Scripts\python.exe -m evals.run --all --no-verify --out evals/runs/no-verify --concurrency 2 --timeout 600
.\venv\Scripts\python.exe -m evals.run --all --no-cache --out evals/runs/no-cache --concurrency 2 --timeout 600

# Independent support replay for every run, including no-verify.
foreach ($run in 'full-postfix','single-agent','no-verify','no-cache') {
  .\venv\Scripts\python.exe -m evals.rejudge "evals/runs/$run" --judge-model openai/gpt-oss-120b
}
```

Compare each candidate to the control with the paired bootstrap:

```powershell
.\venv\Scripts\python.exe -m evals.ablation_stats `
  evals/runs/full-postfix/rejudge/summary.json `
  evals/runs/single-agent/rejudge/summary.json
```

The script aligns questions by id, resamples the paired differences, and reports
percentage-point deltas for quality metrics and relative deltas for latency,
tokens and cost. The control is `full-postfix`, not the frozen baseline.

## Results

Populated after the runs. Raw summaries are in the gitignored
`evals/runs/<name>/summary.json`; published copies and the analysis table will
be added here.
