# Distinguishing Iterables, Iterators, and Generators in Python

## Summary
An **iterable** is any object whose elements can be accessed one at a time, enabling traversal with a loop or an iterator constructor.  
An **iterator** is an object that implements the `__next__()` protocol and yields successive items until exhaustion.  
A **generator** is a special kind of iterator created by a function or expression that uses `yield` to produce values lazily.  
All generators are iterators, and all iterators are iterables, but not every iterable is an iterator.  
[1, 2, 3, 4, 5]  

## Iterable
An iterable is defined as an object whose elements can be accessed one at a time.  
This property allows it to be passed to functions like `list()`, `sum()`, or used in a `for` loop.  
In Python, built‑in containers such as lists, tuples, dictionaries, and sets are iterables.  
The language treats any object that implements the `__iter__()` method as an iterable.  
[1]  

## Iterator
An iterator is an object that can traverse an iterable by returning one element at a time through the `__next__()` method.  
When `__next__()` is called, the iterator returns the next item and raises `StopIteration` when the sequence is exhausted.  
Iterators are created by calling `iter()` on an iterable, or by defining a class that implements `__iter__()` and `__next__()`.  
Every iterator is also an iterable because it implements `__iter__()` that returns itself.  
However, many iterables (e.g., lists) are not iterators until `iter()` is applied.  
[2, 5]  

## Generator
A generator is a lightweight iterator produced by a function or expression that contains one or more `yield` statements.  
When a generator function is called, it returns a generator object that implements the iterator protocol.  
Each `yield` pauses execution, preserves local state, and resumes on the next call to `__next__()`.  
Because generators produce values on demand, they are memory efficient for large or infinite sequences.  
Generators can be defined either with a function (`def`) or with a generator expression (`(x for x in iterable)`).  
[3, 4]  

## Relationships and Differences
| Concept   | Creation                     | Protocol                     | Memory                     | Typical Use                     |
|-----------|------------------------------|------------------------------|----------------------------|---------------------------------|
| Iterable  | Inherent to objects          | `__iter__()` returns iterator | N/A                        | Collections, files              |
| Iterator  | `iter(obj)` or custom class | `__next__()`                 | N/A                        | Looping, `next()`               |
| Generator | `yield` in function/expression | `__next__()` via `yield` | Lazy, no full list         | Streams, pipelines              |
[5, 2, 3]  

- **Creation**: Iterables are inherent to objects; iterators are obtained via `iter()` or custom classes; generators are defined with `yield`.  
  [1, 2, 3]  
- **Protocol**: All three support the iterator protocol, but only iterators and generators implement `__next__()`.  
  [2, 3, 5]  
- **Memory**: Generators generate items on the fly, whereas iterables may hold all items in memory.  
  [4, 1, 2]  
- **Use**: Use an iterable when you need a container; use an iterator when you need explicit control over traversal; use a generator for efficient, lazy computation.  
  [1, 2, 3]  

## Limitations
- The evidence does not detail the internal implementation of `__iter__()` for built‑in types.  
- No source explicitly contrasts the performance implications of generators versus list comprehensions.  
- The evidence does not cover advanced iterator protocols such as `__iter__` returning a new iterator each call.

## References

1. Iterables in Python — https://codewithbk.com/python/courses/python-101/pythonic-programming/iterables-in-python/
2. Iterators in Python - GeeksforGeeks — https://www.geeksforgeeks.org/python/iterators-in-python/
3. Generators in Python - GeeksforGeeks — https://www.geeksforgeeks.org/python/generators-in-python/
4. Difference Between Iterator vs Generator - GeeksforGeeks — https://www.geeksforgeeks.org/python/difference-between-iterator-vs-generator/
5. Python | Difference between iterable and iterator - GeeksforGeeks — https://www.geeksforgeeks.org/python/python-difference-iterable-iterator/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | An iterable is an object whose elements can be accessed one at a time. | "An iterable is an object whose elements can be accessed one at a time." | 592-662 |
| [1] | Python calls objects that can be traversed one item at a time iterables. | "Python calls objects that can be traversed one item at a time iterables." | 217-289 |
| [2] | An iterator in Python is an object used to traverse through all the elements of a collection (like lists, tupl | "An iterator in Python is an object used to traverse through all the elements of a collection (like lists, tuples or dictionaries) one element at a tim" | 0-152 |
| [3] | A generator function returns an iterator object and uses yield to produce a series of results over time, pausi | "A generator function is a special type of function that returns an iterator object. Instead of using return to send back a single value, generator fun" | 0-297 |
| [4] | A generator is another way to create iterators, but in a simpler and more readable manner. Instead of storing  | "A generator is another way to create iterators, but in a simpler and more readable manner. Instead of storing all values, generators produce values on" | 351-534 |
| [5] | Every iterator is also an iterable, but not every iterable is an iterator in Python. | "Note: Every iterator is also an iterable, but not every iterable is an iterator in Python." | 351-441 |
| [5] | An iterator is an object, which is used to iterate over an iterable object using the __next__() method. | "An iterator is an object, which is used to iterate over an iterable object using the __next__() method." | 105-208 |

---
*7 passages from 5 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*