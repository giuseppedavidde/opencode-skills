# Chapter 8: Testing Set Overfitting

## Core Idea
Tests repeated K times on the same dataset guarantee a false discovery; selecting the best of K backtests inflates the expected maximum Sharpe ratio of a *false* strategy to a strictly positive value (the **False Strategy theorem**). In finance the odds ratio `θ = s_T/s_F` is low (few true strategies, many false ones), so even a low p-value yields a high false-discovery rate (~86% at standard α=0.05, β=0.2, θ=1/99). This chapter gives two complementary ML-augmented procedures to evaluate the probability that a discovered strategy is a false positive: the **Deflated Sharpe Ratio (DSR)** and the **Familywise Error Rate (FWER)** via Šidàk's correction — both using ONC to estimate the effective number of independent trials.

## Frameworks Introduced
- **Precision and recall of a strategy test** as odds-ratio functions: `precision = (1−β)·θ / ((1−β)·θ + α)`, `recall = 1−β`. A strategy is more likely false than true when `(1−β)·θ < α`. At `θ=1/99`, α=0.05, β=0.2: only 8 true positives vs ~50 false positives; FDR ≈ 86%.
- **Multiple testing correction**: `α_K = 1−(1−α)^K` (FWER), `β_K = β^K` (familywise false negative). Precision and recall generalize to `precision = (1−β_K)·θ / ((1−β_K)·θ + α_K)`.
- **Sharpe ratio distribution** under IID (Lo 2002) and under stationary/ergodic non-Normal returns (Mertens 2002, Christie 2005, Opdyke 2007): `ŜR − SR → N(0, (1 + ½SR² − γ₃·SR + ((γ₄−1)/4)·SR²)/T)`. Skewness γ₃ and kurtosis γ₄ enter the variance — wrongly assuming Normality grossly underestimates the type I error.
- **False Strategy theorem**: for K trials `ŜR_k ~ N(0, V[{ŜR_k}])`, the expected max Sharpe ratio is
  `E[max{ŜR_k}] ≈ (1−γ)·Z⁻¹(1−1/K) + γ·Z⁻¹(1−(K·e)⁻¹)·sqrt(V[{ŜR_k}])`,
  where γ is Euler-Mascheroni, e Euler's number. For 1000 trials with σ(SR)=1 the expected max SR is ~3.26 *even though the true SR is zero*.
- **Deflated Sharpe Ratio (DSR)**: `DSR = Z[(ŜR − E[max{ŜR_k}])·sqrt(T−1) / sqrt(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²)]` — probability of observing a Sharpe ratio higher than the one observed, under the null that the true SR is zero, adjusted for skewness, kurtosis, sample length, and multiple testing.
- **Effective number of trials** via ONC: cluster the N backtested return series into K groups of highly-correlated strategies; `E[K]` is a conservative upper bound on the number of (effectively) independent trials. ONC reuses the clustering machinery from Ch.4.
- **Variance across trials `V[{ŜR_k}]`**: for each cluster k, form cluster-return series `S_{k,t}` using **minimum-variance** weighting (prevents high-variance trials dominating); annualize via `Frequency_k`; estimate variance of clustered trials.
- **FWER via Šidàk's correction**: `α = 1−(1−α_K)^(1/K)` (Bonferroni's approximation `α ≈ α_K/K`). Test statistic `ẑ[0] = ŜR·sqrt(T−1) / sqrt(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²)`. Reject H0 if `max_k ẑ[0]_k > z_α`, where `z_α = Z⁻¹[(1−α_K)^(1/K)]`.
- **Type II errors under multiple testing**: power of test `(1−β)` increases with SR*, sample length, skewness, decreases with kurtosis. Familywise miss probability `β_K = β^K` shrinks as K grows, so `β_K` decreases even though single-trial β rises with K.

## Key Concepts
- SBuMT (Selection Bias under Multiple Testing): two-stage compounding — each researcher runs millions of trials; firm selects best of already-overfit backtests ("backtest hyper-fitting").
- Numerical example: K=1000, daily obs T=1250 (5yr), annualized SR=1.25, γ₃=−3, γ₄=10, E[K]=10 → α_k ≈ 0.0062 single-trial; corrected FWER α_K ≈ 0.0608; if returns were Normal the FWER would have been ≈ 0.0261 — *Normality assumption grossly understates type I error*.
- The False Strategy theorem produces asymptotically unbiased estimates; standard deviation of approximation error < 0.5% of predicted value.
- CPCV (combinatorial purged cross-validation, AFML ch.12) and Monte Carlo synthetic data are the other two defenses — DSR/FWER is the multiple-testing correction.

## Anti-patterns
- Reading a Sharpe ratio at face value: a high SR can have low precision when θ is low — p-value and precision are different things.
- Assuming Normal IID returns for Sharpe-ratio inference — non-Normality (skewness, kurtosis) inflates the type I error severalfold.
- Reporting only the single-trial `α` after running K backtests; always correct for multiple testing.
- Treating K correlated trials as K independent trials — use ONC to estimate the effective number of clusters.
- Sizing cluster-return series by equal weights when estimating `V[{ŜR_k}]` — use minimum-variance to prevent high-variance trials dominating.
- Selecting by Sharpe rather than precision/recall; ignoring the type II error (power) budget when designing tests.

## Key Takeaways
1. Under multiple testing, a *false* strategy exhibits a strictly positive expected maximum Sharpe ratio that grows with K and `V[{ŜR_k}]` — this is the False Strategy theorem.
2. Two complementary ML-augmented procedures evaluate the probability of a false discovery: the Deflated Sharpe Ratio (compares observed SR to the expected max under H0) and the FWER (Šidàk-corrected critical value).
3. Both require ONC to estimate the effective number of independent trials K and the variance across clustered trials — the ML machinery from earlier chapters is essential.
4. Wrongly assuming Normal returns grossly understates the type I error: track skewness and kurtosis explicitly.
5. Report both type I (α_K) and type II (β_K) familywise errors when designing a test; the minimum detectable SR* at given power requires a minimum sample length T.
6. The book's capstone: theories, not backtests, make predictions — ML tools help estimate how likely your discovery is false, but only a theory can explain why.