# research-agent

A deep research agent where **every claim is traceable to a source span and machine-checked**.

Provider-agnostic (local Ollama by default), built from scratch — no agent framework.

## Status

| Step | Piece | State |
| --- | --- | --- |
| 1 | LLM provider abstraction + Ollama adapter | done |
| 2 | Agent loop (ReAct) | done |
| 3 | Tool registry (schema from signature + pydantic validation) | done |
| 4 | Real retrieval: search, fetch, extract, cache, SSRF guard | done |
| 5 | Planner (query decomposition) | done |
| 6 | Parallel sub-agents (two-phase reader/extractor) | done |
| 7 | Evidence store (dedupe + span verification) | done |
| 8 | Report writer (citation-closed prose) | done |
| 9 | Claim verifier (support + contradiction scan + trust tiers) | done |
| 10 | Eval harness (30-question set, metrics, artifacts) | done |
| 11 | Tracing + cost (spans, waterfall, token attribution) | done |
| 11b | Live web UI (FastAPI + SSE, citation spotlight) | done |
| 12 | Ablations | next |
| 13 | Packaging + CI | |
| 14 | README with real numbers | done |

See [ROADMAP.md](ROADMAP.md) for the full plan.

## Quickstart

```bash
.\venv\Scripts\python.exe -m pip install -r requirements.txt
ollama serve                  # only needed for the local provider
cp .env.example .env          # then set RA_PROVIDER and a key if using a hosted one
.\venv\Scripts\python.exe -m examples.step5_planner
```

## Live web UI

```bash
.\venv\Scripts\python.exe -m web.server
# open http://127.0.0.1:8000
```

Type a question and watch the run stream in: the plan's sub-questions, each
sub-agent's tool calls and sources, evidence and verdict counts, then the
writing stage. Plain HTML/CSS/JS — no build step, no framework, no CDN.

![A finished run: plan, sub-agents, tool calls, failed fetch, and stats](docs/web-run.png)

The screenshots are a real run (`openai/gpt-oss-20b`, free tier): 2m 8s,
26 model calls, 25,011 tokens, 4/4 cited claims judged supported, and one
`read_source` tool call that timed out and is shown as an error instead of
being hidden.

![The finished report with clickable citation chips](docs/web-report.png)

Clicking a citation opens the page text the agent actually read and highlights
the stored quote at its exact character offsets:

![Source drawer with the exact quote highlighted at characters 24-285](docs/web-source.png)

That interaction is the project thesis. The span was computed when the evidence
was stored; the browser receives `{start, end}` and paints that range. It never
searches the page for the quote, so a wrong span would be visibly wrong instead
of silently plausible.

How it is wired:

* `Tracer` accepts listeners. The SSE endpoint subscribes to span start/end and
  pushes events into a queue, so the UI required no callbacks in planning,
  research, verification or writing.
* Stage spans carry semantic attributes (sub-questions, findings, verdict
  counts, word/citation counts). The timeline renders what the trace already
  records; the UI is a second reader of the same data as `trace.json`.
* One consumer loop with result/error sentinels, so "queue is empty" never
  means "still thinking". A timeout cancels the runner and emits the partial
  trace instead of hanging the browser.
* `create_app(pipeline=...)` accepts a fake pipeline, so the UI's tests run
  offline with no API key.

A run is hard-stopped at `RA_WEB_TIMEOUT` seconds (default 360). The timeout
cancels the runner and returns the partial trace, so a slow model produces a
diagnosable error instead of a hung page. If the server itself is restarted
mid-run, the page says the connection closed and shows how many events arrived
and which one was last — it does not claim the run produced no report.

## Config

All via environment variables (prefix `RA_`) or a local `.env` (gitignored; real
env vars win). `.env.example` documents the minimum.

