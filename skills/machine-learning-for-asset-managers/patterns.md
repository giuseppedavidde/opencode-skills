# Patterns — Machine Learning for Asset Managers

Applied setups derived from chapters 2, 4, 6, 8 (the four technical chapters in this skill). Each pattern lists **When** to use it, **How** to apply it, and **Trade-offs**.

---

## Pattern 1 — Denoise a covariance matrix before any downstream computation (Ch.2)

**When**: You are about to compute a regression, optimize a portfolio, run Monte Carlo, cluster securities, or build a factor-based covariance matrix from a noisy empirical covariance/correlation matrix (T not vastly larger than N).

**How**:
1. `eVal, eVec = getPCA(corr)` from the empirical correlation matrix.
2. Fit the Marcenko–Pastur PDF to the KDE of eigenvalues (`findMaxEval`) to recover `λ+` and the implied noise variance `σ²`. Count signal factors `nFacts = N − position of λ+` in descending eigenvalues.
3. Replace noise eigenvalues with their trace-preserving average (`denoisedCorr`, constant-residual-eigenvalue method). Targeted shrinkage (`denoisedCorr2`) is an alternative if you need finer control via `α`.
4. Rescale the diagonal to 1.

**Trade-offs**:
- Constant-residual-eigenvalue preserves trace and signal; targeted shrinkage lets you tune the noise-vs-signal trade but adds a hyperparameter `α`.
- Ledoit–Wolf shrinkage is simpler but dilutes signal; do not use as a one-stop replacement.
- Fitting requires choosing KDE bandwidth; cross-validate it if accuracy matters.

---

## Pattern 2 — Detone before clustering (Ch.2 + Ch.4)

**When**: Clustering a correlation matrix that has a strong market/common component (typical of equity universes). Without detoning, the algorithm cannot find dissimilarities across clusters.

**How**:
1. Denoise first (Pattern 1).
2. Identify the market component(s) — first eigenvector(s) with loadings ≈ `N^{-1/2}`.
3. Subtract `W_M Λ_M W_M'` from the denoised matrix; rescale diagonal to 1.
4. Cluster the detoned matrix with ONC (Pattern 4).
5. For portfolio optimization on a detoned (singular) matrix: optimize in principal-component space then map back `ω* = W_₊ᵀ f*`.

**Trade-offs**:
- Detoned matrix is singular — fine for clustering and PCA-space optimization, *not* directly usable for vanilla mean-variance.
- Removing too many market components can erase a real risk factor; statistically test the hypothesis that the component is "the market" first.

---

## Pattern 3 — Use information-theoretic distance instead of correlation when the relationship is nonlinear (Ch.3)

**When**: You are building a proximity matrix and the variables may have nonlinear codependency; correlation misses it (e.g., `y = 100|x| + ε` gives `corr ≈ 0` but strong relationship).

**How**:
1. Discretize continuous variables with optimal binning (`numBins`, Hacine-Gharbi).
2. Compute mutual information `I[X;Y]` and normalized variation of information `ṼI[X;Y] = 1 − I/H[X,Y]` — a true metric bounded in [0,1].
3. Use `ṼI` as the dissimilarity for clustering / proximity matrices.

**Trade-offs**:
- `ṼI` requires discretization for continuous variables; suboptimal binning biases the estimate.
- Correlation-based distance `d_ρ = sqrt(0.5(1−ρ))` is cheaper and fine for purely linear structures.
- Mutual information is *not* a metric (no triangle inequality); use normalized `ṼI` when you need a metric.

---

## Pattern 4 — Recover the optimal number of clusters with ONC (Ch.4)

**When**: You need to partition objects into an unknown number of clusters without an arbitrary threshold.

**How**:
1. Build the observations matrix `Xᵢⱼ = sqrt(0.5·(1−ρᵢⱼ))` (option c) and standardize.
2. For large N, project onto the low-dim PCA space of eigenvalues > `λ+` (Ch.2).
3. Run `clusterKMeansBase` — double for-loop over `k=2..N` and `n_init` restarts — pick the partition maximizing `q = E[{Sᵢ}] / sqrt(V[{Sᵢ}])`.
4. Run `clusterKMeansTop` — re-cluster below-average-quality clusters recursively, keep new clustering only if average cluster quality improves.

**Trade-offs**:
- Computation is `O(n_init · N · k-means cost)`; can be expensive for very large N.
- The base algorithm is k-means; biclustering needs similarity (reciprocal of distance), not distance.
- ONC is agnostic to the observation matrix — use distance of distances, variation of information, or other metric.

---

## Pattern 5 — Clustered Feature Importance (CFI) for theory discovery (Ch.6)

**When**: You have many features, suspect multicollinearity, and want to identify which *clusters* of features overfit a model. This is the book's core research tool.

**How**:
1. Compute the features' correlation matrix (or normalized variation of information) and denoise/detone it.
2. Run ONC (Pattern 4) to get K feature-clusters.
3. If silhouette scores are low: residualize each feature against out-of-cluster features to remove cross-cluster information.
4. Fit a random forest on the original features.
5. **Clustered MDI**: sum per-tree feature MDI within each cluster; mean/std via CLT.
6. **Clustered MDA**: shuffle all features in a cluster simultaneously; compute cross-validated performance decay (use log-loss or PWA, not accuracy).
7. Rank clusters by importance; the noise cluster should fall to ~0 while informative+redundant clusters rank together.

**Trade-offs**:
- Clustered MDI is in-sample (still cheap, no CV); Clustered MDA is cross-validated (more expensive but solves all 4 p-value caveats).
- Clustering in correlation space misses nonlinear redundancy — prefer normalized variation of information for the proximity matrix in financial datasets.
- More clusters ⇒ more granular attribution ⇒ less substitution bias, but smaller per-cluster sample → noisier importance.

---

## Pattern 6 — Evaluate a backtest for false discovery (Ch.8)

**When**: You (or someone) ran multiple backtests and are about to act on the best Sharpe ratio.

**How** (two complementary procedures):
- **Deflated Sharpe Ratio**:
  1. Collect the K backtested return series.
  2. Run ONC on their correlation matrix → `E[K]` effective independent trials; use minimum-variance cluster-return weighting to estimate `V[{ŜR_k}]`.
  3. Compute expected max SR under H0 via the False Strategy theorem: `E[max{ŜR_k}] ≈ f(E[K], V[{ŜR_k}])`.
  4. Compute `DSR = Z[(ŜR − E[max{ŜR_k}])·sqrt(T−1) / sqrt(1 − γ̂₃ ŜR + ((γ̂₄−1)/4)·ŜR²)]`.
  5. Reject H0 only if `DSR ≪ α_K`.
- **FWER via Šidàk**:
  1. Compute `ẑ[0] = ŜR·sqrt(T−1) / sqrt(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²)`.
  2. Single-trial `α = 1 − Z[ẑ[0]]`; correct `α_K = 1 − (1−α)^E[K]`.
  3. Reject H0 if `α_K < threshold`.

**Trade-offs**:
- DSR is a probability; FWER is a corrected α — they answer different questions, apply both.
- ONC on the trials is the costly step but it is also the conservative estimate: true K ≤ effective K, so the correction is on the conservative side.
- Assuming Normal returns understates the false-positive rate — always pass γ̂₃ and γ̂₄ (e.g., hedge-fund-like γ₃=−3, γ₄=10). At K=1000, Normal FWER=0.026 vs corrected 0.061 — more than doubling.
- Report both `α_K` and `β_K` (familywise misses): the test only has power to detect strategies with `SR ≥ SR*`; a strategy with annualized SR≈1 may be undetectable after 10 trials.