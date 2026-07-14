# Chapter 3: Mean-Variance Investing

## Core Idea
Mean-variance investing is all about diversification: by exploiting the interaction of assets with each other, so one asset's gains offset another's losses, diversification raises expected returns while reducing risk. The Markowitz (1952) machinery is the industry workhorse, but unconstrained mean-variance optimization is notoriously unstable — small input errors produce wild portfolios. Practical success comes from *constraining* the inputs: equal-weighted, minimum-variance, and risk-parity portfolios are constrained special cases that empirically dominate unconstrained optimization.

## Frameworks Introduced
- **Mean-variance frontier (Markowitz 1952)** — the set of maximum-return portfolios for each level of variance; built from expected returns, volatilities, and correlations. The frontier expands with low correlations; all individual assets lie inside or on it.
- **Diversification** — N assets with pairwise correlation ρ reduce idiosyncratic variance by a factor of roughly (1 + (N−1)ρ)/N; as N grows and ρ falls, portfolio variance approaches systematic (non-diversifiable) risk.
- **G5 mean-variance frontiers** — adding countries (U.S., U.K., Japan, Germany, France) expands the frontier, but the gain depends on time-varying correlations that rise in crises.
- **Constrained frontiers** — short-sale and weight caps shrink the feasible set but produce robust portfolios; the unconstrained frontier overfits sampling noise.
- **Two-fund separation (with risk-free asset)** — find the tangency (max-Sharpe) risky portfolio, then mix it with the risk-free asset; every investor holds the *same* tangency portfolio and differs only by the risk-free mix.
- **Capital Allocation Line (CAL)** — E(rp) = rf + Sharpe·σp; the tangent portfolio maximizes the slope.
- **Garbage In, Garbage Out (GIGO)** — mean-variance weights are extremely sensitive to input errors: small changes in expected returns swing weights by huge amounts (Michaud "error-maximization").
- **Constrained special cases** — equal-weight (1/N ignores all inputs), minimum-variance (uses only covariance), risk parity (equal risk contribution). These robustly outperform unconstrained mean-variance in practice.
- **Mean-variance horserace** — DeMiguel-Garlappi-Uppal compare naïve 1/N to optimized portfolios; the constrained cases win; unconstrained optimization is hard to beat even out-of-sample by luck.
- **Why unconstrained MV underperforms** — error-maximization, concentration, turnover, and the asymmetry that estimation errors in the highest expected-return assets inflate their weights the most.

## Key Concepts
- **Home bias** — investors overweight domestic assets even when foreign assets expand the frontier; explanations include time-varying correlations, exchange-rate risk, transaction costs, asymmetric information, and behavioral biases.
- **Non-participation** — many households hold no stocks, explained by non-mean-variance utility, participation costs, social factors, and ambiguity aversion.
- **Is diversification a free lunch?** — yes for risk reduction, but costly to maintain: it foregoes upside, requires rebalancing, and can be impaired by rising correlations in bad times.
- **Rebalancing is inherent** — maintaining fixed mean-variance weights requires counter-cyclical rebalancing, which itself is a source of return (see Chapter 4).
- **Norway and Wal-Mart (SRI)** — divesting an unethical name reduces diversification (frontier shrinks) and imposes a cost; SRI is a constraint, not a return enhancer.

## Anti-patterns
- **Unconstrained mean-variance optimization** — naive plug-in weights maximize *estimation* error, not true expected utility; produces extreme, concentrated, unstable portfolios.
- **Using point estimates of expected returns** — the most noise-laden input dominates the optimization; tiny mean errors cause huge weight swings.
- **Ignoring time-varying correlations** — static correlations understate crash risk; diversification fails precisely when needed (2008).
- **Equating "more assets" with "more diversification"** — adding highly correlated or high-beta assets can *worsen* the frontier; junk-in-junk-out applies to asset choice too.
- **Wall-of-home-bias complacency** — defending home bias with behavioral comfort while the measurable cost (forgone Sharpe) is large.
- **Treating SRI screening as free** — every exclusion has a diversification cost the owner should quantify and consciously accept.

## Key Takeaways
1. **Diversify first, optimize second** — the dominant gain is simply holding many low-correlation assets; sophisticated optimization adds little unless inputs are constrained.
2. **Constrain the inputs** — equal-weight, minimum-variance, and risk parity triumph over unconstrained MV because they minimize the impact of estimation error.
3. **Solve the two-fund problem** — find the best risky tangency portfolio, then mix with the risk-free asset; investors differ only in the mix, not the risky portfolio.
4. **Expect and plan for rising correlations in crises** — static MV frontiers overstate diversification; stress-test to high-correlation regimes.
5. **Quantify the cost of constraints** — SRI exclusions, home bias, and liability mandates shrink the frontier; own the cost deliberately.
6. **Rebalance to maintain the frontier** — fixed-weight MV requires counter-cyclical rebalancing, which is itself a return source; do not let weights drift to pro-cyclical extremes.