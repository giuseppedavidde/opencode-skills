---
name: advances-in-financial-machine-learning
description: "Knowledge base from 'Advances in Financial Machine Learning' by Marcos M. López de Prado."
---
# Advances in Financial Machine Learning
**Author**: Marcos M. López de Prado | **Chapters**: 22 | **Generated**: 2026-07-14

López de Prado argues that **financial machine learning is a distinct subject**, not standard ML applied to finance: overlapping labels, non-IID observations, backtest overfitting, and regime changes break textbook tools. The book is a production-line recipe covering data structures, labeling, weighting, modelling, cross-validation, backtesting, feature engineering, allocation, and HPC.

## Core Frameworks & Mental Models

**1. Meta-Strategy Paradigm (Ch.1).** Quant firms that hire 50 PhDs each to deliver a strategy in six months always fail (Sisyphus Paradigm → overfit backtests or overcrowded factor investing). Successful firms run an assembly line: Data Curators → Feature Analysts → Strategists → Backtesters → Deployment → Portfolio Oversight (Embargo → Paper Trading → Graduation → Re-allocation → Decommission). Only microscopic alpha remains and it requires industrial methods.

**2. Information-Driven Pipeline (Ch.2–5).** Build the universe from information-driven bars (TIB/VIB/DIB, TRB/VRB/DRB) and the ETF trick; label with the **Triple-Barrier Method** and decouple side from size via **Meta-Labeling**; weight by **average uniqueness** + **sequential bootstrap**; make features stationary with **Fractional Differentiation (FFD)**, preserving memory where integer differentiation loses it.

**3. Honest Cross-Validation & Backtesting (Ch.7–14).** Standard K-fold leaks because observations are not IID. Use **Purged K-Fold + Embargo**, then **Combinatorial Purged Cross-Validation (CPCV)** to obtain a *distribution* of Sharpe ratios. Reject strategies with the **Deflated Sharpe Ratio (DSR)** under multiple testing. Two laws: *"Backtesting is not a research tool — feature importance is"* and *"Backtesting while researching is like drinking and driving."*

**4. Feature Importance as Research Loop (Ch.8).** MDI (in-sample, tree), MDA (OOS permutation, any classifier — can be negative), SFI (single feature, no substitution effects). Orthogonalize via PCA before MDI/MDA to alleviate linear substitution. Compare importance across regimes/instruments via rank correlation.

**5. Strategy & Portfolio Risk (Ch.15–16).** **Strategy risk ≠ portfolio risk** — a low-vol book can still fail to deliver a target Sharpe. Compute the precision-PDF integral below the implied precision p*. For allocation use **Hierarchical Risk Parity (HRP)**: tree-cluster on correlation distance → quasi-diagonalize → recursive bisection with 1/σ² weights. Avoids Markowitz's Curse (higher correlation → more leverage → less stable inverse).

**6. Financial Features (Ch.17–19).** Detect regime change with **SADF/CADF/SMT** on log prices (bubbles → spikes; O(T²) → needs HPC). Quantify market efficiency / structure with **Shannon entropy, mutual information, Lempel-Ziv**. Capture liquidity with **Kyle/Amihud/Hasbrouck lambda** and informed-trade probability with **PIN / VPIN** microstructural features.

**7. High-Performance Computing (Ch.20–22).** Python parallelism = multiprocessing (GIL blocks true multithreading); atoms → molecules via `linParts`/`nestedParts` and `mpPandasObj` with `mpBatches>1` and on-the-fly `redux`. For NP-hard dynamic allocation, discretize to **integer optimization** and hand to a **quantum annealer**. For streaming analytics the **HPC stack (MPI + HDF5 + ADIOS/ICEE)** beats cloud on both latency (no virtualization overhead) and cost (3–7x cheaper); CIFT reports 234x–720x speedups on VPIN/HHI.

## Chapter Index

