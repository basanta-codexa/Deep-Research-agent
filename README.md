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
| 11 | Tracing + cost | next |
| 12 | Ablations | |
| 13 | Packaging + CI | |
| 14 | README with real numbers | |

See [ROADMAP.md](ROADMAP.md) for the full plan.

## Quickstart

```bash
ollama serve                  # only needed for the local provider
cp .env.example .env          # then set RA_PROVIDER and a key if using a hosted one
.\venv\Scripts\python.exe -m examples.step5_planner
```

## Config

All via environment variables (prefix `RA_`) or a local `.env` (gitignored; real
env vars win). `.env.example` documents the minimum.

| Var | Default | Meaning |
| --- | --- | --- |
| `RA_PROVIDER` | `ollama` | `ollama`, `groq`, or `openai` |
| `RA_MODEL` | per provider | model name |
| `RA_JUDGE_MODEL` | per provider | cheaper model for classification calls (support judging); empty = same as `RA_MODEL` |
| `RA_BASE_URL` | per provider | server URL |
| `RA_API_KEY` | – | key for hosted providers |
| `GROQ_API_KEY` | – | used automatically when `RA_PROVIDER=groq` |
| `RA_TEMPERATURE` | `0.2` | sampling temperature |
| `RA_MAX_TOKENS` | provider default | output cap |
| `RA_THINK` | `false` | stream reasoning tokens (Ollama) |
| `RA_NUM_CTX` | `8192` | Ollama context window |
| `RA_CACHE_TTL` | `86400` | seconds a cached page/search stays fresh |
| `RA_TIMEOUT` | `20` | per-request network timeout |

## Evals

30 questions across 8 software-engineering categories, run through the full
pipeline (plan → research → verify → write).

```bash
.\venv\Scripts\python.exe -m evals.run --dry-run          # show the dataset
.\venv\Scripts\python.exe -m evals.run --sample 10 --seed 7
.\venv\Scripts\python.exe -m evals.run --all              # the whole set
.\venv\Scripts\python.exe -m evals.compare evals/runs/a/summary.json evals/runs/b/summary.json
```

`evals.compare` exits non-zero when a regression is detected (citation precision
below 1.0, any unsupported citation, or a drop in success/support rate), so it
can gate CI once step 13 wires it up.

### Last run: 10-question sample (`--sample 10 --seed 7`)

| | |
| --- | --- |
| published | 9/10 reports, 0 errors |
| claim support | 61/61 judged (44 supported, 17 partial, 0 unsupported, 0 contradicted, 1 unjudged) |
| citations | 56, every one citable (precision 1.0) |
| citation coverage | 90% of citable evidence used |
| keyword recall | 90% (one report never used the term `Retry-After`) |
| misconception hits | 0 |
| cost | 22,419 tokens and 126 s per question (224,190 total, 21 minutes) |

The tenth report is why the eval exists. It typeset citations with full-width
brackets (`【ev_…】`); the ASCII extractor saw no ids, so it published with zero
machine-readable citations while every check still passed. Citations are now
normalised at the boundary and a draft with no ids is a hard `no_citations`
error, with regression tests on both.

Reported per run:

| Metric | What it means |
| --- | --- |
| success rate | report published, checks passed, at least one citation |
| claim support | share of judged claims the quote actually supports |
| citation precision | **invariant**, micro-averaged over citations, must stay 1.0 |
| citation coverage | share of citable evidence the report used |
| keyword recall | proxy for coverage: expected terms present in the prose |
| misconception hits | known-wrong phrases present, negation-aware |
| tokens / seconds | cost and latency per question |

Rates are macro (per question, then averaged), so one long run cannot hide ten
short failures. Citation precision is the exception — micro-averaged, because a
report that cited nothing has no precision; that failure shows up in success
rate instead. Every run writes `summary.json` and `summary.md`, plus
`report.md`, `evidence.json` and `plan.json` per question under `evals/runs/`.

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
the regression gate, and per-question timeouts in the eval harness.
