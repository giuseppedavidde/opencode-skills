# Chapter 7: Portfolio Construction

## Core Idea
Markowitz's mean-variance optimization is mathematically correct but numerically unstable in finance, and the **instability is caused by signal, not just noise**. When clusters of securities are highly correlated, the covariance matrix's condition number explodes — "Markowitz's curse": the more you need Markowitz, the more unstable it is. The **Nested Clustered Optimization (NCO)** algorithm, an ML-based wrapper, splits the optimization into intracluster and intercluster subproblems to contain the instability, halving the RMSE of Markowitz out-of-sample.

## Frameworks Introduced
- **Quadratic-programming formulation**: `min_ω ½ ω'Vω` s.t. `ω'a = 1`, with closed-form `ω* = V⁻¹a / (a'V⁻¹a)`; the characteristic vector `a` yields the naïve (1/N), inverse-variance, minimum-variance, and maximum-Sharpe portfolios as special cases.
- **Condition number diagnosis**: `max|λ| / min|λ|` of the correlation matrix; for a 2×2 case it diverges as `ρ → ±1`. Trace is fixed at `N`, so eigenvalues grow only at the expense of others.
- **Markowitz's curse**: the solution is guaranteed stable only when `ρ ≈ 0` — i.e. exactly the case where diversification help is unnecessary.
- **Block-diagonal signal instability**: a 500×500 matrix with two blocks at intracluster corr 0.5 has condition number 251 — structural, independent of `N/T`, and not cured by more observations.
- **Hierarchical Risk Parity (HRP)** (López de Prado 2016): the precursor ML allocation method that beats Markowitz out-of-sample despite being suboptimal in-sample.
- **Nested Clustered Optimization (NCO)**: (1) cluster the (denoised) correlation matrix via ONC; (2) solve intracluster allocations; (3) form the reduced covariance `cov2 = W_intra' · cov1 · W_intra` and solve the intercluster allocation; (4) final `ω = W_intra · ω_inter` — a wrapper compatible with any frontier member and any constraint set.

## Key Concepts
- **Three classical instability remedies**: priors (Black–Litterman), extra constraints (Clarke et al.), covariance shrinkage (Ledoit–Wolf) — all address *noise*, none address *signal*.
- **Separation theorem**: any unconstrained efficient-frontier portfolio is a convex combination of the minimum-variance and maximum-Sharpe portfolios — so testing these two is sufficient.
- **Dominant block propagation**: the condition number is governed by the highest-correlation cluster; reducing correlation in weaker blocks does not help — instability must be contained at the dominant cluster.
- **`NCO` as wrapper / modular design**: agnostic to the inner optimizer (CLA, min-variance, max-Sharpe, Black-Litterman, shrinkage); can be recursively nested for hierarchical clusters-within-clusters.
- **Monte Carlo validation**: `formTrueMatrix` defines a ground-truth `{μ_0, V_0}`, `simCovMu` draws empirical estimates, RMSE of `ω̂ vs ω_0` is measured across 1,000 simulations.

## Anti-patterns
- **Attributing all mean-variance instability to noise**: signal-induced instability is structural, governed by cluster correlation, and cannot be reduced by sampling more observations — only by restructuring the problem.
- **Relying on Ledoit–Wolf shrinkage alone**: experiments show shrinkage cuts RMSE only ~12% (min-var) to ~7% (max-Sharpe); combining shrinkage with NCO is *worse* than NCO alone — shrinkage adds no value here.
- **Calling NCO "optimal"**: NCO is suboptimal in-sample by construction — its purpose is robustness out-of-sample, not theoretical optimality. Selling it as in-sample-optimal misunderstands the method.
- **Ignoring the condition number before optimizing**: deploying Markowitz on a covariance matrix with a high condition number guarantees unstable, transaction-cost-eroding allocations.
- **Clustering `corr1` vs. `corr1.abs()` blindly**: for long-short portfolios with negative correlations, clustering the absolute correlation is usually better — flipping sign via negative weights injects instability that must be contained within a cluster.
- **Treating NCO as a fixed black box**: it is a modular strategy; when the matrix is strongly hierarchical, NCO should be *recursively* applied to subclusters, mirroring the tree.
- **Setting `maxNumClusters` without thought**: single-item clusters do not raise the condition number, so the default `N/2` is principled — but deliberately mis-setting it (e.g. to 2) still beats Markowitz, demonstrating that *containment* matters more than perfect clustering.
- **Always using one optimization method**: the Monte Carlo protocol lets you pick the most robust optimizer *per case* — rigid adherence to a single method is a misuse of the framework.

## Key Takeaways
1. Markowitz's curse: mean-variance optimization is numerically stable only when `ρ ≈ 0`, precisely when it is least needed.
2. Signal — not just noise — is a primary source of covariance instability; it is structural and survives larger samples.
3. NCO contains the instability by clustering, optimizing intracluster, then optimizing across clusters via the reduced (near-diagonal) covariance — translating a Markowitz-cursed problem into a well-behaved one.
4. In Monte Carlo, NCO achieves ~47% (min-var) and ~55% (max-Sharpe) RMSE *reductions* vs. Markowitz on a 50-security portfolio; Ledoit–Wolf shrinkage adds no value on top.
5. NCO is modular and hierarchical: it wraps any frontier member and constraint set, and can be recursively nested for clusters-within-clusters — choose the optimizer opportunistically per dataset via Monte Carlo.