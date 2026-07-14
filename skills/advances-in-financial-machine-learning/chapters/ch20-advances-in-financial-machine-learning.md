# Chapter 20: Multiprocessing and Vectorization

## Core Idea
Machine learning algorithms are computationally intensive; an efficient quant pipeline must use every available CPU, server, and cluster core. Python's Global Interpreter Lock (GIL) prevents true multithreading (one write-thread per processor), so parallelism in Python is achieved through **multiprocessing** — separate processes with separate memory spaces. The book's recurring helper `mpPandasObj` is finally explained: a thin multiprocessing engine that groups indivisible "atoms" into parallelizable "molecules" and dispatches them to a pool of workers. Parallelization buys both **speed** and, crucially, **memory headroom**: many financial problems are unsolvable on a single core regardless of how long you wait.

## Frameworks Introduced
- **Vectorization (array programming)**: replace nested `For`-loops with matrix algebra / compiled iterators / generators. Infers dimensionality from the input, runs underneath in C/C++, and scales to user-defined dimensions without code changes. The Cartesian-product snippet is the canonical example.
- **Single-thread vs Multithreading vs Multiprocessing**: multithreading shares one memory space (risk of concurrent writes); the GIL serializes write access to one thread per core; multiprocessing uses independent memory spaces (no write races, but harder object sharing).
- **Atoms and Molecules**: an *atom* is an indivisible task; a *molecule* is a subset of atoms processed sequentially by a single-threaded callback. Parallelization happens at the molecular level.
- **Linear partitions (`linParts`)**: split N atoms into M ≤ N subsets of equal size; molecule count = min(processors, atoms). Simple but inefficient when atoms differ in cost.
- **Two-nested loops partitions (`nestedParts`)**: for triangular structures {(i,j) | 1 ≤ j ≤ i} (or upper-triangular with `upperTriang=True`), solve the recurrence r_m so each molecule has ~equal work — a bin-packing solution that keeps all CPUs busy even with 20x cost spread across atoms. Used for SADF (Ch.17) and covariance on misaligned series.
- **Multiprocessing engine (`mpPandasObj`)**: `func`, `pdObj=(arg_name, atoms)`, `numThreads`, `mpBatches`, `linMols`, `kargs`. With `mpBatches>1` there are more molecules than cores; front-load heavy molecules so light ones fill the idle cores, cutting runtime by the ratio of heavy to light molecules.
- **Asynchronous dispatch**: `multiprocessing.Pool.imap_unordered(expandCall, jobs)` runs each molecule on one thread; `reportProgress` reports completion percentage.
- **`expandCall`**: the core trick — unwrap a job dictionary into keyword arguments of the callback. Turns a dict into a task; once understood, you can build your own engines.
- **Pickle/Unpickle workaround**: bound methods are not picklable; add the `copyreg`/`_pickle` patch at the top of the engine library (Ascher et al. 2005, §7.5).
- **On-the-fly output reduction (`processJobsRedux` + `mpJobList`)**: `redux` / `reduxArgs` / `reduxInPlace` reduce molecular outputs as they arrive (e.g. `pd.DataFrame.add`) instead of buffering a full list — avoids memory errors when outputs are large.
- **Sparse-column PCs example**: decompose Z'Z (Ch.8), load only subset Z_b of columns per molecule, compute `getPCs`, and aggregate with `redux=pd.DataFrame.add`. For large enough B the RAM is never exhausted, while molecules still run in parallel.

## Key Concepts
- The same code on a 5000-CPU cluster runs in ~1/5000 of the single-thread time; you can stack three levels of parallelism (multiprocess × vectorize × HPC-cluster nodes).
- `mpBatches = K` with one heavy molecule out of K rebalances load: every core receives equal work even though the first 10 molecules take as long as the next 20.
- Keep `numThreads = 1` for debugging — multiprocessing bugs are *Heisenbugs* (behavior changes under scrutiny).
- Only 63.2% of observations are unique in a standard bootstrap (Ch.4) — multiprocessing does not fix redundancy; pair it with sequential bootstrap.
- Parallelization is justified by memory as much as by speed: a problem requiring billions of datapoints cannot be solved single-threaded at all.

## Anti-patterns
- Writing a bespoke parallelization wrapper per function — instead build one engine that parallelizes unknown callbacks.
- Using linear partitions for two-nested-loops problems — the heaviest molecule dominates runtime.
- Storing all molecular outputs in a list before reducing — memory error on large outputs.
- Forgetting the pickle workaround — bound methods crash the pool silently.
- Debugging only with `numThreads > 1` — Heisenbugs hide; develop sequentially first.
- Vectorizing everything blindly — multiprocessing of vectorized code is still needed when the vectorized op alone does not fit in RAM.

## Key Takeaways
- Python parallelism = multiprocessing (GIL makes multithreading a non-option for CPU work).
- Atoms → molecules → jobs: structure work so a single engine can dispatch unknown functions.
- `nestedParts` solves bin-packing for triangular tasks; choose partition scheme by atom-cost variance.
- On-the-fly `redux` keeps memory bounded when outputs are large.
- Parallelization is a memory-management tool, not just a speed tool — many financial ML problems are unsolvable without it.