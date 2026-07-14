# Chapter 12: Backtesting through Cross-Validation

## Core Idea
The ubiquitous **walk-forward (WF)** backtest — train on the past, test on the next slice, slide forward — is as easy to overfit as any other, yields a single path (no distribution of performance), and discards most data as either pure-train or pure-test. The chapter replaces it with **Combinatorial Purged Cross-Validation (CPCV)**, a generalization of purged k-fold that produces many backtest paths from a single dataset while controlling leakage through purging + embargoing.

## Frameworks Introduced
- **Walk-Forward (WF) method**: train [0,t], test [t,t+1], advance. No embargo needed (train precedes test) but: one path, low train/test efficiency, overfit-prone.
- **Pitfalls of WF**: easy to overfit, ignores most data, no distribution of Sharpe ratios.
- **Cross-Validation method**: k-fold train/test across the timeline — more paths, but leakage from overlapping labels (needs Ch.7 purging/embargoing).
- **Combinatorial Purged Cross-Validation (CPCV)**: choose N groups and a test-size k; combinatorially select k groups as testing, the rest as training, purge overlapping labels, embargo if test precedes train. Yields φ[N,k] ≥ 1 backtest paths.
  - k=1 → φ[N,1]=1 path = standard CV; CPCV is CV generalized for k>1.
- **Distribution of Sharpe ratios**: CPCV returns a *distribution* (mean E[y_i], variance tied to average off-diagonal path correlation ρ̄), not a single number — enables inference.
- **Overfitting control**: φ increases with k; the spread of Sharpe ratios reveals how brittle the strategy is.

## Key Concepts
- A single WF path cannot separate skill from luck — backtest overfitting hides in the unobserved variance.
- Path correlation ρ̄ falls as paths decorrelate → CPCV variance falls → estimate converges to the true Sharpe E[y_i].
- CPCV enforces purging (drop labels spanning train/test) and embargoing (gap after test) so no label leaks across the train/test boundary.
- Combinatorial choice of test groups is what generates multiple independent backtest paths from one series.
- More paths ≠ automatically better: too-high k over-hyper-fragments and inflates variance.

## Anti-patterns
- Treating one WF Sharpe as the strategy's expected return.
- Running k-fold CV on financial data without purging/embargo (label leakage inflates results).
- Selecting the CPCV path with the highest Sharpe and reporting only that (selection bias reintroduced).
- Ignoring the correlation among paths when estimating dispersion.
- Using WF because "it has no leakage" — it has overfitting instead.

## Key Takeaways
1. CPCV turns one dataset into a distribution of backtest paths, enabling Sharpe-ratio inference.
2. k=1 reduces to CV; CPCV generalizes CV for k>1.
3. Always purge overlapping labels and embargo after test sets.
4. Report the dispersion of CPCV Sharpes, never the max path.
5. CPCV is the backtest analogue of purged k-fold (Ch.7) — the same anti-leakage machinery, multiplied.