| Var | Default | Meaning |
| --- | --- | --- |
| `RA_PROVIDER` | `ollama` | `ollama`, `groq`, `openai`, or `openrouter` |
| `RA_MODEL` | per provider | model name |
| `RA_JUDGE_MODEL` | per provider | cheaper model for classification calls (support judging); empty = same as `RA_MODEL` |
| `RA_BASE_URL` | per provider | server URL |
| `RA_API_KEY` | – | key for hosted providers |
| `GROQ_API_KEY` | – | used automatically when `RA_PROVIDER=groq` |
| `OPENROUTER_API_KEY` | – | used automatically when `RA_PROVIDER=openrouter` |
| `RA_TEMPERATURE` | `0.2` | sampling temperature |
| `RA_MAX_TOKENS` | provider default | output cap |
| `RA_THINK` | `false` | stream reasoning tokens (Ollama) |
| `RA_NUM_CTX` | `8192` | Ollama context window |
| `RA_CACHE_TTL` | `86400` | seconds a cached page/search stays fresh |
| `RA_TIMEOUT` | `20` | per-request network timeout |
| `RA_WEB_TIMEOUT` | `360` | wall-clock budget for one web-UI run, in seconds |
| `RA_PRICE_INPUT` | – | USD per 1M prompt tokens; overrides the built-in price table |
| `RA_PRICE_OUTPUT` | – | USD per 1M completion tokens; must be set with the input price |

## Evals

30 questions across 8 software-engineering categories, run through the full
pipeline (plan → research → verify → write).

```bash
.\venv\Scripts\python.exe -m evals.run --dry-run          # show the dataset
.\venv\Scripts\python.exe -m evals.run --sample 10 --seed 7
.\venv\Scripts\python.exe -m evals.run --all              # the whole set
.\venv\Scripts\python.exe -m evals.run --all --single-agent --out evals/runs/no-planner
.\venv\Scripts\python.exe -m evals.run --all --no-verify --out evals/runs/no-verify
.\venv\Scripts\python.exe -m evals.run --all --no-cache --out evals/runs/no-cache
.\venv\Scripts\python.exe -m evals.run --resume --out evals/runs/sample10
.\venv\Scripts\python.exe -m evals.compare evals/runs/a/summary.json evals/runs/b/summary.json
```

Each question writes `record.json` as soon as it finishes, so `--resume` keeps
finished rows and re-runs failures or missing questions. A changed question
invalidates its old record. `--keep-failures` keeps failed rows instead.

The ablation flags are explicit and recorded in `summary.json`: `--single-agent`
skips the planner and uses one research thread; `--no-verify` skips support
judging but keeps the quote-in-page gate; `--no-cache` disables retrieval
caching. With `--no-verify`, support is `n/a`, not `0%`; use `evals.rejudge`.

`evals.compare` exits non-zero when a regression is detected (citation precision
below 1.0, any unsupported citation, or a drop in success/support rate), so it
can gate CI once step 13 wires it up.

Support verdicts are self-judged by default. Before quoting them, replay them
with a different model: `python -m evals.rejudge evals/runs/<run> --judge-model <model>`.
It writes a separate `<run>/rejudge/` summary and leaves the original untouched.

### Baseline: 30 questions (`--all`)

Published artifacts: [`evals/baseline-30/`](evals/baseline-30/).

| | |
| --- | --- |
| generation | `openai/gpt-oss-20b` via OpenRouter |
| published | **24/30** reports, 6 failures |
| self-judged support (20b) | 95.6% lenient / 81.1% strict |
| independent re-judge (120b) | **94.0% lenient / 73.1% strict** |
| 95% CI, strict (120b) | 62.7%-82.2% |
| verdicts (120b) | 113 supported, 31 partial, 6 unsupported, 0 contradicted |
| citations | 150 cited claims; 6 judged unsupported by 120b; judge-based precision 97.5% |
| keyword recall / coverage | 76.7% / 81.3% |
| misconception hits | 0 |
| budget | 32,678 tokens, 142 s, $0.0023 per question (71 min, $0.069 total) |

The independent judge is the headline: **73.1%** of claims were strictly
supported by the quote the report cited, not the 81.1% the run reports about
itself. The wide interval is honest: 30 questions can show a large regression,
not a two-point one.

