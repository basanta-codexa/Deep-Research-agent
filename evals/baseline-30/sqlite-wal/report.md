# WAL Mode and Concurrency in SQLite

## Summary
SQLite’s Write‑Ahead Logging (WAL) mode decouples writes from the main database file, allowing readers to access the original data while a writer records changes in a separate log file [1]. This design permits readers to continue accessing the unaltered database while a writer commits changes, as the original pages remain untouched until a checkpoint merges the WAL into the database [1]. The result is a concurrency model where readers do not block writers and vice versa [1].  

## WAL Mode Overview
WAL mode rewrites the default rollback journal by appending changes to a WAL file instead of modifying the database in place. This approach allows readers to continue accessing the original unaltered database while changes are committed into the WAL, enabling reading and writing to proceed concurrently [1].  

## Reader Concurrency
In WAL mode, readers can keep operating from the original unaltered database while changes are committed into the WAL. At least one source reports that reading and writing can proceed concurrently, allowing readers to see a consistent snapshot of the database even as a writer is active [1].  

## Writer Concurrency
WAL does not turn SQLite into a multi‑writer database. Readers can usually continue while a writer commits changes, but write operations are still serialized behind a single writer lock. At least one source notes that WAL mode enables concurrent readers and a single writer, eliminating reader‑writer contention [2, 3].  

## Performance Implications
The primary performance benefit of WAL is reduced contention between readers and writers, which can improve throughput for mixed workloads [1]. However, the `wal_autocheckpoint` setting governs how many pages accumulate before a passive checkpoint merges the WAL into the database. Setting this value too high can cause the WAL to bloat during write bursts, while a low value can thrash flash endurance. The balance point depends on workload characteristics [3].  

## Limitations
- The evidence does not provide quantitative metrics (e.g., throughput or latency) for WAL under concurrent workloads.  
- No source confirms that WAL allows multiple writers to operate concurrently; all evidence indicates that writes remain serialized.  
- Performance trade‑offs related to `wal_autocheckpoint` are described qualitatively; specific thresholds are not established.

## References

1. Write-Ahead Logging — https://sqlite.org/wal.html
2. SQLite WAL Mode: Concurrency, Checkpoints, and Operational Pitfalls — https://nalar.dev/sqlite-wal-mode-concurrency-checkpoints-and-operational-pitfalls/
3. WAL Optimization & Concurrency Tuning — https://productionhardening.org/wal-optimization-concurrency-tuning/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | Readers can keep operating from the original unaltered database while changes are committed into the WAL. | "Thus a COMMIT can happen without ever writing to the original database, which allows readers to continue operating from the original unaltered databas" | 2067-2281 |
| [1] | WAL provides more concurrency as readers do not block writers and a writer does not block readers. | "WAL provides more concurrency as readers do not block writers and a writer does not block readers." | 353-451 |
| [1] | WAL mode allows readers to continue while a writer commits changes by writing to a separate log file. | "WAL provides more concurrency as readers do not block writers and a writer does not block readers. Reading and writing can proceed concurrently." | 1699-1843 |
| [2] | Readers can usually continue while a writer commits changes, but WAL does not make SQLite a multi-writer datab | "Readers can usually continue while a writer commits changes, but WAL does not turn SQLite into a multi-writer database." | 805-924 |
| [3] | A high wal_autocheckpoint value causes the WAL to bloat during write bursts, whereas a low value can thrash fl | "wal_autocheckpoint governs how many pages accumulate before SQLite triggers a passive checkpoint; set it too high and the WAL bloats during write burs" | 2185-2444 |
| [3] | WAL mode allows concurrent readers and one writer, eliminating reader‑writer contention. | "PRAGMA journal_mode = WAL; -- concurrent readers + one writer; the whole point" | 2037-2124 |

---
*6 passages from 3 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*