# Impact of @dataclass(slots=True) on Class Behavior and Instance Memory

## Summary
`@dataclass(slots=True)` adds a `__slots__` attribute to the generated class, restricting attribute assignment to a fixed set and eliminating the instance dictionary. This restriction reduces per‑instance memory usage from roughly 150–200 bytes to 48–64 bytes for small dataclasses. The decorator also enforces that the class does not already define `__slots__` and that subclasses do not pass parameters to `__init_subclass__`, otherwise a `TypeError` is raised. Using slots can cut overall heap consumption by 50–70 % when many instances are created. [1, 2]

## Purpose of `__slots__`
`__slots__` limits the attributes a class can have, thereby reducing memory usage. [3]  
It replaces the per‑instance dictionary with a fixed‑width list or mutable tuple, which stores only the declared attributes. [4]

## How `@dataclass(slots=True)` Modifies the Class
When `slots=True`, the dataclass decorator injects a `__slots__` attribute containing all field names that are not already present in a base class’s `__slots__`. [1]  
If the class already defines `__slots__`, a `TypeError` is raised to prevent accidental overriding. [1]  
Passing arguments to a base class’s `__init_subclass__` while using `slots=True` also triggers a `TypeError`. [1]

## Memory Impact
A conventional dataclass instance with a few attributes consumes about 150–200 bytes. [2]  
The same instance with `slots=True` typically drops to 48–64 bytes. [2]  
When millions of records are instantiated, enabling slots can reduce overall heap usage by 50–70 %. [2]

## Limitations and Trade‑offs
Because `__slots__` removes the instance dictionary, dynamic attribute addition is disallowed; attempting to set an undeclared attribute raises an `AttributeError`. [3]  
Subclassing a slotted dataclass requires careful handling of `__slots__` inheritance; overlapping slot names are omitted to avoid overriding. [1]  
The memory savings come at the cost of flexibility: slots prevent the use of features that rely on dynamic attribute assignment, such as monkey‑patching or adding attributes at runtime. [3]  
The decorator’s enforcement of no pre‑existing `__slots__` and no parameterized `__init_subclass__` can restrict certain metaclass patterns. [1]

## Limitations
- The evidence does not quantify the performance impact on attribute access speed.  
- No data is provided on how slots affect pickling, serialization, or interaction with third‑party libraries.  
- The memory figures are specific to small dataclasses; larger or nested dataclasses may exhibit different scaling.

## References

1. dataclasses — Data Classes — https://docs.python.org/3/library/dataclasses.html
2. Python Dataclass slots=True Memory and Performance - python — https://salivity.github.io/python/article/python-dataclass-slots-true-memory-and-performance
3. Python | Use of __slots__ - GeeksforGeeks — https://www.geeksforgeeks.org/python/python-use-of-__slots__/
4. __slots__ for optimizing classes — https://www.pythonmorsels.com/__slots__/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | If slots is true, __slots__ attribute is added to the class. | "- slots: If true (the default is False), __slots__ attribute" | 772-832 |
| [1] | Passing parameters to a base class __init_subclass__() when using slots=True will result in a TypeError. | "Warning Passing parameters to a base class __init_subclass__() when using slots=True will result in a TypeError." | 905-1017 |
| [1] | Using slots=True raises a TypeError if the class already defines __slots__ | "If __slots__ is already defined in the class, then TypeError is raised." | 833-904 |
| [1] | Field names already in a base class's __slots__ are omitted from the generated __slots__ to prevent overriding | "Added in version 3.10. Changed in version 3.11: If a field name is already included in the __slots__ of a base class, it will not be included in the g" | 1018-1214 |
| [2] | Enabling slots=True can reduce overall heap usage by 50% to 70% when dealing with millions of records. | "enabling slots=True can reduce overall heap usage by 50% to 70%." | 2031-2095 |
| [2] | A conventional dataclass instance with a few attributes consumes around 150 to 200 bytes, while a slotted data | "A conventional dataclass instance with a few attributes often consumes around 150 to 200 bytes. With slots=True, that same instance typically drops to" | 1738-1904 |
| [3] | __slots__ limits the attributes a class can have, reducing memory usage. | "slots provide a special mechanism to reduce the size of objects.It is a concept of memory optimisation on objects." | 202-316 |
| [4] | __slots__ uses a fixed-width list to store attributes instead of a dictionary. | "Instead, __slots__ uses something kind of like a fixed-width list (or like a mutable tuple) to store specifically three attributes: x, y, and z." | 436-580 |

---
*8 passages from 4 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*