# Chapter 6: Ensemble Methods

## Core Idea
Ensemble methods combine many weak learners to reduce bias, variance, or both. The chapter reframes the canonical bias-variance-noise decomposition for finance and argues that **bagging is generally preferable to boosting** in financial applications, because the low signal-to-noise ratio makes overfitting (boosting's failure mode) a far greater threat than underfitting. It also shows how to use bagging as a **scalability tool**: wrap a non-scalable estimator (SVM) in a bagging classifier with tight early stopping.

## Frameworks Introduced
- **Three sources of error**: Bias (underfit), Variance (overfit/sensitivity to training set), Noise (irreducible σ²_ε).
- **Bias-variance decomposition**: E[(f − f̂)²] = Bias² + Variance + Noise.
- **Bootstrap Aggregation (Bagging)**: N independent bootstrapped estimators, forecasts averaged (majority vote or mean probability); parallelizable.
- **Variance of bagged prediction**: σ²/N·(1+ρ(N−1)) — bagging only helps if ρ→0; sequential bootstrap (Ch.4) lowers ρ.
- **Condorcet-style majority-vote accuracy**: bagging improves accuracy only if individual p > 1/k; poor classifiers stay poor.
- **Random Forest**: bagging + per-split random feature subsample to decorrelate trees; provides feature importance and (inflated) OOB accuracy.
- **Boosting (AdaBoost)**: sequential reweighting of misclassified observations; reduces both bias and variance but increases overfit risk.
- **Bagging for scalability**: wrap SVM with tight `max_iter`/`tol`, parallelize the bags, recover variance via many independent estimators.

## Key Concepts
- Observation redundancy (low uniqueness) drives ρ→1 → bagging cannot reduce variance regardless of N.
- RF overfits when samples are redundant → essentially identical overfit trees; fix with `max_features=1`, `min_weight_fraction_leaf≈5%`, `max_samples=avgU`, or sequential bootstrap.
- Bagging reduces variance; boosting reduces bias: in low-SNR finance, **overfitting is the bigger risk** → prefer bagging.
- Set `StratifiedKFold(n_splits=k, shuffle=False)`, low k, and ignore OOB on redundant data.
- Fit RF on PCA of features — feature-space rotation aligns splits with axes, fewer levels, less overfit.

## Anti-patterns
- Boosting noisy financial series hoping to "fix" underfit — usually amplifies noise.
- Trusting OOB accuracy when samples overlap heavily.
- Allowing `max_samples` = full N in sklearn RF on redundant data.
- Building only one tree-type and assuming it generalizes because training accuracy is high.
- Parallelizing a boosting pipeline expecting speed gains (boosting is inherently sequential).

## Key Takeaways
1. In finance, bagging beats boosting because controlling variance/overfit matters more than chasing bias.
2. Bagging's variance reduction is governed by inter-estimator correlation ρ — drive it down via sequential bootstrap and uniqueness-aware `max_samples`.
3. Bagging is a scaling device: pair a slow base estimator with early stopping, parallelize, average.
4. RF needs identical anti-overlap safeguards as bagging — default RF parameters overfit financial data.
5. Cross-validate with purged, unshuffled k-fold; never rely on OOB alone.