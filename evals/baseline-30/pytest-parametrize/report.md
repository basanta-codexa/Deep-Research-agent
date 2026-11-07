# How `pytest.mark.parametrize` Turns One Function into Multiple Independent Tests

## Summary
`pytest.mark.parametrize` is a built‑in decorator that supplies a test function with several argument tuples, turning it into multiple test cases. The syntax lists argument names and a list of tuples, e.g. `@pytest.mark.parametrize("a,b", [(1,2),(3,4)])`. During collection, Pytest generates a distinct test ID for each tuple and treats each as an independent test. The decorator does not alter the test function body; it merely expands the test space at collection time.  
[1, 2]

## Syntax and Basic Usage
The decorator accepts a comma‑separated string of argument names followed by an iterable of tuples. A typical example is `@pytest.mark.parametrize("test_input,expected", [("3+5", 8), ("2+4", 6)])`. This syntax is also supported at module level via `pytestmark = pytest.mark.parametrize(...)`.  
[1]

## Generation of Test Cases
During the collection phase, Pytest calls `pytest_generate_tests` for each parameterized test. The function receives the test function and the parameter values, and Pytest creates two calls to the test function for the example in the docs. Each call is collected as a separate test item.  
[2]

## Independence of Generated Cases
Each generated test item receives its own set of arguments and is executed in isolation. The decorator does not share state between the generated calls; the test function is invoked anew for each tuple.  
[2]

## Naming and Discovery
Pytest builds a string ID for each set of values, which appears in the test report and can be inspected with `--collect-only`. The ID reflects the function name and the parameter values, allowing the test runner to discover and report each case separately.  
[2]

## Impact on Execution Order and Isolation
Because each parameterized case is a distinct test item, Pytest treats them like any other test: they run in the order determined by the collection mechanism and are isolated from one another. No special ordering guarantees are provided beyond the default collection order.  
[2]

## Limitations
- The evidence does not describe the internal algorithm Pytest uses to transform the decorator arguments into test items.  
- The sources do not explicitly state how generated test cases are independent or how isolation is enforced beyond the fact that each call is separate.  
- There is no explicit mention of how parametrize affects test execution order beyond the default collection behavior.  

---

## References

1. How to parametrize fixtures and test functions¶ — https://docs.pytest.org/en/stable/how-to/parametrize.html
2. Parametrizing tests¶ — https://docs.pytest.org/en/7.1.x/example/parametrize.html

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The syntax for parametrize is @pytest.mark.parametrize("arg1,arg2", [(val1,val2), ...]). | "@pytest.mark.parametrize("test_input,expected", [("3+5", 8), ("2+4", 6), ("6*9", 42)])" | 694-780 |
| [1] | Parametrize can be applied to a module by assigning to pytestmark. | "pytestmark = pytest.mark.parametrize("n,expected", [(1, 2), (3, 4)])" | 956-1024 |
| [1] | The @pytest.mark.parametrize decorator is used to define multiple sets of arguments for a test function. | "The builtin pytest.mark.parametrize decorator enables parametrization of arguments for a test function." | 470-573 |
| [2] | pytest_generate_tests generated two calls to the test_db_initialized during the collection phase | "pytest_generate_tests generated two according calls to the test_db_initialized during the collection phase" | 1866-1972 |
| [2] | Running pytest with --collect-only will show the generated IDs. | "Running pytest with --collect-only will show the generated IDs." | 1041-1104 |
| [2] | Pytest will build a string that is the test ID for each set of values in a | "pytest will build a string that is the test ID for each set of values in a" | 966-1040 |

---
*6 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*