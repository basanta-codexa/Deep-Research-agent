# Behavior of asyncio.gather When a Coroutine Raises an Exception

## Summary
When a coroutine passed to `asyncio.gather` raises an exception, the gather future propagates that exception to its caller immediately. [1, 2]  
By default, `asyncio.gather` does not cancel the remaining coroutines automatically. [1]  
To cancel all tasks when one fails, you must manually cancel them or cancel the gather future itself. [3]

## Default Behavior of asyncio.gather
`asyncio.gather` aggregates the results of multiple awaitables. If any awaitable raises an unhandled exception, the gather future fails with that exception and the exception is propagated to the caller immediately. [1, 2]  
The exception is not swallowed or delayed; the caller receives it as soon as the gather future completes. [1, 2]

## Cancellation of Remaining Coroutines
By default, `asyncio.gather` does not automatically cancel the other awaitables when one fails. [1]  
Consequently, resources may be consumed by tasks that are no longer needed, and their eventual completion or failure will still be reported by the gather future. [1]

## Preventing Cancellation of Other Tasks
To cancel all tasks when one fails, you must manually cancel them or cancel the gather future itself. This can be done by iterating over the list of tasks and calling `task.cancel()` on each, or by calling `gather_future.cancel()` to propagate cancellation to all underlying tasks. [3]  
Because `asyncio.gather` does not perform this cancellation automatically, developers must explicitly manage task lifetimes if they wish to avoid orphaned coroutines. [3]

## Limitations

## References

1. Asyncio gather() Handle Exceptions — https://superfastpython.com/asyncio-gather-exception/
2. Asyncio gather() Exception in Task Does Not Cancel — https://superfastpython.com/asyncio-gather-exception-not-cancel/
3. Asyncio gather() Cancel All Tasks if One Task Fails — https://superfastpython.com/asyncio-gather-cancel-all-if-one-fails/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | asyncio.gather propagates an unhandled exception to the caller immediately | "By default, if a coroutine is executed by asyncio.gather() fails with an unhandled exception, it will be propagated to the caller." | 171-301 |
| [2] | asyncio.gather propagates an unhandled exception to the caller immediately | "By default, an exception in asyncio.gather() will be propagated to the caller immediately." | 113-203 |
| [3] | To cancel all tasks when one fails, you must manually cancel them or cancel the gather future | "You can cancel all tasks when one task fails when using asyncio.gather() by manually traversing the list of tasks can cancel them manually." | 52-191 |

---
*3 passages from 3 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*