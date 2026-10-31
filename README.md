# research-agent

A deep research agent where **every claim is traceable to a source span and machine-checked**.

Provider-agnostic (local Ollama by default), built from scratch — no agent framework.

## Status

| Step | Piece | State |
| --- | --- | --- |
| 1 | LLM provider abstraction + Ollama adapter | done |
| 2 | Agent loop (ReAct) | done |
| 3 | Tool registry (schema from signature + pydantic validation) | done |
| 4 | Search / fetch / extract / cache | next |
| 5 | Planner | |
| 6 | Parallel sub-agents | |
| 7 | Evidence store | |
| 8 | Report writer | |
| 9 | Claim verifier | |
| 10 | Eval harness | |
| 11 | Tracing + cost | |
| 12 | Ablations | |
| 13 | Packaging + CI | |
| 14 | README with real numbers | |

See [ROADMAP.md](ROADMAP.md) for the full plan.

## Quickstart

```bash
ollama serve                  # in one terminal
.\\venv\\Scripts\\python.exe -m examples.step1_chat
```

## Config

All via environment variables (prefix `RA_`):

| Var | Default | Meaning |
| --- | --- | --- |
| `RA_PROVIDER` | `ollama` | `ollama` or `openai` |
| `RA_MODEL` | `qwen3.5:4b` | model name |
| `RA_BASE_URL` | provider default | server URL |
| `RA_API_KEY` | – | key for hosted providers |
| `RA_TEMPERATURE` | `0.2` | sampling temperature |
| `RA_MAX_TOKENS` | unlimited | output cap |
| `RA_THINK` | `false` | stream reasoning tokens |
