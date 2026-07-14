# Chapter 8: Feature Importance

## Core Idea
**Backtesting is not a research tool — feature importance is.** Re-running a backtest until it looks good (~20 iterations yields a false discovery at 5% significance) is scientific fraud. Instead, the right research loop is: fit a classifier, evaluate on purged k-fold CV, then ask *which features drove the result*. The chapter gives three feature-importance methods split by whether they suffer **substitution effects** (multi-collinearity), plus an orthogonal-features pre-processing step.

## Frameworks Introduced
- **Marcos' First Law of Backtesting**: "Backtesting is not a research tool. Feature importance is."
- **Mean Decrease Impurity (MDI)** — fast, in-sample, tree-only; sums to 1, bounded [0,1]. Set `max_features=int(1)` to prevent masking; replace zeros with NaN.
- **Mean Decrease Accuracy (MDA)** — slow, predictive (OOS), any classifier; permute one column, measure performance loss; "permutation importance". Allow F1 / negative log-loss, not just accuracy.
- **Single Feature Importance (SFI)** — OOS performance of each feature in isolation; **no substitution effects**; loses joint/hierarchical effects.
- **Orthogonal features (PCA on standardized Z)**: compute P = ZW explaining ≥95% variance before MDI/MDA — alleviates linear substitution.
- **Parallelized vs stacked feature importance**: compare importance across regimes/instruments via rank correlation.
- **Regime/feature experiments**: is a feature important always or only in certain environments? across asset classes? — the real research loop.

## Key Concepts
- Substitution effects: importance of a feature is diluted by correlated twins (MDI halves importance of identical features; MDA can mark both as irrelevant).
- MDI is biased toward high-cardinality predictors (Strobl et al.).
- MDA can return *all features unimportant* (OOS-based) and even *negative* importance — feature actively hurts.
- PCA features mitigate, not eliminate, substitution; diagonalize on standardized Z (centering orients PC1; scaling focuses on correlation not variance).
- SFI cannot capture interaction: feature B may be useless alone but vital alongside A.

## Anti-patterns
- Running data → ML → backtest → repeat until "nice" (test-set overfitting / selection bias).
- Defaulting to sklearn's MDI without `max_features=1` and NaN handling for zero-importance features.
- Applying MDI to non-tree classifiers.
- Drawing conclusions from correlated features via MDA without orthogonalization.
- Using SFI alone (misses joint effects) — use it as a complement to MDI/MDA.
- Forgetting purged+embargoed CV for MDA (same leakage as Ch.7).

## Key Takeaways
1. Feature importance must run *before* backtesting — it is the research instrument.
2. Pair MDI (fast IS) with MDA (OOS) and SFI (no substitution) — no single method suffices.
3. Orthogonalize (PCA) to tame linear substitution before MDI/MDA.
4. Rank-correlate importance across regimes and instruments to find robust signals.
5. Negative MDA importance is a signal to drop the feature — never keep it just because MDI > 0.