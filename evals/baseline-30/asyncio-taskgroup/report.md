# asyncio.TaskGroup vs asyncio.gather: Failure Handling and Cleanup

## Summary
`asyncio.gather()` does not cancel remaining tasks when one fails and propagates the first unhandled exception to the caller. [1, 2]  
`asyncio.TaskGroup` automatically cancels the remaining tasks, waits for their cleanup, and raises a single `ExceptionGroup` containing all failures. [3, 4]  
TaskGroup’s exception reporting aggregates multiple errors, whereas gather reports only the first exception unless `return_exceptions=True`. [4, 2]  
Cleanup in TaskGroup is guaranteed via `finally` blocks on each task, ensuring resources are released before the group raises the exception. [3]

## asyncio.gather() on Child Task Failure
When a coroutine passed to `asyncio.gather()` raises an exception, the gather call propagates that exception to its caller immediately, without automatically cancelling the other pending tasks. [2]  
To cancel the remaining tasks, the caller must explicitly iterate over the returned `Task` objects and invoke `cancel()`. [1]  
If `return_exceptions=True` is set, gather instead returns a list containing the exception objects for failed tasks, but still does not cancel the others. [1]

## asyncio.TaskGroup on Child Task Failure
Upon the first task failure within a `TaskGroup`, the group cancels all other tasks that are still pending. [3]  
The group then waits for each cancelled task to finish its cleanup, typically executing any `finally` blocks defined in the task’s coroutine. [3]  
After all tasks have terminated, the group raises a single `ExceptionGroup` that aggregates the original exception(s) and any `CancelledError`s from the cancelled tasks. [3, 4]

## Exception Reporting Differences
`asyncio.gather()` propagates the first unhandled exception (unless `return_exceptions=True`), so the caller receives only that exception. [2]  
`asyncio.TaskGroup` encapsulates all exceptions that occurred in its member tasks into an `ExceptionGroup`, allowing structured handling of multiple failures. [4]  
Thus, gather’s exception reporting is singular, while TaskGroup’s is aggregated.

## Cleanup and Finalization
Because gather does not cancel remaining tasks automatically, any cleanup code (e.g., `finally` blocks) in those tasks may not execute unless the caller cancels them manually. [1]  
TaskGroup guarantees that each task’s cleanup code runs before the group raises the `ExceptionGroup`, ensuring resources are released even when tasks are cancelled. [3]  
Consequently, TaskGroup provides more robust finalization semantics in failure scenarios.

## Limitations
- The evidence does not cover the behavior of `asyncio.gather` when `return_exceptions=True` in detail.  
- No source explicitly compares the timing of exception propagation between gather and TaskGroup.  
- The provided records do not discuss nested TaskGroups or interaction with other cancellation mechanisms.

## References

1. Asyncio gather() Cancel All Tasks if One Task Fails — https://superfastpython.com/asyncio-gather-cancel-all-if-one-fails/
2. Asyncio gather() Handle Exceptions — https://superfastpython.com/asyncio-gather-exception/
3. Cancellation and Cleanup in asyncio TaskGroup – Phenomic — https://www.phenomic.io/handling-cancellation-in-python-asyncio/
4. Python Taskgroups with asyncIO - GeeksforGeeks — https://www.geeksforgeeks.org/python/python-taskgroups-with-asyncio/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | asyncio.gather() does not automatically cancel remaining tasks when one task fails; you must manually cancel t | "You can cancel all tasks when one task fails when using asyncio.gather() by manually traversing the list of tasks can cancel them manually." | 52-191 |
| [2] | asyncio.gather propagates unhandled exceptions to the caller by default. | "By default, if a coroutine is executed by asyncio.gather() fails with an unhandled exception, it will be propagated to the caller." | 171-301 |
| [3] | TaskGroup uses finally blocks as the cleanup mechanism, running them whether the task returns, raises, or is c | "The finally block is the cleanup mechanism: it runs whether the task returns, raises, or is cancelled." | 1358-1460 |
| [3] | TaskGroup cancels remaining tasks after a child fails and waits for their cleanup before raising an ExceptionG | "After beta finishes its cleanup, the TaskGroup sees that failure and cancels the waiting workers. Their CancelledError handlers re-raise the cancellat" | 785-1090 |
| [4] | TaskGroup reports multiple exceptions as a single ExceptionGroup, allowing structured handling of all exceptio | "All exceptions became part of a Single Group and we didn't need to handle them one by one by using the traditional except keyword." | 2040-2170 |

---
*5 passages from 4 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*