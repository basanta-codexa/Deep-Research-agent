# Pytest Fixture Scopes: Scope, Isolation, and Cost

## Summary
Pytest offers four fixture scopes—class, module, package, and session—allowing a fixture to be shared across different test groupings. The default scope is function, meaning a fixture is created and destroyed for each test. Fixture scope dictates the duration of setup and teardown relative to test execution. Current documentation does not provide quantitative data on isolation or performance trade‑offs for these scopes. [1, 2]

## Available Fixture Scopes
Pytest defines four primary fixture scopes: class, module, package, and session. These scopes enable a fixture to be shared across all tests within a class, module, package, or the entire test session, respectively. [1]

## Scope's Role in Test Execution
The default fixture scope is function, which causes the fixture to be instantiated before each test and destroyed afterward. [1]  
Fixture scope determines how long the fixture’s setup and teardown code is executed in relation to your test functions. [2]

## Implications for Isolation and Performance
The evidence does not discuss how fixture scope influences test isolation.  
No data on the setup or teardown cost for different scopes is available.

## Choosing Scopes: Considerations
Because the available documentation does not recommend a specific balance between isolation and performance, developers must rely on their own experience and testing needs when selecting a scope.

## Limitations
- The evidence does not establish how fixture scope affects test isolation.  
- No data on the setup or teardown cost for different scopes is available.  
- Best‑practice recommendations for balancing isolation and performance are not present in the cited sources.

## References

1. How to use fixtures¶ — https://docs.pytest.org/en/stable/how-to/fixtures.html
2. What Are Pytest Fixture Scopes? (How To Choose The Best Scope For Your Test) — https://pytest-with-eric.com/fixtures/pytest-fixture-scope/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The default fixture scope is function, meaning the fixture is destroyed at the end of each test. | "- function: the default scope, the fixture is destroyed at the end of the test." | 514-593 |
| [1] | Fixture scopes include class, module, package, and session. | "Scope: sharing fixtures across classes, modules, packages or session" | 351-419 |
| [2] | Fixture scope determines how long a fixture’s setup and teardown code is executed in relation to your test fun | "The scope determines how long a fixture’s setup and teardown code is executed in relation to your test functions." | 351-464 |

---
*3 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*