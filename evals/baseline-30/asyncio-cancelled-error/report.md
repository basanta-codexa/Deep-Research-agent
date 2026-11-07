# asyncio.CancelledError Inheritance in Python 3.8+

## Summary
`asyncio.CancelledError` is a subclass of `Exception`, which itself inherits from `BaseException`[1]. In Python 3.8 the class was changed to inherit directly from `BaseException` rather than from `Exception`[2]. The evidence does not provide a rationale for this change, nor does it discuss how this inheritance affects exception handling or developer practice[2].

## Class Definition and Inheritance Hierarchy
The official documentation states that `asyncio.CancelledError` is a subclass of `Exception` and, by extension, of `BaseException`[1]. In Python 3.8 the class definition was updated so that `CancelledError` inherits directly from `BaseException` instead of from `Exception`[2].

## Rationale for the Change
No evidence in the provided sources explains why the inheritance was altered in Python 3.8. The documentation notes the change but does not elaborate on the motivation[2].

## Impact on Exception Handling and Developer Implications
The evidence does not describe how inheriting from `BaseException` influences exception handling, propagation, or the behavior of asyncio tasks. Consequently, no conclusions can be drawn about the practical implications for developers writing asyncio code[2].

## Limitations
- The evidence does not establish the prior inheritance hierarchy before Python 3.8, so the exact nature of the change cannot be fully confirmed.  
- No rationale for the inheritance change is documented in the sources.  
- The effect of this inheritance on exception handling, task cancellation semantics, or developer best practices is not addressed by the evidence.

## References

1. Weird Behavior of asyncio.CancelledError and '_GatheringFuture exception was never retrieved' in Python AsyncIO: Understanding and Fixing Unhandled Exceptions — https://www.ancisoft.com/blog/weird-behaviour-of-asyncio-cancellederror-and-gatheringfuture-exception-was-never-retrieved/
2. Exceptions — https://docs.python.org/3/library/asyncio-exceptions.html

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | asyncio.CancelledError is a subclass of Exception, which inherits from BaseException | "asyncio.CancelledError is a subclass of Exception (and BaseException) specifically designed to signal task cancellation in asyncio." | 351-482 |
| [2] | `CancelledError` is a subclass of `BaseException` rather than `Exception`. | "CancelledError is now a subclass of BaseException rather than Exception." | 499-571 |

---
*2 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*