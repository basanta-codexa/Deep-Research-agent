# Deep Research Agent — Build Roadmap

## The thesis

Most "research agent" projects are a `while` loop wrapped around a search API. They look
impressive in a demo and fall apart under scrutiny, because nobody can tell whether the
report is *true*.

This project's thesis is **verifiable research**:

> Every claim in the final report is linked to a specific span of a specific source,
> and a machine checks that the span actually supports the claim.

That single constraint forces us to build the parts that are actually hard, and it is what
makes the project resume-worthy instead of a weekend demo:

| What everyone builds | What we build |
| --- | --- |
| "agent writes a report" | claim → source span → machine-verified support |
| one big prompt | planner + parallel sub-agents with token budgets |
| no evaluation | citation precision/recall, support rate, coverage, cost/latency |
| `print()` debugging | structured traces + a viewer |
| works only with one API | provider abstraction (local Ollama by default) |

## Architecture we're aiming at

```
                     ┌──────────────────────┐
   question ────────▶│      RESEARCHER      │
                     │  (orchestrator loop) │
                     └──────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
   ┌─────────┐            ┌────────────┐          ┌────────────┐
   │ Planner │            │ Sub-agent  │   ...    │ Sub-agent  │
   │ (splits │            │  (own ctx) │          │  (own ctx) │
   │  query) │            └─────┬──────┘          └─────┬──────┘
   └─────────┘                  │                       │
                                ▼                       ▼
                        ┌───────────────────────────────────┐
                        │  search → fetch → extract → note  │
                        └───────────────┬───────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │  Evidence Store  │  claim + span + url + score
                              └────────┬─────────┘
                                       ▼
                              ┌──────────────────┐
                              │  Writer + Verifier│
                              └────────┬─────────┘
                                       ▼
                            report.md + report.json + trace.json
```

## Phases

### Phase 0 — Foundations (steps 1–3)
Build the plumbing every later step depends on. Nothing user-visible yet, but this is where
most of the *engineering* lives.

| Step | Concept | Deliverable | You'll be able to explain |
| --- | --- | --- | --- |
| 1 | Provider abstraction | `LLMClient` interface + Ollama adapter | why SDKs leak, why you normalize message formats, token accounting |
| 2 | The agent loop | ReAct loop with stop conditions + step budget | why one big prompt fails, what ReAct actually is, why loops diverge |
| 3 | Tool registry | `@tool` decorator, JSON-schema from signatures, validation | why schemas must be generated not hand-written, error text as model feedback |

### Phase 1 — Retrieval (steps 4–7)
Getting good text into the system, cheaply.

| Step | Concept | Deliverable | You'll be able to explain |
| --- | --- | --- | --- |
| 4 | Search + fetch + extract | pluggable search, readability-style extraction, SQLite cache | idempotency, rate limits, why raw HTML is unusable |
| 5 | Planning | query decomposition into sub-questions | static vs dynamic planning, over/under-decomposition |
| 6 | Sub-agents | fan-out with isolated context + token budgets | context rot, why sub-agents exist, worst-case cost math |
| 7 | Evidence store | structured notes: claim, quote, url, span offsets | why raw text in context is a liability |

### Phase 2 — Synthesis (steps 8–9)
Turning evidence into a report that survives scrutiny.

| Step | Concept | Deliverable | You'll be able to explain |
| --- | --- | --- | --- |
| 8 | Writer | report with inline citations, claim↔source mapping | grounding, hallucinated citations, structured output |
| 9 | Verifier | LLM-judge + string-overlap checks, contradiction detection | NLI, judge bias, why verification is its own agent |

### Phase 3 — Proof (steps 10–12)
This is the part 95% of side projects skip, and the part interviewers ask about.

| Step | Concept | Deliverable | You'll be able to explain |
| --- | --- | --- | --- |
| 10 | Evals | dataset of ~30 questions, metric code, regression runs | why "it looked good" is not evidence, metric design |
| 11 | Observability | spans, token/cost accounting, `trace.json` + HTML viewer | where the tokens went, latency attribution |
| 12 | Tuning | ablations: single-agent vs multi-agent, model A vs B | empirical claims, not vibes |

### Phase 4 — Ship (steps 13–14)

| Step | Concept | Deliverable | You'll be able to explain |
| --- | --- | --- | --- |
| 13 | Packaging | `pyproject.toml`, pytest suite, GitHub Actions, Docker | reproducible builds, test pyramid for LLM apps |
| 14 | Story | README with real numbers, demo recording, design doc | how to present engineering work |

## Resume bullets we are building toward

Numbers are placeholders — step 10 fills them in with real measurements.

- Built a multi-agent research system in Python with a provider-agnostic LLM layer
  (local Ollama + OpenAI-compatible), ~N LOC, fully offline-capable.
- Designed a claim-level verification pipeline that links every sentence to a source span;
  achieved **XX% claim-support rate** and **YY% citation precision** on a 30-question eval set.
- Cut cost per report by **ZZ%** via parallel sub-agents with per-agent token budgets and
  cached retrieval.
- Added structured tracing + eval harness; caught a **WW pt** regression from prompt changes
  that manual review missed.

## Honest notes

- A 4B local model will be a weak agent. That is *useful*: you will see failures concretely
  and learn why evals, retries and constraints exist. Demos switch to a stronger model via
  config, not code changes.
- We write everything from scratch first (no LangChain / CrewAI), then you can compare. You
  cannot debug a framework whose loop you've never implemented.
