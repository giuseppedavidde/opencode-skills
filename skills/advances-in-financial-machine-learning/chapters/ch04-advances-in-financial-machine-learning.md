# Chapter 4: Sample Weights

## Core Idea
Financial observations are **not IID**. Path-dependent labeling (triple-barrier) forces consecutive outcomes to share returns, so labels overlap. Treating overlapping samples as independent causes bootstrap redundancy, inflated out-of-bag (OOB) accuracy, and overfit random forests. The chapter builds weighting and resampling schemes that restore quasi-independence: **number of concurrent labels**, **average uniqueness**, **sequential bootstrap**, **return attribution**, **time decay**, and **class weights**.

## Frameworks Introduced
- **Overlapping outcomes**: when t_i,1 > t_{i+1,0} the labels y_i, y_j share a common return → IID fails.
- **Number of concurrent labels** c_t = Σ 1_{t,i}: how many labels span a given return.
- **Average uniqueness** ū_i = mean_t(1_{t,i} / c_t): harmonic-mean-style non-overlap score in [0,1].
- **Sequential bootstrap**: redraw with probabilities δ updated each draw to prefer features that increase uniqueness of the running sample set φ — converges closer to IID than standard bootstrap.
- **Return attribution**: sample weight = uniqueness × |attributed return| over the event lifespan.
- **Piecewise-linear time decay** (parameter c ∈ (−1,1]): c=1 no decay, 0< c<1 positive-but-decaying, c=0 linear to zero, c<0 erases oldest cT of observations.
- **Class weights** `balanced` / `balanced_subsample` to upweight rare but critical classes (flash crashes).

## Key Concepts
- In a standard bootstrap only ~63.2% of observations are unique; with K non-overlapping outcomes the effective unique count drops further → oversampling.
- Redundancy makes in-bag samples ≈ out-of-bag samples → OOB accuracy grossly inflated; cross-validation (no shuffle, low k) gives a more honest estimate.
- Sequential bootstrap raises expected uniqueness above standard bootstrap (Monte Carlo confirmed: median 0.7 vs 0.6).
- Decay operates on **cumulative uniqueness**, not chronological time, so redundant observations don't decay weights too fast.
- Drop "neutral"/zero labels — they break return attribution; let a low-confidence ±1 prediction imply neutrality instead.
- When samples overlap, set `max_samples=out['tW'].mean()` in sklearn BaggingClassifier so in-bag draws are not more frequent than uniqueness allows.

## Anti-patterns
- Restricting the bet horizon to eliminate overlap ("a terrible solution") — coarsens the model and kills path-dependent labeling.
- Dropping any observation with partial overlap (extreme information loss).
- Trusting RF/Bagging OOB accuracy on redundant financial data.
- Chronological time-decay that zeroes weights before redundancy is accounted for.
- Leaving minority/rare-event labels un-weighted — the ML optimizes majority accuracy and treats crashes as outliers.

## Key Takeaways
1. Overlap is structural in finance; correct it with *uniqueness-aware* sampling and weighting, not by shortening horizons.
2. Sequential bootstrap produces samples with measurably higher uniqueness than standard bootstrap.
3. Final sample weight ≈ uniqueness × |return|, optionally decayed by cumulative uniqueness.
4. OOB accuracy is biased upward on overlapping data — always corroborate with purged k-fold CV.
5. Balanced class weights are essential whenever the important class is rare (liquidity crises, tail events).