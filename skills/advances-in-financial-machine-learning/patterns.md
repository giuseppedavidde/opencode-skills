# Patterns — Advances in Financial Machine Learning

Reusable setups distilled from the 22 chapters. Each pattern lists **When** to apply it, **How**, and **Trade-offs**.

## Labeling & Sample Weighting

### Triple-Barrier Meta-Labeling
**When**: you have a directional primary model (or discretionary PM) but want an ML-controlled size and entry filter.
**How**: primary sets side ∈ {−1,+1}; triple barriers (dynamic pt/sl multiples + vertical expiry) label the path; secondary classifier learns {0,1} take/pass; bet size = f(secondary probability). Use scoring='f1' (Ch.9).
**Trade-offs**: decouples side from size, limits overfit damage, enables long/short secondary models — but the primary must already achieve high recall; meta-labeling only buys precision.

### Average-Uniqueness Sample Weights
**When**: overlapping labels from triple-barrier or path-dependent events make observations non-IID.
**How**: c_t = concurrent labels; ū_i = mean_t(1_{t,i}/c_t); weight = uniqueness × |attributed return|; pair with sequential bootstrap and bagging `max_samples=avgU`.
**Trade-offs**: honest OOB accuracy at the cost of slightly fewer effective observations — better than inflated inflating OOB estimates.

## Cross-Validation & Backtesting

### Purged K-Fold + Embargo
**When**: fitting, backtesting, or scoring any financial model with overlapping labels.
**How**: purging drops training labels overlapping test labels; embargo drops a small training gap h≈0.01T after every test. Confirm performance no longer improves as k→T.
**Trade-offs**: loses ~a few % of training observations vs eliminating leakage-induced false positives — net positive.

### Combinatorial Purged Cross-Validation (CPCV)
**When**: you need a *distribution* of Sharpe ratios, not a single walk-forward path.
**How**: pick N groups and test-size k; φ[N,k]≥1 backtest paths; purge overlapping labels; embargo when test precedes train. Increase k until the Sharpe spread reveals brittleness.
**Trade-offs**: more paths ⇒ better inference but more computation and more overfitting surface; keep φ small enough to stay honest.

### Deflated Sharpe Ratio (DSR) Gate
**When**: selecting a strategy from many trials.
**How**: compute PSR with SR* set to the expected maximum SR under multiple testing; reject unless DSR > threshold. Log every backtest to inform SR*.
**Trade-offs**: conservative — may discard marginal real edges; preferable to the alternative (reporting overfit alphas).

### Structural-Break Check Before Backtest
**When**: regime change could invalidate a static backtest.
**How**: run SADF/CADF/SMT on log prices (Ch.17); flag bubbles and breaks; segment performance attribution by regime.
**Trade-offs**: O(T²) for SADF — run via `mpPandasObj` (Ch.20).

## Feature Engineering

### FFD Minimum-d* Stationarity
**When**: price-like features are non-stationary but integer returns erase memory.
**How**: cumsum → FFD(d) for d∈[0,1] → take minimum d* with ADF p<5% → use FFD(d*) as the predictive feature.
**Trade-offs**: preserves ~0.995 correlation with the original series vs 0.03 for d=1 — at the cost of a small stationarity check.

### Orthogonal-Feature Importance (PCA + MDI/MDA)
**When**: correlated features dilute importance (substitution effects).
**How**: standardize Z, PCA to ≥95% variance → P; run MDI (in-sample, max_features=1) and MDA (OOS, F1/neg-log-loss) on P; supplement with SFI for non-substituted single features.
**Trade-offs**: loses the original-feature interpretation; recover via loadings.

### Information-Driven Bars + CUSUM Sampling
**When**: time bars produce heteroscedasticity, serial correlation, non-normality.
**How**: build TIB/VIB/DIB (or TRB/VRB/DRB) bars; then apply a CUSUM filter to trigger features only on cumulative runs of length h.
**Trade-offs**: better statistical properties vs added complexity in bar construction.

## Asset Allocation

### Hierarchical Risk Parity (HRP)
**When**: covariance is ill-conditioned (Markowitz's Curse) and CLA underperforms OOS.
**How**: distance d=√(½(1−ρ)); hierarchical linkage → dendrogram; quasi-diagonalize; recursive bisection with inverse-variance weights.
**Trade-offs**: weaker in-sample optimality than CLA but lower OOS variance; no covariance inverse — robust.

## Computing & Execution

### mpPandasObj with nestedParts + mpBatches>1
**When**: atom costs are heterogeneous (two-nested-loops, SADF, covariance on misaligned series) or outputs are large.
**How**: `nestedParts` balances molecule work; `mpBatches>1` front-loads heavy molecules; `redux=pd.DataFrame.add` reduces on the fly to bound RAM.
**Trade-offs**: more bookkeeping vs near-linear scaling and feasibility on RAM-limited problems.

### HDF5 + HPC for Early-Warning Indicators
**When**: indicators (VPIN, HHI) must compute on multi-TB tick data before the next event arrives.
**How**: store bars in HDF5 with indexing; implement in C++ with MPI; benchmark single-core to multi-core speedup (CIFT reports 234x–720x).
**Trade-offs**: HPC devops overhead vs decision-speed and 3–7x cost savings vs cloud.

### Integer-Optimization → Quantum for NP-hard Allocation
**When**: dynamic portfolio problem with non-continuous transaction costs that defeat convex solvers.
**How**: pigeonhole-partition K capital units among N assets; Ω = partitions × {−1,1}^N signs; Φ = Ω × H trajectories; evaluate all and pick global optimum. Discretize → hand to quantum annealer.
**Trade-offs**: global optimum and generality vs exponential compute — only viable with quantum hardware.

## Strategy Risk Sizing

### Strategy-Risk Precision PDF
**When**: judging whether a strategy can deliver a target Sharpe θ* given its bet distribution.
**How**: estimate π_−, π_+ (mixture of two Gaussians via EF3M); annual n; bootstrap p over k-year windows; KDE f[p]; strategy risk = ∫_{p≤p*} f[p] dp where p* is implied by θ*.
**Trade-offs**: separates parameters under the PM's control from the market's; rejects low-volatility-but-high-failure-probability strategies that traditional portfolio risk keeps.

### Concave Bet Sizing with Discretization
**When**: translating probabilities into position sizes.
**How**: m = concave(p) calibrated to concurrent longs/shorts and divergence d; m' = round(m/d)·d for discretization; set breakeven limit price from a sigmoid schedule.
**Trade-offs**: a small amount of optimality for a large reduction in turnover, commissions, and slippage.