| # | Title | Key Frameworks |
|---|---|---|
| 1 | Financial Machine Learning as a Distinct Subject | Sisyphus vs Meta-Strategy paradigm; production-chain structure; Portfolio Oversight lifecycle; microscopic alpha |
| 2 | Financial Data Structures | Fundamental/Market/Analytics/Alternative data; Time/Tick/Volume/Dollar bars; Imbalance & Runs bars; tick rule; ETF trick; PCA weights; single-future roll; CUSUM filter |
| 3 | Labeling | Fixed-time horizon (fails); dynamic thresholds; Triple-Barrier Method; learning side & size; Meta-Labeling; quantamental way |
| 4 | Sample Weights | Overlapping outcomes; # concurrent labels; average uniqueness; sequential bootstrap; return attribution; piecewise-linear time decay; class weights |
| 5 | Fractionally Differentiated Features | Stationarity vs memory dilemma; fractional difference operator; expanding-window vs fixed-width (FFD); minimum d* with ADF p<5% |
| 6 | Ensemble Methods | Bias-varariance decomposition; Bagging; RF; Boosting/AdaBoost; bagging for scalability; bagging helps only if ρ→0 |
| 7 | Cross-Validation in Finance | Why K-fold fails; purging; embargo; PurgedKFold; leakage = joint (X,Y) overlap |
| 8 | Feature Importance | First Law of Backtesting; MDI; MDA (permutation); SFI; PCA orthogonalization; parallelized vs stacked importance |
| 9 | Hyper-Parameter Tuning with Cross-Validation | Grid search with purging (clfHyperFit); MyPipeline sample-weight fix; randomized search; log-uniform distribution; scoring=f1 / neg_log_loss |
| 10 | Bet Sizing | Strategy-independent sizing; concave f[p,I,d]; averaging active bets; size discretization; dynamic bet sizes & limit prices |
| 11 | The Dangers of Backtesting | Seven Sins; Mission Impossible; PBO via CSCV; Second Law; recommendations; strategy selection |
| 12 | Backtesting through Cross-Validation | Walk-Forward pitfalls; CV method; Combinatorial Purged CV (CPCV); distribution of Sharpe ratios; overfitting control |
| 13 | Backtesting on Synthetic Data | Trading rule as parameter set; overfit trading rule; discrete O-U process; 5-step OTR algorithm; OTR Conjecture (unique optimum) |
| 14 | Backtest Statistics | Types; time- vs dollar-weighted; hits; runs (HHI); drawdown/TuW; Sharpe; PSR; DSR; efficiency; classification scores |
| 15 | Understanding Strategy Risk | Symmetric payouts (θ depends on precision); asymmetric payouts; implied betting frequency; probability of strategy failure via precision-PDF |
| 16 | Machine Learning Asset Allocation | Convex-optimization problems; Markowitz's Curse; hierarchical relationships; HRP (tree-cluster → quasi-diag → recursive bisection); inverse-variance; OOS Monte Carlo |
| 17 | Structural Breaks | CUSUM (Brown-Durbin-Evans, Chu-Stinchcombe-White); Chow-type Dickey-Fuller; SADF; QADF; CADF; sub/super-martingale tests |
| 18 | Entropy Features | Shannon entropy; Kolmogorov complexity; mutual information; plug-in estimator; Lempel-Ziv; encoding schemes; Gaussian-process entropy; generalized mean |
| 19 | Microstructural Features | Tick rule; Roll model; high-low volatility; Corwin-Schultz; Kyle/Amihud/Hasbrouck lambda; PIN; VPIN; what is microstructural information |
| 20 | Multiprocessing and Vectorization | Vectorization; single-thread vs multithreading vs multiprocessing (GIL); atoms & molecules; linParts/nestedParts; mpPandasObj; async dispatch; expandCall; pickle workaround; on-the-fly redux; sparse-column PCs |
| 21 | Brute Force and Quantum Computers | Combinatorial optimization; qubits & superposition; objective with generic transaction costs; non-convexity; pigeonhole partitions; Ω and Φ trajectory sets; integer optimization; static vs dynamic solution; foundation for Rosenberg et al. 2016 quantum annealer |
| 22 | High-Performance Computational Intelligence and Forecasting Technologies | CIFT project; Flash Crash motivation; HPC vs cloud; virtualization overhead; HPC economics; MPI; HDF5; ADIOS/ICEE; use cases (supernova, fusion blobs, LTAP electricity, VPIN/HHI, VPIN calibration, non-uniform FFT) |

## Topic Index

**Backtesting**: 11, 12, 13, 14, 15
**Cross-Validation / Leakage**: 7, 9, 12
**Feature Engineering**: 5, 8, 17, 18, 19
**High-Performance Computing**: 20, 21, 22
**Labels & Weights**: 3, 4, 10
**Memory & Stationarity**: 5
**ML Models**: 6
**Allocation**: 16, 21
**Quantum Computing**: 21
**Risk**: 15
**Data Structures / Bars**: 2
**Strategy Lifecycle / Overfitting**: 1, 11
**Structural Breaks**: 17
**Entropy**: 18
**Microstructure**: 19
**Multiprocessing**: 20
**Streaming Analytics**: 22

## Supporting Files
- [glossary.md](glossary.md)
- [patterns.md](patterns.md)
- [cheatsheet.md](cheatsheet.md)

### Chapter Files
All chapter notes live in [`chapters/`](chapters/): `ch01` … `ch22`, each named `chNN-advances-in-financial-machine-learning.md` with sections Core Idea, Frameworks Introduced, Key Concepts, Anti-patterns, and Key Takeaways.