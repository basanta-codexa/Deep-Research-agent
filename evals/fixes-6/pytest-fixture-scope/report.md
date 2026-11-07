# Fixture Scope in Pytest: Isolation vs. Setup Cost

## Summary
Pytest fixtures can be scoped at **function**, **class**, **module**, **package**, or **session** level, controlling how many times the fixture is instantiated and when its teardown runs. [1, 2]  
The **function** scope provides the highest isolation, as each test receives a fresh fixture instance and the fixture is destroyed afterward. [2]  
Larger scopes such as **module** or **session** reduce the number of fixture creations, lowering setup overhead for expensive resources like Docker containers. [2]  
Choosing the appropriate scope requires balancing isolation needs against performance; a common practice is to use function scope for stateful tests and larger scopes for costly, read‑only resources. [2, 1]

## Pytest Fixture Scopes and Their Mechanics
Pytest defines five fixture scopes: `function`, `class`, `module`, `package`, and `session`. Each scope determines the lifetime of a fixture instance. [1]  
- **function**: a new instance per test function; teardown occurs immediately after the test.  
- **class**: one instance per test class; teardown after all methods in the class.  
- **module**: one instance per test module; teardown after all tests in the module.  
- **package**: one instance per package; teardown after all tests in the package.  
- **session**: one instance for the entire test run; teardown after all tests finish.  
Pytest caches a single instance per scope; when a fixture is parametrized, it may be invoked multiple times within the same scope. [3]  

## Impact on Test Isolation
Isolation refers to the independence of test outcomes from one another.  
- With **function** scope, each test gets a clean fixture state, preventing side effects across tests. [2]  
- **Class**, **module**, **package**, and **session** scopes share the same fixture instance across multiple tests, which can introduce shared state if the fixture mutates. This shared state can lead to flaky tests unless the fixture is designed to be immutable or properly reset. [2]  

## Impact on Setup Cost
The cost of creating a fixture depends on the resource it manages.  
- **Function** scope incurs the setup and teardown cost for every test, which can be expensive for heavyweight resources (e.g., spinning up a Docker container). [2]  
- **Module** or **session** scopes amortize this cost across many tests, reducing overall runtime. The trade‑off is that the fixture remains alive longer, potentially increasing memory usage or risk of stale state. [2]  

## Best Practices for Selecting Fixture Scopes
1. **Use function scope for stateful or mutable fixtures** that must not leak between tests.  
2. **Prefer larger scopes for expensive, read‑only resources** (databases, containers) when tests do not modify the fixture.  
3. **Avoid sharing mutable fixtures across scopes** unless you explicitly reset them in a teardown or fixture function.  
4. **Leverage parametrization** to test multiple configurations while keeping the fixture scope minimal; Pytest will invoke the fixture per parameter within the chosen scope. [3]  
5. **Profile test runs** to identify fixtures that dominate runtime; adjust their scope accordingly.  

## Limitations
- The evidence does not directly quantify the isolation guarantees of non‑function scopes; it only states that function scope destroys the fixture after each test.  
- The impact of shared state on test flakiness is inferred rather than explicitly documented in the sources.  
- The cost savings of larger scopes are mentioned qualitatively; no numeric benchmarks are provided.

## References

1. What Are Pytest Fixture Scopes? (How To Choose The Best Scope For Your Test) — https://pytest-with-eric.com/fixtures/pytest-fixture-scope/
2. pytest fixtures: explicit, modular, scalable¶ — https://docs.pytest.org/en/6.2.x/fixture.html
3. How to use fixtures¶ — https://docs.pytest.org/en/stable/how-to/fixtures.html

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | Fixture scope determines how long a fixture’s setup and teardown code is executed in relation to your test fun | "The scope determines how long a fixture’s setup and teardown code is executed in relation to your test functions." | 351-464 |
| [2] | Using a larger scope such as module or session can reduce setup cost for expensive fixtures like Docker contai | "In some cases, you might want to change the scope of the fixture without changing the code. This can be especially useful when dealing with fixtures t" | 1017-1225 |
| [2] | Function scope gives isolation by destroying the fixture after each test. | "- function: the default scope, the fixture is destroyed at the end of the test." | 766-845 |
| [3] | Pytest caches one instance of a fixture per scope, so a fixture may be invoked more than once in a given scope | "Pytest only caches one instance of a fixture at a time, which means that when using a parametrized fixture, pytest may invoke a fixture more than once" | 351-521 |

---
*4 passages from 3 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*