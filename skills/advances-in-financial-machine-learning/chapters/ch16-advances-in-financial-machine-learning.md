# Chapter 16: Machine Learning Asset Allocation

## Core Idea
Markowitz's mean-variance optimization (and its Critical Line Algorithm) is **structurally unstable** in the real world: it inverts the covariance matrix, and the more correlated the assets, the more the optimizer demands leveraged offsetting positions ("Markowitz's Curse"). The chapter introduces **Hierarchical Risk Parity (HRP)**, which replaces quadratic programming with hierarchical clustering — it requires no covariance inversion, works on singular matrices, allocates top-down through a dendrogram, and beats CLA out-of-sample even though CLA's objective IS minimum variance.

## Frameworks Introduced
- **The problem with convex portfolio optimization**: CLA's instability, concentration, underperformance out-of-sample.
- **Markowitz's Curse**: higher correlation → more need to diversify → optimizer leverages more → covariance inversion more unstable → solutions blow up.
- **From geometric to hierarchical relationships**: covariance matrices are *flat* (every pair equally related); trees encode *hierarchy* (asset classes → sectors → individual securities, weights distributed top-down).
- **Hierarchical Risk Parity (HRP)** — three stages:
  1. **Tree clustering**: distance = sqrt(½(1−ρ)) on correlation matrix, hierarchical linkage → dendrogram.
  2. **Quasi-diagonalization**: reorder rows/cols so similar assets sit adjacently.
  3. **Recursive bisection**: top-down, split each cluster into two, allocate inverse-variance weights recursively (appendix A).
- **Inverse Variance Allocation**: weight within a cluster ∝ 1/σ² — does not need a covariance inverse.
- **Out-of-sample Monte Carlo**: HRP delivers lower OOS variance than CLA despite CLA optimizing for min-variance. HRP also outperforms on historical data.
- **Herfindahl-style diversification measure** to quantify concentration.

## Key Concepts
- Inverting the covariance matrix compounds estimation errors — small perturbations in ρ cause large allocation swings.
- HRP is robust to ill-degenerate / singular covariance (no matrix inverse, no convex program).
- HRP recommends *concentration within diversified clusters* — the opposite of Markowitz's "spread across correlated assets with leverage."
-unsupervised; it doesn't need expected returns (the most error-prone input).
- Recursive bisection guarantees a top-down allocation consistent with the tree hierarchy.

## Anti-patterns
- Running Markowitz CLA / quadratic optimizer with noisy sample covariance on highly correlated assets.
- Feeding expected returns estimates (least reliable input) to the optimizer.
- Assuming a min-variance objective guarantees low realized variance — sample instability makes OOS variance worse.
- Treating covariance as a flat Euclidean object with no hierarchy.
- Leveraging "diversifying" positions when correlation spikes (exactly when diversification fails).

## Key Takeaways
1. Markowitz's curse inverts: high correlation demands leverage, leverage destabilizes the solution.
2. HRP replaces a convex program with a hierarchical clustering + recursive bisection.
3. HRP needs no covariance inversion and no expected-return estimates; it allocates from distance(ρ) alone.
4. HRP consistently beats CLA out-of-sample, even though CLA IS the minimum-variance optimizer.
5. Use HRP for multi-asset allocation, signal-strategy blending, and any allocation where correlation is unstable.