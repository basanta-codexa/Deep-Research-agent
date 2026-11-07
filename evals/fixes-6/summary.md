# Eval run 2026-11-07T14-41-10

- questions: **6**
- model: `openai/gpt-oss-20b` (judge: `openai/gpt-oss-20b`)
- total tokens: **207,318**
- total time: **741.9s**

| metric | value | 95% CI |
| --- | --- | --- |
| success rate | 100.0% | 100.0%-100.0% |
| claim support (supported + partial) | 98.3% | 95.0%-100.0% |
| strict claim support (supported only) | 88.5% | 77.5%-97.6% |
| keyword recall | 100.0% | 100.0%-100.0% |
| citation coverage | 100.0% | 100.0%-100.0% |
| citation precision (invariant) | 100.0% | 100.0%-100.0% |
| misconception hits | 0.0% | 0.0%-0.0% |
| writer repair turns | 50.0% | - |
| words / report | 496.0 | - |
| tokens / question | 34553.0 | 29865.1-39373.7 |
| seconds / question | 123.6 | 82.4-189.1 |
| cost / question | $0.0024 | - |

CI: cluster bootstrap over questions (2000 resamples, seed 7, 95%).

judged claims: supported 31, partial 4, unsupported 1, contradicted 0, unjudged 0

| category | n | success | support | tokens |
| --- | --- | --- | --- | --- |
| asyncio | 1 | 100% | 90% | 43436 |
| containers | 1 | 100% | 100% | 30476 |
| http | 1 | 100% | 100% | 31216 |
| python | 1 | 100% | 100% | 30418 |
| security | 1 | 100% | 100% | 43839 |
| testing | 1 | 100% | 100% | 27933 |