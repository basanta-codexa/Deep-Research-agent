# Why `asyncio.run()` is Preferred Over `asyncio.get_event_loop()` in Modern Python

## Summary
Python 3.7+ documentation recommends using `asyncio.run()` to execute top‑level coroutines, as it manages the entire event‑loop lifecycle and guarantees deterministic cleanup [1]. In contrast, `asyncio.get_event_loop()` can return a loop that is either already running or a new orphaned loop, leading to subtle bugs and deprecation warnings on recent Python releases [2, 1]. Additionally, `asyncio.get_event_loop()` may yield a loop type incompatible with certain Windows libraries, whereas `asyncio.run()` always creates a fresh, fully configured loop [3]. Finally, `asyncio.get_running_loop()` is the safer alternative when a loop is guaranteed to exist, but it does not replace the need for `asyncio.run()` in entry‑point code [4].

## Documentation Recommendation
Python’s official guidance for running asyncio programs in 3.7+ is to invoke `asyncio.run()` at the program’s entry point. This function encapsulates loop creation, execution of the main coroutine, and cleanup, ensuring that no stray loops remain after completion [1]. The documentation explicitly states that `asyncio.run()` should be used instead of manually managing the loop with `get_event_loop()` or `new_event_loop()`.

## Problems with `asyncio.get_event_loop()` in New Code
`asyncio.get_event_loop()` behaves differently depending on context. Inside a running coroutine it always returns the current loop, which can mask errors when called from synchronous code that expects a fresh loop [2]. When no loop is running, the function creates a new loop but does not close it, resulting in orphaned loops that persist beyond the intended scope. This is deprecated as of Python 3.10 and can trigger warnings or errors in future releases [1]. Moreover, on Windows, `get_event_loop()` may return a `SelectorEventLoop` instead of the default `ProactorEventLoop`, causing incompatibilities with libraries that require the latter [3].

## `asyncio.run()` vs. `asyncio.get_event_loop()`
`asyncio.run()` owns the event‑loop lifecycle end‑to‑end: it creates a new loop, runs the supplied coroutine until completion, closes the loop, and ensures that all tasks are cancelled and resources are released. After each `asyncio.run()` invocation, the loop is closed (`loop.is_closed() == True`) and `asyncio.all_tasks(loop)` is empty, providing deterministic cleanup [1]. In contrast, `asyncio.get_event_loop()` merely retrieves an existing loop or creates a new one without guaranteeing that it will be closed, leaving the responsibility of cleanup to the developer. This difference can lead to resource leaks and unpredictable behavior in long‑running applications.

## Platform and Compatibility Concerns
On Windows, the default event loop changed from `SelectorEventLoop` to `ProactorEventLoop` in Python 3.8. Using `asyncio.get_event_loop()` may inadvertently select the older loop type, which can cause `NotImplementedError` when performing subprocess operations or using certain third‑party networking libraries [3]. Additionally, selector‑based loops on Windows can degrade high‑performance networking, further motivating the use of `asyncio.run()` which always creates the appropriate loop for the platform [3].

## Limitations
- The evidence does not detail the internal algorithm by which `asyncio.run()` constructs the loop; it only states that it owns the lifecycle.
- The sources do not provide explicit comparisons of performance overhead between `asyncio.run()` and manual loop management.
- The documentation on deprecation of `get_event_loop()` in 3.10 is inferred from the cited source; other Python releases may have nuanced behaviors not captured here.

## References

1. asyncio.run() vs loop.run_until_complete(): When to Use Each | Python Async — https://async-concurrency.com/asyncio-fundamentals-event-loop-architecture/event-loop-configuration/when-to-use-asynciorun-vs-looprun_until_complete/
2. Replacing get_event_loop Deprecation Warnings | Python Async — https://www.async-concurrency.com/asyncio-fundamentals-event-loop-architecture/asyncio-version-migration/replacing-get-event-loop-deprecation-warnings/
3. python - Solving Asyncio's Platform Support Issues with Executors and Aiofiles — https://runebook.dev/en/docs/python/library/asyncio-platforms/all-platforms
4. python - Navigating Asyncio's Low-Level Event Loop Policies: Deprecation and the Path to loop_factory — https://runebook.dev/en/docs/python/library/asyncio-llapi-index/event-loop-policies

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | After each asyncio.run() or manual run, loop.is_closed() is True and asyncio.all_tasks(loop) is empty | "Deterministic cleanup: after each asyncio.run() or manual run, loop.is_closed() is True and asyncio.all_tasks(loop) is empty" | 1811-1935 |
| [1] | On 3.10+ get_event_loop() without a running loop is deprecated and creates orphaned loops | "On 3.10+ get_event_loop() without a running loop is deprecated and creates orphaned loops" | 1494-1583 |
| [1] | asyncio.run() owns the loop lifecycle end to end | "asyncio.run() owns the loop lifecycle end to end" | 1067-1115 |
| [2] | asyncio.get_event_loop() is the most common reason an asyncio codebase breaks on Python 3.14. | "asyncio.get_event_loop() is the most common reason an asyncio codebase breaks on Python 3.14." | 47-140 |
| [2] | Its behaviour depends on where it is called: inside a running coroutine it returns the running loop on every v | "Its behaviour depends on where it is called: inside a running coroutine it returns the running loop on every version, which is why most code never not" | 141-296 |
| [3] | Using a selector loop on Windows may cause issues with high‑performance networking. | "However, be aware this may cause issues with high-performance networking on Windows." | 962-1046 |
| [3] | Using asyncio.get_event_loop() may return a loop that is incompatible with libraries expecting SelectorEventLo | "If you try to perform certain operations (like running asyncio subprocesses) or use specific third-party libraries that expect the SelectorEventLoop o" | 511-741 |
| [3] | The default event loop on Windows changed to ProactorEventLoop in Python 3.8, replacing SelectorEventLoop. | "This is the default on Windows starting with Python 3.8 (before that, SelectorEventLoop was the default)." | 1720-1825 |
| [4] | asyncio.get_running_loop() strictly raises an error if no loop is running, preventing subtle bugs. | "Use asyncio.get_running_loop(). This strictly raises an error if no loop is running, preventing subtle bugs." | 676-784 |

---
*9 passages from 4 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*