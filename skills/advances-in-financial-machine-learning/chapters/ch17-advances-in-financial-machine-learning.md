# Chapter 17: Structural Breaks

## Core Idea
Structural breaks — the transition from one market regime to another (e.g., mean-reverting -> momentum, or the birth/burst of a bubble) — offer some of the best risk/reward setups because most participants are caught off guard and then act irrationally before accepting their losses. The chapter surveys tests that measure the likelihood of a break so that informative features can be built on them: **CUSUM tests** (deviation from white-noise forecasting errors) and **explosiveness tests** (exponential growth/collapse incompatible with a random walk or stationary process).

## Frameworks Introduced
- **Two categories**: (1) CUSUM tests on cumulative forecasting errors; (2) explosiveness tests — right-tail unit-root tests (autoregressive) and sub/super-martingale tests (various functional forms).
- **Brown-Durbin-Evans CUSUM on recursive residuals** (1975): standardized 1-step recursive residuals from RLS regressions fit on expanding subsamples; S_t ~ N[0, t-k-1] under constant beta. Caveat: starting point arbitrary.
- **Chu-Stinchcombe-White CUSUM on levels** (Homm & Breitung 2012): drop features, assume H0: beta_t = 0, work directly on log-price levels; standardized S_{n,t} ~ N[0,1]; one-sided critical value b_{0.05}=4.6 via Monte Carlo. Run on backward-shifting windows and take the supremum to remove the arbitrary reference level.
- **Chow-Type Dickey-Fuller**: random walk (H0: rho=1) switches at break date tau* T to an explosive process (H1: delta>1). Andrews (1993) tries all tau* and takes the supremum. Limited: assumes a single break and that the bubble runs to the sample end.
- **Supremum Augmented Dickey-Fuller (SADF)** (Phillips, Wu & Yu 2011): fit the ADF regression at each endpoint t with backwards-expanding start points t_0; SADF_t = sup over t_0 of the ADF statistic. Standard ADF is the special case tau = t-1. SADF handles multiple regime switches without assuming their number or dates; produces a time series that spikes during bubble behavior. Use **log prices** (not raw prices) so price levels condition returns' mean, not volatility.
- **QADF (Quantile ADF)**: take a high quantile (e.g. q=0.95) of the ADF values instead of the supremum — more robust to sampling.
- **CADF (Conditional ADF)**: a conditional moment of the high-ADF distribution; by construction CADF <= SADF and is less outlier-sensitive.
- **Sub-/Super-Martingale Tests (SMT)**: fit polynomial (SM-Poly1, SM-Poly2), exponential (SM-Exp), or power (SM-Power) trends to backwards-expanding windows and take sup |t_beta|. Penalize sample length via a coefficient phi in [0,1] so that the signal filters opportunities for a chosen holding period (phi->0 = long-run bubbles; phi->1 = short-run, noisier).

## Key Concepts
- log prices make returns approximately time-invariant in volatility across regimes; raw prices make ADF structurally heteroscedastic when bubbles produce k != 1.
- SADF runs in O(T^2): for a 356,631-observation E-mini dollar-bar series, one ADF estimate ~11.4 MFLOPs, one SADF update ~2 TFLOPs, a full SADF series ~242 PFLOPs — an HPC cluster is needed.
- Three system states: Steady (beta<0, mean-reverting, with half-life), Unit-root (beta=0, martingale), Explosive (beta>0).
- ADF conditions: Δlog[y_t] = alpha + beta log[y_{t-1}] + eps_t.

## Anti-patterns
- Applying ADF/SADF on **raw prices** when the sample spans decades or bubbles.
- Using a single-bubble Chow-type test on a series with multiple bubble-burst-bubble cycles — periodically collapsing bubbles look stationary to it.
- Running SADF sequentially without parallelization (Ch.20) on long series — tractable only with HPC.
- Picking the SADF supremum unconditionally — outliers bias it upward; prefer QADF/CADF for robustness.

## Key Takeaways
- Use SADF (and its robust variants QADF, CADF) to detect explosiveness across unknown break dates and bubble-counts.
- Use sub/super-martingale tests when you do not want to assume an AR(1) specification; tune phi to the holding horizon.
- Structural-break features are most profitable exactly when most participants are forced into stop-loss behavior.