# PostgreSQL MVCC: Concurrent Readers and Writers

## Summary
PostgreSQL’s Multi‑Version Concurrency Control (MVCC) gives each SQL statement a snapshot of the database at a point in time, allowing reads to see a consistent view while writes proceed independently. Tuple headers store the inserting and deleting transaction IDs (xmin, xmax), and a deterministic visibility routine selects the appropriate version for a given snapshot. Writers create new row versions that become visible only after commit, and old versions are retained until no active snapshot can see them. This design ensures that read locks never conflict with write locks, preserving non‑blocking behavior even at the strictest isolation level. [1]

## MVCC Implementation in PostgreSQL
PostgreSQL implements MVCC by attaching transaction identifiers to each tuple header and using a visibility routine to evaluate those identifiers against the active snapshot. The routine applies a deterministic mathematical predicate that checks the tuple’s xmin and xmax against the transaction’s snapshot. [2, 3] Each tuple therefore carries the metadata needed for visibility decisions without requiring locks. [2]

## Visibility Determination
When a query executes, PostgreSQL captures a snapshot that records the set of active transaction IDs at the start of the statement. The visibility routine then compares a tuple’s xmin (the inserting transaction) and xmax (the deleting transaction) against this snapshot. If xmin is not in the snapshot and xmax is either null or in the snapshot, the tuple is visible; otherwise it is invisible. Snapshots are used to determine which version of a tuple is visible in a given transaction. [3]

## Writer Behavior and Old Version Handling
Writers create a new row version that is not visible to other transactions until the writing transaction commits. The new tuple’s xmin is set to the writer’s transaction ID, and the old tuple’s xmax is set to the writer’s ID upon update or delete. The old version remains in the table until no active snapshot can reference it, at which point it becomes eligible for vacuum cleanup. An UPDATE writes a new version of the row and keeps the old one until no snapshot can still see it. [4, 5] This strategy allows readers to continue accessing the old version without waiting for the writer to finish. [4]

## Preventing Mutual Blocking
Because read locks are not acquired on tuples, readers never block writers, and writers do not acquire locks that conflict with read operations. The MVCC model ensures that read locks do not conflict with write locks, so reading never blocks writing and writing never blocks reading. This guarantee holds even under Serializable Snapshot Isolation, the strictest isolation level supported by PostgreSQL. [1]

## Limitations
- The evidence does not detail the exact algorithmic implementation of the visibility routine beyond its deterministic nature.  
- While the primary sources confirm non‑blocking behavior, secondary sources provide partial or incomplete coverage of the underlying mechanics.  
- The discussion of vacuum and cleanup of old tuples is limited to a single source and does not cover edge cases such as transaction ID wraparound.

## References

1. 13.1. Introduction — https://www.postgresql.org/docs/current/mvcc-intro.html
2. PostgreSQL MVCC Internals & Tuple Visibility Demystified | InitNode — https://www.initnode.dev/signal/postgresql-mvcc-internals-tuple-visibility-vacuum-isolation
3. Introduction to Snapshots and Tuple Visibility in PostgreSQL — https://jnidzwetzki.github.io/2024/04/03/postgres-and-snapshots.html
4. How PostgreSQL MVCC Works — Multi-Version Concurrency Control Deep Dive — Pranesh Nikhar — https://www.praneshnikhar.site/posts/postgres-mvcc
5. MVCC Internals: How PostgreSQL Stores Row Versions — https://thesev1database.com/lessons/mvcc-internals-row-versions

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | In PostgreSQL, MVCC ensures that read locks do not conflict with write locks, so readers never block writers a | "the MVCC model of concurrency control rather than locking is that in MVCC locks acquired for querying (reading) data do not conflict with locks acquir" | 812-1052 |
| [1] | PostgreSQL maintains the no‑blocking guarantee even at the strictest isolation level, Serializable Snapshot Is | "PostgreSQL maintains this guarantee even when providing the strictest level of transaction isolation through the use of an innovative Serializable Sna" | 1053-1231 |
| [1] | MVCC allows reads to never block writes and writes to never block reads. | "The main advantage of using the MVCC model of concurrency control rather than locking is that in MVCC locks acquired for querying (reading) data do no" | 784-1052 |
| [1] | MVCC is a multiversion model that gives each SQL statement a snapshot of the database as it existed at a point | "This means that each SQL statement sees a snapshot of data (a database version) as it was some time ago, regardless of the current state of the underl" | 254-414 |
| [2] | PostgreSQL implements MVCC by storing the transaction IDs of the inserting and deleting transactions in each t | "When a query executes, the database engine passes each candidate tuple through a deterministic mathematical predicate—the Visibility Routine—which eva" | 656-912 |
| [3] | Tuples are stored with two attributes (xmin, xmax) that determine in which snapshots (and transactions) they a | "Tuples are stored with two attributes (xmin, xmax) that determine in which snapshots (and transactions) they are visible." | 902-1023 |
| [3] | Snapshots are used to determine which version of a tuple is visible in a given transaction. | "Snapshots are used to determine which version of a tuple is visible in a given transaction." | 162-253 |
| [4] | Writers create new row versions that only become visible once the writing transaction commits. | "Writers create new row versions that only become visible once the writing transaction commits." | 572-666 |
| [4] | Readers see a consistent snapshot of the data as it existed when their transaction began. | "Readers see a consistent snapshot of the data as it existed when their transaction began." | 482-571 |
| [5] | An UPDATE writes a new version of the row and keeps the old one until no snapshot can still see it. | "An UPDATE writes a new version of the row and keeps the old one until no snapshot can still see it." | 190-289 |

---
*10 passages from 5 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*