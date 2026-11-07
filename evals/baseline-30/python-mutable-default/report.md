# Mutable Default Arguments in Python: Shared State Across Calls

## Summary
Default arguments are parameters with predefined values, and non‑default parameters must precede them in a function definition. When a default argument is mutable, the same object is reused across separate calls, causing modifications to persist. The evidence shows that a list used as a default argument is shared and modified each time the function is invoked with a single argument. The report discusses the handling of default arguments, the mechanism of sharing, and the limitations of the evidence regarding mitigation strategies. [1, 2]

## Handling of Default Arguments
Default arguments are parameters with predefined values, allowing a function to be called with fewer arguments than it declares. Non‑default parameters must come before default parameters in the function definition. These rules are established at the time a function is defined. [1]

## Mutable Defaults Become Shared
If the default values are mutable or modifiable (lists, dictionaries, etc.), they can be modified within the function, and those modifications will persist across function calls. The same list is used whenever the function is called with a single argument, because the default value list is modified each time the function is called. This shared state arises from the fact that the default object is created once and reused. [2]

## Concrete Example of Shared Mutable Default
The evidence indicates that a list used as a default argument is shared across separate calls. When the function is invoked with a single argument, the default list is reused, and any modifications to that list are retained for subsequent calls. This demonstrates that the mutable default argument is not recreated on each call. [2]

## Implications for Function Design
Because mutable defaults are shared, a function that modifies its default argument will leave side effects that affect future calls. The evidence shows that modifications to a mutable default persist, which can lead to unexpected behavior if the developer is unaware of this sharing. [2]

## Common Misconceptions
Some developers may assume that each call creates a new default object, but the evidence contradicts this assumption by showing that the same list is reused. The evidence explicitly states that the default value list is modified each time the function is called, indicating that a new object is not created. [2]

## Avoiding Unintended Sharing
The evidence does not provide explicit guidance on how developers can avoid unintended sharing of mutable default arguments. It only describes the behavior that occurs when such defaults are used. Therefore, developers must consult additional resources to learn mitigation techniques. [2]

## Limitations
- The evidence does not include actual function code demonstrating the shared mutable default argument.  
- The evidence does not discuss strategies for preventing unintended sharing or alternative design patterns.  
- The evidence is limited to a single source domain (geeksforgeeks.org) and does not cover broader community consensus or best practices.  

---

## References

1. Default arguments in Python - GeeksforGeeks — https://www.geeksforgeeks.org/python/default-arguments-in-python/
2. Use mutable default value as an argument in Python - GeeksforGeeks — https://www.geeksforgeeks.org/python/use-mutable-default-value-as-an-argument-in-python/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | Non‑default parameters must come before default parameters in the function definition. | "Non-default parameters must come before default parameters in the function definition." | 1274-1360 |
| [1] | Default arguments are parameters with predefined values. | "In Python, functions can have default arguments, which are parameters with predefined values." | 0-93 |
| [2] | The same list is used whenever the function is called with a single argument, because the default value list i | "As you can see the same list is used whenever we call the function with a single argument, this is because the default value list is modified each tim" | 1760-1935 |
| [2] | Mutable default values are shared across function calls, causing modifications to persist. | "If the default values are mutable or modifiable (lists, dictionaries, etc.), they can be modified within the function and those modifications will per" | 567-744 |

---
*4 passages from 2 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*