Six questions failed, and all six are documented rather than dropped: four
writer empty drafts caused by hidden reasoning consuming the output budget, one
600 s research timeout caused by an unbounded tool call, and one report whose
prose went beyond its evidence. The writer now requests low reasoning effort,
every tool call has a 60 s bound, and `evals.rejudge` skips records with no
evidence instead of aborting the run.

A targeted rerun of those six with the fixes published **6/6** reports
([`evals/fixes-6/`](evals/fixes-6/)). The independent 120b judge put strict
support on that repair set at **86.8%** (73.5%-97.6% CI) over 36 claims, with 2
unsupported. The repair set is a check that the fixes worked, not a replacement
for the frozen 30-question baseline.

The earlier 10-question sample is still useful for one reason: it caught the
full-width-bracket bug. One report typeset `【ev_…】`, the ASCII extractor saw no
ids, and it shipped with zero machine-readable citations while every check
passed. Citations are now normalised at the boundary and a draft with no ids is
a hard `no_citations` error, with regression tests on both.

Reported per run:

| Metric | What it means |
| --- | --- |
| success rate | report published, checks passed, at least one citation |
| claim support | share of judged claims the quote supports, counting partial |
| strict claim support | share of judged claims the quote fully supports |
| citation precision | **invariant**, micro-averaged over citations, must stay 1.0 |
| citation coverage | share of citable evidence the report used |
| keyword recall | proxy for coverage: expected terms present in the prose |
| misconception hits | known-wrong phrases present, negation-aware |
| tokens / seconds | cost and latency per question |

Rates are macro (per question, then averaged), so one long run cannot hide ten
short failures. They carry 95% cluster-bootstrap intervals over questions
(2,000 resamples); with n=30 those intervals are wide, and that is the point.
Citation precision is the exception — micro-averaged, because a
report that cited nothing has no precision; that failure shows up in success
rate instead. Every run writes `summary.json` and `summary.md`, plus
`report.md`, `evidence.json`, `plan.json`, `trace.json` and `trace.html` per
question under `evals/runs/`.

## Tracing & cost

A report says what the agent concluded. A trace says how it got there. Every run
builds a span tree — `pipeline → plan/research/verify/write → sub-agent → LLM
call or tool` — and writes it twice:

- `trace.json` — the data (one object per span, parent ids, start/duration,
  status, attributes, token usage, cost). Queryable and diffable.
- `trace.html` — a self-contained waterfall (no server, no CDN, no build step)
  with per-stage token tables, per-model cost, the critical path and the slowest
  calls. Double-click it.

Open a trace directly:

```python
from research_agent.pipeline import ResearchPipeline

result = await pipeline.run(question)
if result.trace is not None:
    result.trace.save_html("trace.html")
```

Attribution rules that keep the numbers honest:

- **Tokens are counted once.** Only LLM spans carry usage; stage totals roll up
  their nearest stage. Summing every span would double-count each call.
- **Unknown is not free.** A model missing from `research_agent/pricing.py`
  makes the cost `n/a` and names the model — it never quietly becomes `$0.00`.
  The Groq and Ollama entries are genuinely `0.0` (free tier / local), which is
  a different statement from "we don't know".
- **The critical path is a chain, not a call.** With parallel sub-agents, the
  long pole is root → the child that ends last → its slowest child. That is what
  to optimise; the slowest single call may be sitting off the critical path.

Prices are what *this deployment* pays, not vendor list prices; override them
with `RA_PRICE_INPUT` / `RA_PRICE_OUTPUT` (USD per 1M tokens) when you move to a
paid tier.

## Tests

```bash
.\venv\Scripts\python.exe -m pytest tests -q
```

The suite is deterministic and offline: no API key, no network. The LLM is
replaced by a scripted fake client wherever a model would otherwise be called.
It covers quote location (exact / normalized / fragment / missing), dedupe,
the citable gate, draft checks (including full-width brackets and a draft with
no citations), citation renumbering, failure-to-verdict mapping, the fail-closed
path when a judge call errors, the JSON-mode fallback ladder, metric arithmetic,
the regression gate, per-question timeouts in the eval harness, span nesting
(including concurrent tasks), token attribution without double counting, the
critical path, pricing/override math, and HTML escaping of model output.
