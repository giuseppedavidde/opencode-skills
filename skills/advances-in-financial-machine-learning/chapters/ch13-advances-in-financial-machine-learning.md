# Chapter 13: Backtesting on Synthetic Data

## Core Idea
Rather than calibrating trading-rule parameters (profit-taking, stop-loss) by historical simulation — which invites backtest overfitting — characterize the stochastic process that *generates* the observed returns from the full historical sample, then **derive the optimal trading rule (OTR) numerically from the process itself**, on synthetic data. Because the OTR is not the outcome of a single historical path, the procedure avoids the central risk of overfitting to the realized past.

## Frameworks Introduced
- **Trading Rule as parameter set**: a rule R = {profit-taking threshold, stop-loss threshold}; brute-force calibration sweeps R over a grid Omega, backtests each, and picks R*. Free variables invite overfitting — trivially by targeting a few outliers.
- **Overfit Trading Rule (Definition 2)**: R* is overfit if it is expected to underperform the median of alternative rules R in Omega out-of-sample. Overfitting leads to **negative OOS performance** when outcomes exhibit serial dependence.
- **Discrete Ornstein-Uhlenbeck (O-U) process on prices**: P_{i,t} = (1-phi) * target + phi * P_{i,t-1} + sigma * eps_{i,t}, eps ~ N(0,1); performance process pi_{i,t} inherits Gaussianity; stationarity requires phi in (-1,1); half-life tau = -log(2)/log(phi).
- **Five-step OTR algorithm**: (1) estimate {sigma, phi} via OLS on the linearized O-U; (2) build a 20x20 mesh of (stop-loss, profit-taking) pairs; (3) simulate ~100,000 paths per node using observed initial conditions, max holding period = 100 (vertical barrier); (4) compute Sharpe ratio per node; (5) output the optimal pair, or the optimal stop-loss for a given profit target, or the optimal profit-taking for a given stop-loss limit.
- **OTR Conjecture**: for a price characterized by a discrete O-U process, there is a *unique* optimal trading rule in terms of profit-taking and stop-loss that maximizes the Sharpe ratio — supported empirically across all experiments.

## Key Concepts
- Zero equilibrium (market-maker, phi small, short half-life): Sharpe is maximized at small profit-taking + large stop-loss — exactly what real market-makers do; the worst rule is short stop-loss + large profit-taking. Symmetric barriers are close to neutral.
- As tau grows toward an effective random walk (phi -> 1), the heat-map flattens, no optimal region remains, and historical backtest calibration degenerates into overfitting a single random path.
- Positive equilibrium (position-taker): optimal profit-taking is higher and bounded; optimal region takes a characteristic rectangular shape (wide stop-loss, narrow profit-taking); highest Sharpe across experiments ~12.
- Negative equilibrium (closing a losing position): the heat-map is a rotated photographic negative of the positive case; optimal rule = the rule that *minimizes* the loss; rectangular shape becomes a region of worst performance.
- Performance is robust to the *type* of equilibrium and to half-life; asymmetry between profit-taking and stop-loss in OTRs is structural, not accidental.

## Anti-patterns
- Calibrating trading-rule parameters on a single historical simulation — selects one random combination that happened to win (a statistical fluke).
- Assuming a random walk process and then "finding" an optimal rule — there is no consistent optimum to find; any choice is overfit.
- Reusing the same calibrated rule across regimes without re-fitting the O-U parameters.
- Treating the OTR conjecture as proved; it is an experimental rule, but the probability it is false is negligible compared with the probability you overfit by ignoring it.

## Key Takeaways
- Derive trading rules from the underlying stochastic process, estimated from the entire sample, not from one historical path.
- The discrete O-U process plus a 20x20 Sharpe-ratio mesh + 100k synthetic paths yields a numerical OTR in seconds.
- Optimal profit-taking and stop-loss are asymmetric; symmetry (diagonal of the mesh) is near-neutral; the worst rule is the rotated complement of the best.
- Even the closed form is unnecessary — numerical experiments suffice because the OTR conjecture is empirically un-falsified.