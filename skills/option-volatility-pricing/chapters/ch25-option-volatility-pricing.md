# Chapter 25: Volatility Contracts

## Core Idea
Volatility contracts (variance swaps, VIX futures/options) allow traders to take direct positions on volatility without the complexity and cost of dynamic hedging. By separating volatility exposure from directional risk, these instruments democratize volatility trading. However, their unique settlement mechanics—particularly variance-based settlement—create non-linear payoff profiles that traders must thoroughly understand.

## Frameworks Introduced
- **Two Contract Types**:
  - **Realized Volatility Contracts (Variance Swaps)**: Settle into the annualized standard deviation of logarithmic daily returns over a specified period. Calculation uses population standard deviation (divide by n, not n-1) with zero-mean assumption.
  - **Implied Volatility Contracts (VIX Futures/Options)**: Settle into the implied volatility of options on an underlying index at a specified date.
- **Variance vs. Volatility Settlement**: Contracts are typically quoted in volatility points but settled in variance points (σ²). One variance point = notional amount / (2 × volatility price). This is because variance is additive across time periods (σ²_total = Σ σ²_i × t_i / t_total), making hedging and replication tractable.
- **VIX Calculation Framework**: Modern VIX uses a wide range of OTM SPX options, weighted by strike, to compute a model-free 30-day expected volatility. The original methodology used only two at-the-money strikes; the updated methodology captures the full volatility smile.

## Key Concepts
- **Variance Swap P&L**: Profit = notional_vega × (σ²_realized - σ²_strike). Convex payoff—a 10-point vol increase from 20 to 30 produces a much larger P&L than a 10-point decrease from 20 to 10.
- **Volatility Caps**: Sellers of variance swaps often require caps (e.g., 2.5× strike) to limit exposure to extreme events. A 20-strike swap capped at 40 limits max variance to 1600.
- **VIX Products**: VIX futures and options enable trading of expected future volatility. Unlike variance swaps (backward-looking), VIX contracts are forward-looking on implied volatility.
- **Replication**: A variance swap can be replicated using a portfolio of OTM options weighted by 1/K², providing the theoretical foundation for pricing and hedging.

## Anti-patterns
- Confusing volatility-quoted prices with variance-settled payoffs—the convexity means P&L is not linear in volatility.
- Selling uncapped variance swaps on single stocks—a takeover, bankruptcy, or fraud revelation can cause volatility to spike to extreme levels, producing theoretically unlimited losses.
- Trading VIX products without understanding the term structure (contango/backwardation)—roll yield can dominate the P&L.
- Assuming variance swaps on indexes are "safe"—broad indexes can still experience volatility spikes (2008, 2020) that devastate short-vol positions.

## Key Takeaways
1. Volatility contracts provide direct volatility exposure without dynamic hedging.
2. Variance swaps settle in variance points (σ²), creating convex, non-linear payoff profiles.
3. Variance is additive across time periods, simplifying hedging and multi-period strategies.
4. VIX futures and options are forward-looking on implied volatility; term structure effects are critical.
5. Caps are essential for single-stock variance sellers; even index products carry tail risk.
