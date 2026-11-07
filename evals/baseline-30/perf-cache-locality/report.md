# Row‑Major vs Column‑Major Iteration: Cache‑Based Performance Insights

## Summary
Row‑major storage aligns contiguous memory with inner‑loop indices, enabling efficient cache line utilization during traversal. Spatial locality ensures that sequential reads prefetch entire cache lines, reducing memory latency. Column‑wise iteration on a row‑major layout typically fetches one element per cache line, leading to poor cache reuse. Empirical data from Mojo on an M2 MacBook Pro shows measurable speed differences between row‑major and column‑major orders. [1, 2]

## Memory Layout of Two‑Dimensional Arrays
Row‑major storage aligns contiguous memory with inner‑loop indices, enabling efficient cache line utilization during traversal. [1] The evidence focuses on row‑major storage, where elements of a row are laid out consecutively in memory. [1]

## Spatial Locality and Cache Lines
Arrays benefit from spatial locality: sequential reads use cache lines and hardware prefetchers. [3] On modern CPUs, an array can be ~3× faster than a linked list for the same traversal because of spatial locality and cache line behavior. [3]

## Row‑Major Iteration and Cache Efficiency
Row‑major iteration consumes each cache line almost fully before moving to the next line, providing excellent locality. [1] Column‑wise traversal on row‑major storage often touches one element per cache line and moves on, wasting most of the fetched data. [1]

## Empirical Benchmarks
Mojo outperforms NumPy in both row‑major and column‑major order on an M2 MacBook Pro, indicating that the choice of traversal order can influence performance even in high‑level frameworks. [2] No additional benchmark data for matrix‑vector multiplication or other operations is present in the evidence.

## Limitations
- The evidence does not specify which other common languages use row‑major or column‑major order beyond the discussed examples.  
- Benchmark data is limited to Mojo versus NumPy on a single hardware platform; broader comparisons across languages and workloads are not covered.  
- The analysis assumes standard cache line sizes (e.g., 64 bytes) and typical integer sizes; variations in hardware or data types may alter the observed effects.

## References

1. Performance Analysis of Row-Major and Column-Major Iteration in C: What Actually Makes One Loop Faster – TheLinuxCode — https://thelinuxcode.com/performance-analysis-of-row-major-and-column-major-iteration-in-c-what-actually-makes-one-loop-faster/
2. Modular: Row-major vs. Column-major Matrices: A Performance Analysis in Mojo and NumPy — https://www.modular.com/blog/row-major-vs-column-major-matrices-a-performance-analysis-in-mojo-and-numpy
3. CPU Caches and Spatial Locality: Why an Array is 3x Faster Than a Linked List for the Exact Same Big-O Complexity | Ankit Rana — https://ankit-rana.com/logs/18-cpu-caches-spatial-locality/

## Evidence appendix

| ref | claim | quote | span |
| --- | --- | --- | --- |
| [1] | Row‑major iteration consumes each cache line almost fully before moving to the next line, providing excellent  | "Modern CPUs fetch memory in cache lines, commonly 64 bytes. With int at 4 bytes, one line holds 16 elements. Row-major iteration through matrix[i][j] " | 351-612 |
| [1] | Column‑wise traversal on row‑major storage often touches one element per cache line, wasting most of the fetch | "Column-wise traversal on row-major storage often touches one element per cache line and moves on. You pay for 64 bytes and use 4 bytes right away. The" | 1311-1495 |
| [2] | Mojo outperforms NumPy in both row‑major and column‑major order on an M2 MacBook Pro. | "In the red box below, you can see the performance difference on my M2 MacBook Pro using Mojo. In the purple box, you can see that Mojo also outperform" | 2155-2359 |
| [3] | An array can be ~3x faster than a linked list for the same traversal because of spatial locality and cache lin | "On modern CPUs, an array can be ~3x faster than a linked list for the same traversal because of spatial locality and cache line behavior." | 74-211 |
| [3] | Arrays benefit from spatial locality: sequential reads use cache lines and hardware prefetchers. | "Arrays benefit from spatial locality: sequential reads use cache lines and hardware prefetchers." | 565-661 |

---
*5 passages from 3 sources. Every quote was located in the fetched page at the character offset shown in the appendix before this was written.*