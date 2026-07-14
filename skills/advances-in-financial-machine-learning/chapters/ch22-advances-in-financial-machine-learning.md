# Chapter 22: High-Performance Computational Intelligence and Forecasting Technologies

## Core Idea
Authored by Kesheng Wu and Horst D. Simon (LBNL), this chapter introduces the **Computational Intelligence and Forecasting Technologies (CIFT)** project — an effort to transfer High-Performance Computing (HPC) tools from scientific supercomputing to financial streaming analytics. The trigger was the 2010 Flash Crash: SEC/CFTC took five months to investigate ~20 TB of data, citing data volume as the delay. NERSC routinely processes hundreds of TB in minutes, so the bottleneck was tooling, not data. CIFT demonstrates that HPC hardware and software (MPI, HDF5, in-situ processing) outperform cloud systems on latency-sensitive streaming workloads — for both performance and cost — and illustrates the point with six use cases spanning astronomy, fusion plasma, electricity, and finance.

## Frameworks Introduced
- **HPC vs Cloud paradigm**: HPC built for large-scale simulation (weather, physics) — optimized for turnaround time on a single shared-memory job; cloud built for parallel independent data objects (high throughput, not real-time). Financial streaming data benefits from HPC: divide one data object's analytical work across many CPU cores.
- **HPC hardware**: commercial CPUs/GPUs (same as cloud); InfiniBand intra-cluster network; **concentrated global file-system storage** (vs cloud's distributed storage). Difference is arrangement, not components.
- **Virtualization overhead**: cloud virtualizes CPU/storage/network — portable but slow. Non-optimized commercial cloud ran scientific apps 2–10x slower; PARATEC 53x slower; TCP-over-Ethernet virtualized networking barely scaled with cores. HPC avoids virtualization.
- **HPC economics**: Magellan report (Yelick 2011) found DOE centers 3–7x cheaper than commercial cloud; high-energy-physics comparison (Holzman 2017) ~50% more expensive on cloud; National Academies (2016) cloud 2–3x a long-term Amazon lease for science workloads.
- **MPI (Message Passing Interface)**: cornerstone HPC communication protocol; point-to-point + collective ops; MPICH open-source reference; wide vendor adoption via open license.
- **HDF5 (Hierarchical Data Format 5)**: datasets (array + attributes/dims/type) grouped hierarchically; efficient compression/decompression minimizes network traffic and I/O; specializations HDF5-EOS (NASA) and BioHDF (DNA). Delivered **21-fold data-access speedup** on stock-market data.
- **In-situ processing (ADIOS)**: Adaptable I/O System with the ICEE transport engine — tap the I/O stream, discard irrelevant data in-flight (avoiding slow storage), and complete writes extremely fast. Enables real-time distributed streaming analysis.
- **HPC↔Cloud convergence**: inevitable, but advocate keeping the HPC software advantages (MPI, HDF5, ADIOS) — not just the cloud model.

## Key Concepts
- **Three CIFT hardware/software pillars**: MPI (communication), HDF5 (storage), ADIOS/ICEE (in-situ streaming).
- **Supernova Hunting** (PTF, Palomar Transient Factory): automated ML workflow classified images every 45 min; SN 2011fe discovered 11 hours after first explosion evidence; 3.8% mislabel rate.
- **Blobs in Fusion Plasma (KSTAR)**: ICEE + MPI distributed workflow enabled real-time collaborative decisions between experimental runs (10–30 min windows).
- **Intraday Peak Electricity Usage (AMI)**: gradient tree boosting (GTB) overfits lagged-variable forecasts; white-box **LTAP** model uses piece-wise linear daily-usage-vs-temperature relation and stays self-consistent for year T−1 predictions, controlling self-selection bias in pricing trials.
- **Flash Crash 2010**: HDF5 + C++ implementation of **VPIN** (Volume-Synchronized Probability of Informed Trading) and **HHI** (Herfindahl-Hirschman Index of market fragmentation) with MPI. Single-core: 603.98 s (HDF5) vs ~3.5 h (ASCII); 512 cores: 2.58 s — **234x** speedup; HDF5 indexing added another 3.7x.
- **VPIN Calibration**: 67 months, 100 futures contracts; HPC algorithmic improvement alone delivered **720x** speedup (before parallelization). False-positive rate cut from 20% to 7% with median-bar pricing, 200 buckets/day, 30 bars/bucket, 1-day support window, Student-t (ν=0.1) bulk-volume classification, CDF threshold 0.99. Parameter-insensitivity (threshold 0.9→0.99 did not cut events 10x) confirms events are *intrinsic*, not random.
- **Non-uniform FFT**: applied to natural-gas futures tick prices — a strong once-per-minute (527,040 = 366·24·60) component >10x stronger than neighbors reveals TWAP algorithmic trading; leap-year frequency 366 (not 365) validates the method; twice-a-day (732) and once-a-week (52) cycles expected.

## Anti-patterns
- Treating cloud virtualization as free — networking virtualization alone can render the cloud useless for streaming work.
- Defaulting to ASCII / CSV for multi-TB tick data — HDF5 reduces I/O by an order of magnitude and supports indexing.
- Computing early-warning indicators (VPIN, HHI) on a single core — they arrive too late to act.
- Overfitting model parameters per contract when global VPIN parameters already give 7% false positives across all futures.
- Predicting on lagged-variable GTB for streaming electric load — error accumulation makes forecasts unrealistic within a month; prefer the self-consistent white-box LTAP.
- Extrapolating Fourier results from alphabetical/chronological time — sampling by an activity index (e.g. VPIN's volume clock) is usually more informative.

## Key Takeaways
- For latency-sensitive streaming analytics, HPC beats cloud on both performance (no virtualization overhead) and cost (3–7x cheaper).
- MPI + HDF5 + ADIOS/ICEE is the HPC software stack worth preserving as HPC and cloud converge.
- HPC is a *decision-speed* tool: a 720x speedup turns a daily VPIN into a real-time early-warning indicator.
- CIFT demonstrated concrete wins in six domains — astronomy, fusion, electricity, and three finance cases — proving HPC transfers cleanly to business streaming analytics.
- Non-uniform FFT is a reusable signal-processing lens for exposing algorithmic (TWAP, per-minute) trading in any market.