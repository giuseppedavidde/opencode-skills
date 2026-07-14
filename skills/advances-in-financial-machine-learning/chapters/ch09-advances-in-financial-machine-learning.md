# Chapter 9: Hyper-Parameter Tuning with Cross-Validation

## Core Idea
Hyper-parameter tuning is mandatory; done naively it overfits and live performance disappoints. Because finance CV is leaky (Ch.7), every tuning step must use **purged k-fold CV**. Beyond the CV machinery, the *scoring function* matters: `accuracy` is the wrong objective for strategies that scale bet size by confidence — **neg_log_loss (cross-entropy)** correctly penalizes high-confidence misses.

## Frameworks Introduced
- **Grid Search CV with purging (Snippet 9.1, `clfHyperFit`)**: exhaustive search over `param_grid` using the PurgedKFold generator, with optional bagging of the tuned estimator and `sample_weight` passed through `fit_params`.
- **MyPipeline (Snippet 9.2)**: subclass of sklearn's Pipeline whose `fit` accepts `sample_weight` — works around the sklearn bug where Pipeline.fit does not forward sample weights.
- **Randomized Search CV (Snippet 9.3)**: when the parameter space is large, sample each parameter from a distribution (Bergstra & Bengio 2012) — controls the computational budget and is not penalized by irrelevant parameters.
- **Log-Uniform Distribution (Snippet 9.4)**: for non-negative parameters like SVC's `C` and RBF `gamma`, sampling from U[0,100] is inefficient; instead log[x] ~ U[log a, log b]. Defined and implemented in scipy.stats as `logUniform_gen`.
- **Scoring for hyper-parameter tuning**: use `scoring='f1'` for meta-labeling (binary take/pass, where zero-recall classifiers fool `accuracy`); use `scoring='neg_log_loss'` for non-meta-labeling strategy tuning.

## Key Concepts
- Log loss: L[Y,P] = -sum_{n,k} y_{n,k} log p_{n,k}. A high-confidence miss (p=0.9) costs far more than a low-confidence hit (p=0.5); `accuracy` treats them equally.
- For equally-sized bets a miss with p=0.9 means a large position that loses a lot; log loss is the right ML metric because it mirrors a PnL calculation: correct label = side, probability = size, sample weight = return/outcome.
- Negation is cosmetic: "neg_log_loss" flips the sign so that higher = better, matching accuracy intuition.
- Known sklearn bug #9144 affects `neg_log_loss`; use `cvScore` from Ch.7.

## Anti-patterns
- Tuning with `scoring='accuracy'`: a classifier that always predicts negative gets high accuracy on imbalanced samples yet has zero recall and undefined precision.
- Sampling `C` from a uniform U[0,100]: ~99% of draws land above 1, wasting the search on a regime where the SVC barely responds.
- Passing `GridSearchCV` sklearn's default KFold — leaks overlapping financial labels into every fold, overfitting hyper-parameters to leaked information.
- Using sklearn `Pipeline.fit` directly when sample weights are needed.
- Treating grid and randomized search as interchangeable once parameters matter logarithmically.

## Key Takeaways
- Always wrap tuning in PurgedKFold (Ch.7); never default to sklearn's KFold for financial data.
- Prefer randomized search with a log-uniform prior for scale-type parameters.
- For meta-labeling choose F1; for confidence-sized strategies choose neg_log_loss.
- High-confidence misses must be penalized more than low-confidence hits — accuracy hides that, log loss exposes it.