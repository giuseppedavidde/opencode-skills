# Cheatsheet — Machine Learning for Asset Managers

Quick-reference decision tables for the four technical chapters (2, 4, 6, 8).

## A. Covariance matrix treatment (Ch.2)

| Situation | Method | Output | Notes |
|---|---|---|---|
| Empirical covariance is ill-conditioned | Fit MP PDF on eigenvalue KDE | `λ+`, `σ²`, `nFacts` | Quantifies signal-to-noise ratio |
| Need to remove noise, keep signal | **Constant residual eigenvalue** `denoisedCorr` | Trace-preserving denoised corr | Default choice |
| Need to tune noise/signal trade | **Targeted shrinkage** `denoisedCorr2(α)` | Denoised corr | `α→0` total shrinkage of noise |
| Quick one-step fix (NOT recommended alone) | Ledoit–Wolf shrinkage | Shrunk cov | Dilutes signal; adds little beyond denoising |
| Need to find # factors explained | Threshold method | Fixed-variance components | Ignores true noise — avoid |
| Strong market component blocks clustering | **Detoning**: subtract `W_M Λ_M W_M'` | Detoned (singular) corr | Optimize in PC space: `ω* = W_₊ᵀ f*` |
| RMSE reduction (min variance port) | Denoise only | ~60% | vs ~30% shrinkage alone |
| RMSE reduction (max Sharpe port) | Denoise only | ~94% | vs ~71% shrinkage alone |

## B. Clustering (Ch.4)

| Need | Use | Watch out |
|---|---|---|
| Hierarchical structure (sector tree, credit) | Hierarchical / agglomerative | Cannot easily invert to partitional |
| Optimal unknown K from correlation matrix | **ONC** (`clusterKMeansTop`) | Multi-seed restart, silhouette q-stat |
| High-dim X with N/F imbalance | PCA → keep eigenvalues > `λ+` | Then ONC on projection |
| Negative correlations in long-short | Cluster `corr.abs()` | Sign-flip via weights needs containment |
| Biclustering algorithm | Pass **similarity** (reciprocal of distance) | Passing distance clusters the most distant |
| Compare two partitions | Normalized variation of information | True metric, bounded |
| Quality metric | `q = E[{Sᵢ}]/sqrt(V[{Sᵢ}])` | Silhouette t-statistic |
| Re-clustering weak clusters | ONC higher-level recursion | Keep only if avg quality improves |

Observations matrix for correlation clustering: **option (c)** `Xᵢⱼ = sqrt(0.5·(1−ρᵢⱼ))`.

## C. Feature importance (Ch.6)

| Method | Solves p-value caveat | In-sample? | Bounds | Cost |
|---|---|---|---|---|
| p-value (classical) | — | Yes | [0,1] | Cheap |
| **MDI** (mean-decrease impurity) | #1, #2, #3 | Yes | [0,1] ∑=1 | Medium |
| **MDA** (permutation importance) | #1, #2, #3, **#4** | **No (CV)** | Unbounded | High |
| Probability-Weighted Accuracy (PWA) | Finer scoring for MDA in finance | n/a | [0,1] | n/a |
| **Clustered MDI/MDA** | All + **substitution effects** | MDA no | Bounded per cluster | Highest |

| Multi-feature situation | Recommended |
|---|---|
| Independent features | Plain MDI/MDA |
| Multicollinear (typical in finance) | **CFI** with ONC on feature proximity (prefer normalized VI over correlation) |
| Nonlinear redundancy | Use *normalized variation of information*, not correlation, for clustering |
| Low silhouette after clustering | Residualize each feature against out-of-cluster features |
| Scoring function | log-loss or PWA (never accuracy in finance) |

## D. Testing set overfitting (Ch.8)

| Quantity | Formula / Tool |
|---|---|
| Odds ratio | `θ = s_T / s_F` |
| Precision (multi-test) | `(1−β_K)·θ / ((1−β_K)·θ + α_K)` |
| Recall (multi-test) | `1 − β_K` |
| FWER | `α_K = 1 − (1−α)^K` |
| Familywise miss | `β_K = β^K` |
| Expected max SR (False Strategy thm) | `E[max{ŜR_k}] ≈ ((1−γ)·Z⁻¹(1−1/K) + γ·Z⁻¹(1−(K·e)⁻¹))·sqrt(V[{ŜR_k}])` |
| DSR | `Z[(ŜR − E[max{ŜR_k}])·sqrt(T−1) / sqrt(1 − γ̂₃ ŜR + ((γ̂₄−1)/4)·ŜR²)]` |
| Critical value (FWER) | `z_α = Z⁻¹[(1−α_K)^(1/K)]` -- Šidàk |
| Effective number of trials | **ONC** on backtested-returns corr matrix |
| Variance across trials | Min-variance weighted cluster returns, annualized |

**Decision**:
- Reject H0 (strategy is real) only if `DSR < α` **AND** `α_K < threshold` **AND** `β_K` small enough that `SR*` is detectable at chosen power.
- ALWAYS pass measured skewness γ̂₃ and kurtosis γ̂₄; assuming Normal understates α_K by 2-3×.
- FDR rule of thumb: at θ=1/99, α=0.05, β=0.2 ⇒ FDR ≈ 86% — most "discoveries" in finance are false.

## E. Quick rules of thumb

1. Denoise → detone → cluster before any portfolio or feature work.
2. Use normalized variation of information when relationships may be nonlinear.
3. Never report unclustered feature importance in financial (multicollinear) data.
4. Backtesting is NOT a research tool — feature importance is.
5. Every reported Sharpe ratio must be deflated for the effective number of trials.
6. Always track skewness/kurtosis — Normality assumptions understate false positives.
7. Minimum-variance weighting prevents one noisy trial from dominating cluster-return series.