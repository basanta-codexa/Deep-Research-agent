# Requirements for Functions Decorated by `contextlib.contextmanager`

## Summary
`contextlib.contextmanager` requires the decorated function to be a generator that yields exactly one value, which will be bound to the target of the `with` statement. The evidence does not provide additional details about the function’s structure, pre‑yield or post‑yield code, exception handling, or restrictions beyond the single yield. The report is limited to the information explicitly supported by the available evidence. [1]

## Decorated Function Type
The function supplied to `@contextmanager` must be a generator. This is the only structural requirement documented in the evidence. [1]

## Yield Requirements
The generator must yield exactly one value. This single yielded value is bound to the variable specified in the `with` statement. No other yields are permitted. [1]

## Limitations
- The evidence does not describe any code that must execute before or after the `yield`.  
- Exception handling behavior of the decorator is not covered.  
- No restrictions on the number of yields beyond the requirement of a single yield are documented.  
- The evidence does not address the type of function beyond being a generator, nor does it discuss any other contractual obligations.

## References

1. contextlib — Utilities for with-statement contexts — https://docs.python.org/3/library/contextlib.html

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The generator used with @contextmanager must yield exactly one value. | "This iterator must yield exactly one value, which will be bound to" | 359-425 |

---
*1 passages from 1 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*