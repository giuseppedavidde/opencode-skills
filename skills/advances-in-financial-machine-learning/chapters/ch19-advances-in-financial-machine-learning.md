# Chapter 19: Microstructural Features

## Core Idea
Market microstructure — "the process and outcomes of exchanging assets under explicit trading rules" — produces primary FIX-message data (order cancellations, queues, partial fills, aggressor side, replacements) that reveals how participants conceal and reveal intentions. Three generations of models (price-only, strategic trade, sequential trade) plus additional data-driven features (order-size distributions, cancellation rates, TWAP fingerprints, options-implied distributions) are the raw material for some of the most predictive ML features in finance.

## Frameworks Introduced
- **First Generation — Price Sequences**:
  - **Tick rule**: classify trade aggressor side from price changes (buy-init=1, sell-init=-1); high accuracy despite simplicity.
  - **Roll model (1984)**: effective bid-ask spread c derived from serial covariance of price changes under random-walk mid-price; useful when quotes are unrepresentative (corporate/municipal/agency bonds).
  - **High-Low volatility (Parkinson 1980, Beckers 1983)**: sigma^2 from intra-bar high/low; more accurate than close-to-close.
  - **Corwin-Schultz (2012)**: bid-ask spread estimator from high/low prices; the high-to-low ratio mixes fundamental volatility and the spread, and the volatility component scales with elapsed time.
- **Second Generation — Strategic Trade Models** (informed vs. uninformed traders):
  - **Kyle's lambda (1985)**: regress price changes on signed volume b_t * V_t; lambda is the inverse-liquidity price-impact coefficient. Informed profit grows with mispricing and noise-trader variance, and falls with the security's variance.
  - **Amihud's lambda (2002)**: daily price response per dollar of trading volume, |r_t| / (p_t V_t); high rank correlation with intraday effective spread.
  - **Hasbrouck's lambda (2009)**: Bayesian (Gibbs sampler) estimation on TAQ data; recommends stochastic (volume-clock) sampling over 5-min bars.
  - Prefer **t-values** of these coefficients as features over the means — they add a second dimension (estimation-error scale).
- **Third Generation — Sequential Trade Models**:
  - **PIN (Easley et al. 1996)**: probability of information-based trading from a mixture of three Poisson distributions on buy/sell volumes with parameters {alpha, delta, mu, epsilon}.
  - **VPIN (volume-synchronized PIN, Easley et al. 2012)**: with buy volume V_B_tau and sell volume V_S_tau over volume bars of constant size V, PIN ≈ |sum V_B - sum V_S| / (sum V) over n bars; high-frequency estimate using a volume clock.
- **Additional microstructural features**: distribution of order sizes (round sizes are *abnormally* frequent for GUI traders — e.g. size 100 is 16.8x more frequent than 99 in E-mini; useful to detect human vs silicon flow); cancellation rates and limit/market order ratios (quote stuffers, quote danglers, liquidity squeezers, pack hunters); TWAP execution fingerprints (volume concentrates in the first seconds of each minute — front-run large institutional TWAPs); options-implied distributions via put-call parity; serial correlation of signed order flow (order splitting vs. herding on sub-hourly timescales).

## Key Concepts
- **What is microstructural information? (19.7)**: information is *relative* to market makers' predictive power. Build a classifier on the feature matrix X (VPIN, lambda, cancellations, ...) with y labeling market-making profit/loss; for new out-of-sample observations predict the label and compute cross-entropy loss L_tau; KDE the distribution of {-L_t}; phi_tau = F[-L_tau] in (0,1) is the **microstructural information** — the complexity faced by market makers. On May 6, 2010, rising cross-entropy loss signalled the flash-crash build-up well before the stop-outs.

## Anti-patterns
- Using close-to-close volatility when high-low estimators are strictly more accurate.
- Sampling Hasbrouck's lambda with 5-minute time bars instead of volume/dollar bars — time bars are not synchronized with market activity.
- Treating mean lambda as the feature rather than its t-value.
- Assuming options quotes are informative and stocks are not — Muravyev et al. show disagreements tend to be resolved in favor of stock quotes; sparse option *trades* carry info, quotes can stay irrational.
- Rejecting VPIN as a volatility predictor purely because a linear regression failed — linear methods routinely miss 21st-century nonlinear patterns.

## Key Takeaways
- Three generations of microstructure models give a library of features: Roll spread, Kyle/Amihud/Hasbrouck lambdas, PIN/VPIN.
- Add data-driven features (round-size frequency, cancellation patterns, TWAP volume fronts, options-implied distributions, signed-flow autocorrelation).
- Define microstructural information as phi_tau = F[-L_tau], the CDF of the market-maker classifier's cross-entropy loss —_Actionable when information asymmetry rises.