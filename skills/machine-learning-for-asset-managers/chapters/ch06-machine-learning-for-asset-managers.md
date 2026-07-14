# Chapter 6: Feature Importance Analysis

## Core Idea
Feature importance is the ML research tool that replaces backtesting as a means of theory discovery. The classical recipe — guess a functional form, fit it on a guessed subset of variables, read p-values for significance — is counterintuitive and likely to miss important variables revealed by unexplored specifications. ML decouples the **variable search** from the **specification search**: first isolate the variables that matter irrespective of any functional form, then fit a specification to those variables. This chapter builds MDI, MDA, probability-weighted accuracy, and **clustered feature importance (CFI)** — the capstone that integrates denoising (Ch.2), distance metrics (Ch.3), clustering (Ch.4), and labeling (Ch.5).

## Frameworks Introduced
- **p-value caveats (four)**: (1) built on strong distributional assumptions that may be wrong; (2) meaningless under multicollinearity — substitution effects between correlated regressors; (3) estimates the wrong probability — `P(result|H₀)` rather than `P(H₀|result)`; (4) in-sample — variables significant in-sample may have no out-of-sample forecasting value (p-hacking). ASA has discouraged their continued use as a significance measure.
- **Mean-Decrease Impurity (MDI)** (Breiman 2001): for each tree node, the information gain `Δg[t,f] = i[t] − (N_t^(0)/N_t)·i[t^(0)] − (N_t^(1)/N_t)·i[t^(1)]`; importance of feature `f` = weighted Δg over all nodes where `f` was selected. For a random forest, one MDI per tree => mean & std via CLT. Bounded in [0,1] and sums to 1. Solves caveats #1, #2, #3 but is still in-sample.
- **Mean-Decrease Accuracy (MDA)** (a.k.a. permutation importance): fit a model, compute cross-validated performance; then for each feature, shuffle its column and recompute performance; MDA = pre-shuffle minus post-shuffle performance. Solves caveat #4 (out-of-sample). Caveat: shuffling one of two identical important features can be compensated by the other => underestimates importance.
- **Probability-Weighted Accuracy (PWA)**: `PWA = Σ yₙ·(pₙ − K⁻¹) / Σ (pₙ − K⁻¹)`. Punishes high-confidence wrong predictions more than accuracy but less severely than log-loss; bounded in [0,1]. Fills the gap between accuracy (ignores probabilities) and log-loss (hard to interpret).
- **Substitution effects and orthogonalization**: PCA on features gives orthogonal principal components; run MDI/MDA on components. Caveats: nonlinear redundant features still cause substitution; principal components lack intuitive explanation; components don't necessarily maximize OOS performance.
- **Clustered Feature Importance (CFI)** — the recommended solution:
  - **Step 1**: project features into a metric space (correlation-based or, preferably, normalized variation of information from Ch.3 to catch nonlinear redundancy); run ONC (Ch.4) to find K feature-clusters; optionally residualize each feature against out-of-cluster features to remove cross-cluster information leakage.
  - **Step 2**: **Clustered MDI** = sum of MDI of features in a cluster (one value per cluster per tree => mean/std via CLT). **Clustered MDA** = shuffle *all* features in a cluster simultaneously. Bounded substitution effects since clusters are mutually dissimilar, no change of basis, results intuitive.

## Key Concepts
- Test dataset (Code Snippet 6.1): 40 features — 5 informative ("I_"), 30 redundant ("R_"), 5 noise ("N_"). p-values on the same dataset mislabel the ground truth (only 4/35 non-noise features significant; noise features ranked 9, 11, 14, 18, 26).
- Substitution effects: in MDI, two identical features halve each other's importance. In MDA, two identical features may both look unimportant.
- Apply feature importance across *all* labeling methods (Ch.5) — the importance of a feature depends on what is being predicted.

## Anti-patterns
- Treating a backtest as a research tool — feature importance is the research tool.
- Reporting p-values as a measure of "the probability the variable is relevant" — they estimate `P(result|H₀)`, not `P(H₀|result)`.
- Using MDA with accuracy as the scoring function in finance — accuracy ignores prediction probabilities; use log-loss or PWA instead.
- Reporting unclustered MDI/MDA under high multicollinearity — substitution effects bias the attribution.
- Orthogonalizing via PCA only — non-intuitive components, nonlinear redundancy survives.
- Forgetting to denoise/detone the correlation matrix before clustering features.

## Key Takeaways
1. ML feature importance methods solve 3 of 4 p-value caveats (MDI) and all 4 (MDA, because it is cross-validated).
2. Clustered MDI/MDA is the robust choice in financial (multicollinear) datasets: clusters are mutually dissimilar, so substitution effects are contained and results remain interpretable without a change of basis.
3. Feature importance is the proper tool for theory discovery — it tells you which variables belong in a theory, irrespective of the specification; the researcher then proposes the mechanism that binds them.
4. PWA is a finance-friendly scoring function between accuracy (too lenient) and log-loss (harsh, hard to interpret).
5. The capstone of the book: CFI requires everything learned earlier — denoising/detoning (Ch.2), information-theoretic distance (Ch.3), ONC (Ch.4), and labeling (Ch.5).