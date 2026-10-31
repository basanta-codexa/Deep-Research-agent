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
| 9 | Claim verifier | next |
| 10 | Eval harness | |
| 11 | Tracing + cost | |
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
| `RA_BASE_URL` | per provider | server URL |
| `RA_API_KEY` | – | key for hosted providers |
| `GROQ_API_KEY` | – | used automatically when `RA_PROVIDER=groq` |
| `RA_TEMPERATURE` | `0.2` | sampling temperature |
| `RA_MAX_TOKENS` | provider default | output cap |
| `RA_THINK` | `false` | stream reasoning tokens (Ollama) |
| `RA_NUM_CTX` | `8192` | Ollama context window |
| `RA_CACHE_TTL` | `86400` | seconds a cached page/search stays fresh |
| `RA_TIMEOUT` | `20` | per-request network timeout |
