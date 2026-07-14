# Chapter 6: Factor Theory

## Core Idea
Assets earn risk premiums not because the assets themselves are risky, but because they are bundles of underlying *factor risks*. Each factor defines a different set of "bad times," and investors who bear losses during those bad times are compensated with factor risk premiums in good times. CAPM is the first (single-factor) theory of this; multifactor models (APT, ICAPM, consumption CAPM) generalize "bad times" beyond low market returns to many states of nature, all bound by no-arbitrage.

## Frameworks Introduced
- **CAPM (Sharpe/Lintner/Mossin)** — single-factor model: market portfolio is the only priced factor; asset risk = beta with market; risk premium = γ̄σ_m².
- **Security Market Line (SML) / Capital Market Line (CML)** — beta-pricing relation E(r_i)−r_f = β_i[E(r_m)−r_f]; CML pins market risk premium in equilibrium.
- **Arbitrage Pricing Theory (APT, Ross 1976)** — first multifactor model; many non-diversifiable factors; pricing rests on no-arbitrage, not equilibrium; factors are systematic risks agents wish to hedge.
- **Intertemporal CAPM (ICAPM, Merton 1971/1973)** — dynamic, multi-period extension; state variables drive hedging demand, so investors hold the market plus hedging portfolios for each state variable.
- **Consumption CAPM (Breeden 1979)** — SDF = marginal utility of consumption; bad times = low consumption/high marginal utility; CAPM is a special linear case.
- **Pricing Kernel / Stochastic Discount Factor (SDF)** — general m = a + Σb_k f_k; requires only no-arbitrage (Harrison-Kreps); nests CAPM, APT, ICAPM as restricted forms of m; prices via P_i = E[m × payoff_i].
- **Grossman-Stiglitz (1980) Near-Efficiency** — markets are only *nearly* efficient; costly information creates pockets of inefficiency where active management earns excess returns.

## Key Concepts
- **Factors ≠ asset classes** — factors are the nutrients; assets are the food. Look through asset labels to the underlying factor content.
- **Bad times are multidimensional** — every factor defines its own bad times (low market returns, high inflation, low growth, high volatility, liquidity droughts).
- **Bad vs good factors** — factor risks are inherently *bad* (unlike nutrients which are good); it is by enduring bad experiences that investors earn premiums.
- **Hedging demand** — investors beyond the average hold the market plus/minus hedging portfolios against state-variable risks (labor income, inflation, liabilities).
- **State variables** — macro/investment variables (inflation, growth, volatility, human capital) that shift investment opportunities and justify dynamic, multi-factor exposure.
- **Mean-variance efficient frontier** — the market is the MVE portfolio only under CAPM's strong assumptions; multi-factor world has many MVE portfolios tailored to each investor's preferences.
- **Different investors need different factors** — optimal factor exposures depend on risk aversion, labor income, liabilities, and horizon (e.g., bankruptcy lawyer tolerates low GDP growth).
- **Rational vs behavioral risk premiums** — volatility premium is rational; momentum is behavioral; value/growth is mixed; persistence depends on whether the source is structural/capital-barrier-protected.
- **Time-varying correlations** — factor exposures shift through time, so asset-class correlations rise in bad times, undermining static mean-variance diversification.

## Anti-patterns
- **Misclassifying asset classes as factors** — treating "hedge funds" or "private equity" as factors rather than decoding their embedded equity/volatility/credit/interest-rate/liquidity risk.
- **Assuming idiosyncratic volatility = risk** — pre-CAPM fallacy; risk is co-movement with priced factors, not standalone variance.
- **Single-factor myopia** — using CAPM beta alone and ignoring macro, volatility, liquidity, and higher-moment (downside/co-skewness) factors that violate CAPM assumptions.
- **Statistical factor fitting without economic meaning** — pure PCA factors (Connor-Korajczyk style) lack economic content; prefer factors tied to identifiable bad times.
- **Static diversification by labels** — trusting asset-class labels for diversification when common factor exposures drawdown together in crises (2008).
- **Ignoring that risk premiums may be rational OR behavioral** — investing without identifying whether the premium is structurally persistent or will be arbitraged away.

## Key Takeaways
1. **Invest through factors, not asset labels** — decompose every asset into its factor exposures (market, value, volatility, inflation, liquidity, credit) just as one reads nutrition labels.
2. **Define bad times per factor** — for each factor, explicitly characterize the bad times it hedges or suffers; an asset is attractive iff it pays off in your bad times.
3. **Right-size exposure to your own bad times** — optimal factor loading depends on your liabilities, labor income, and risk aversion relative to the average investor, not on the average market portfolio.
4. **Expect multiple risk premiums where CAPM assumptions fail** — macro factors, downside/higher-moment risk, illiquidity, taxes, and information costs all carry premiums, strongest in small/illiquid names.
5. **Markets are nearly, not perfectly, efficient** — pursue factor premiums only in structural pockets of inefficiency and confirm persistence (rational persistence > ephemeral behavioral mispricing).
6. **Plan for rising correlations in crises** — diversification is not dead, but static asset-class diversification is; manage time-varying factor exposures instead of constant correlations.