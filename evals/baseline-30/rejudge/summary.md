# Independent re-judge

- questions: **30**
- model: `openai/gpt-oss-20b` (judge: `openai/gpt-oss-120b`)
- total tokens: **980,354**
- total time: **4258.0s**

| metric | value | 95% CI |
| --- | --- | --- |
| success rate | 80.0% | 66.7%-93.3% |
| claim support (supported + partial) | 94.0% | 86.1%-99.0% |
| strict claim support (supported only) | 73.1% | 62.7%-82.2% |
| keyword recall | 76.7% | 60.0%-90.0% |
| citation coverage | 81.3% | 67.7%-93.0% |
| citation precision (invariant) | 97.5% | 93.6%-100.0% |
| misconception hits | 0.0% | 0.0%-0.0% |
| writer repair turns | 40.0% | - |
| words / report | 294.2 | - |
| tokens / question | 32678.5 | 29242.4-36521.4 |
| seconds / question | 141.9 | 114.1-181.8 |
| cost / question | $0.0023 | - |

CI: cluster bootstrap over questions (2000 resamples, seed 7, 95%).

judged claims: supported 113, partial 31, unsupported 6, contradicted 0, unjudged 0

| category | n | success | support | tokens |
| --- | --- | --- | --- | --- |
| asyncio | 5 | 80% | 100% | 34135 |
| containers | 3 | 67% | 100% | 33154 |
| databases | 4 | 100% | 95% | 37819 |
| http | 4 | 75% | 75% | 25323 |
| performance | 3 | 100% | 100% | 31961 |
| python | 5 | 80% | 100% | 30485 |
| security | 3 | 67% | 80% | 40174 |
| testing | 3 | 67% | 100% | 29605 |

## Compared with the original run

| | original | re-judged |
| --- | --- | --- |
| judge model | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` |
| support rate (supported + partial) | 95.6% | 94.0% |
| strict support rate (supported only) | 81.1% | 73.1% |
| verdicts | supported 122, partial 26, unsupported 2, contradicted 0, unjudged 0 | supported 113, partial 31, unsupported 6, contradicted 0, unjudged 0 |

Only the support judge was replayed. Reports, citations, and token counts are unchanged; the re-judge's own token usage is reported separately.