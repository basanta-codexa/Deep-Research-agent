# Why PostgreSQL Prefers Sequential Scans Over B‑Tree Indexes

## Summary
PostgreSQL’s query planner is cost‑based and evaluates both sequential and index scans before choosing an execution plan. [1]  
It uses `amcostestimate` to compute index scan costs, factoring in index access costs and WHERE clause selectivity. [2]  
The planner also considers table statistics, cardinality, storage type, and buffer cache state when estimating the cost of a sequential scan. [3]  
When the estimated cost of a sequential scan is lower, PostgreSQL will select it even if a B‑tree index exists. [1, 4]

## Planner Decision Process
The planner constructs a cost model for each possible access method. [1]  
For an index scan, it calls `amcostestimate` with information about the index, the WHERE clauses, and any ORDER BY that can use the index. [2]  
`amcostestimate` returns estimates of startup cost, total cost, and number of tuples. [2]  
For a sequential scan, the planner assumes all pages are read from storage, regardless of buffer cache, and assigns a startup cost of zero. [3]  
The planner then compares the total costs of all viable plans and selects the one with the lowest cost. [1]

## Common Situations Leading to Sequential Scan
If a table fits in only a handful of data pages, a sequential scan is almost always chosen. [5]  
When the filtered column has few distinct values, the index provides little benefit because many rows will be returned. [5]  
Queries that return a large percentage of the table’s rows also favor sequential scans, as the overhead of index traversal outweighs the benefit. [4]  
Outdated or inaccurate statistics can mislead the planner into preferring a sequential scan. [1]  
Small tables or queries that touch most of the rows are typical cases where the planner prefers a sequential scan. [4]

## Influencing the Planner
Adjusting planner cost constants can make sequential scans more expensive, encouraging index usage. [4]  
The `enable_seqscan` GUC can be set to `off` to force the planner to consider only index scans, though this may degrade performance on other queries.  
Using `SET` statements to modify `random_page_cost` or `seq_page_cost` can shift the cost balance toward index scans for specific workloads.  
If statistics are stale, running `ANALYZE` on the table refreshes them and can lead the planner to choose an index scan. [1]

## Limitations
- The evidence does not detail exact GUC values or hint syntax for forcing index usage.  
- The decision logic is described at a high level; implementation specifics may vary across PostgreSQL versions.  
- The evidence does not cover all possible reasons for planner behavior, such as concurrent workload effects or multi‑column indexes.

## References

1. How PostgreSQL’s Query Planner Chooses (or Rejects) Your Index — https://www.cybrosys.com/research-and-development/postgres/how-postgresqls-query-planner-chooses-or-rejects-your-index
2. 63.6. Index Cost Estimation Functions — https://www.postgresql.org/docs/current/index-cost-estimation.html
3. How PostgreSQL Evaluates Execution Plans: Cost Estimation Deep Dive — https://quachthetruong.github.io/tech/postgres-cost-estimation/
4. How to Force Index Usage in PostgreSQL — https://oneuptime.com/blog/post/2026-01-25-force-index-usage-postgresql/view
5. PostgreSQL Seq Scan Despite Index: How to Fix It | Bitsfolio — https://www.bitsfolio.com/fix-postgresql-explain-analyze-seq-scan-despite-index/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | The planner’s decision is a deliberate cost‑based choice. | "This behavior is not a bug. It’s a deliberate decision made by PostgreSQL’s cost-based query planner." | 176-277 |
| [1] | PostgreSQL may choose a sequential scan if statistics are outdated or inaccurate. | "If statistics are outdated or inaccurate, the planner will make poor decisions." | 351-430 |
| [2] | The planner uses amcostestimate to estimate index scan cost based on index access costs and selectivity of WHE | "The amcostestimate function is given information describing a possible index scan, including lists of WHERE and ORDER BY clauses that have been determ" | 351-726 |
| [3] | The planner considers table statistics, cardinality, storage characteristics (SSD vs HDD), and different acces | "PostgreSQL imagines all possible execution scenarios - considering table statistics, cardinality, storage characteristics (SSD vs HDD), and different " | 929-1154 |
| [3] | For sequential scans, the startup cost is always 0 and the planner assumes all pages are read from storage reg | "For sequential scans, the startup cost is always 0 since there’s no index traversal needed - PostgreSQL can read the first tuple immediately from the " | 1226-1386 |
| [4] | The planner may choose a sequential scan for small tables or queries returning a large percentage of rows. | "For small tables or queries returning a large percentage of rows, sequential scan beats index scan:" | 446-545 |
| [4] | Making sequential scans more expensive can encourage index usage. | "Make sequential scans more expensive (encourages index usage) SELECT /*+ IndexScan(orders idx_orders_status) SeqScan(customers) */" | 549-679 |
| [5] | PostgreSQL chooses a sequential scan when the table fits in a handful of data pages. | "If your table fits in a handful of data pages, PostgreSQL will almost always choose a sequential scan." | 1194-1296 |
| [5] | PostgreSQL chooses a sequential scan when the filter column has few distinct values and many rows are returned | "If the column you're filtering on has few distinct values relative to the number of rows, an index on that column provides almost no benefit." | 1441-1582 |

---
*9 passages from 5 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*