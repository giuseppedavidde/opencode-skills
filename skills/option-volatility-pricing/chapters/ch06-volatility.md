# Chapter 6: Volatility

## Core Idea
Volatility is a measure of the speed of the market — the annualized standard deviation of percent price changes. It is the most important yet least understood input in option pricing, directly determining probability distributions and thus option values. Markets that move quickly are high-volatility; markets that move slowly are low-volatility.

## Frameworks Introduced
- **Random Walk Model**: Price movements follow a random path analogous to balls falling through a pinball maze — each step is independent, leading to a distribution of outcomes
- **Normal Distribution Assumption**: At expiration, underlying prices are assumed normally distributed; fully described by mean (forward price) and standard deviation (volatility)
- **Lognormal Distribution**: The Black-Scholes model assumes continuously compounded returns, producing a lognormal price distribution skewed to the upside and bounded by zero on the downside
- **Volatility Scaling**: Volatility is proportional to the square root of time: `σ_period = σ_annual × √t`; divide by √256 (≈16) for daily, √52 (≈7.2) for weekly
- **Realized vs. Implied Volatility**: Realized = historical standard deviation of price changes; Implied = volatility backed out from option market prices using a pricing model

## Key Concepts
- **Standard Deviation Probabilities**: ±1σ ≈ 68.3% (2/3), ±2σ ≈ 95.4% (19/20), ±3σ ≈ 99.7% (369/370)
- **Forward Price as Mean**: The distribution is centered on the forward price, not the spot price — this is the no-arbitrage expected value
- **Volatility = Standard Deviation**: A 20% volatility on a $100 forward means ±$20 is one standard deviation (68% probability over one year)
- **Daily Volatility**: 20% annual / 16 = 1.25% daily = ±$1.25 on $100; expected to be exceeded one day in three
- **Weekly Volatility**: 20% annual / 7.2 ≈ 2.78% weekly; expected to be exceeded one week in three
- **Interest-Rate Products**: Rate volatility vs. price volatility; Eurodollar contracts indexed from 100 (93.00 = 7% rate); calls become puts in rate terms
- **Lognormal Properties**: 110 call always more valuable than 90 put at same forward price (upside unlimited, downside bounded at zero); right tail longer, mean to the right of mode
- **Continuous Compounding**: `$1,000 × e^0.12 = $1,127.50` gain vs. `$1,000 × e^−0.12 = $886.92` loss — asymmetric returns
- **Future vs. Historical Volatility**: Future realized is the unknown ideal input; historical provides a starting estimate; mean reversion is a key characteristic
- **Volatility Forecasting**: Combine serial correlation (tomorrow like today) with mean reversion (extreme values revert to long-term average)
- **Interval Choice**: Daily, weekly, or monthly price changes yield similar volatility profiles — choice of interval rarely changes conclusions significantly

## Anti-patterns
- **Confusing unlikely with impossible**: A 3σ move (1 in 370) can and does happen; don't dismiss observed extremes
- **Assuming constant volatility**: Markets cycle between high and low volatility regimes; stale volatility estimates destroy edge
- **Over-relying on small samples**: 5 days of low price changes don't invalidate a 37% volatility estimate — but 50 days might
- **Ignoring the forward price in probability calculations**: Centers distributions on spot instead of forward, especially important for stocks with significant carry
- **Using price volatility for rate products**: For interest-rate futures, use rate volatility, not contract price volatility
- **Treating volatility as proportional to time**: Volatility scales with square root of time, not linearly (unlike interest rates)

## Key Takeaways
1. Volatility is the annualized standard deviation of percent price changes — the key input that determines an option's theoretical value
2. A lognormal distribution (not normal) is assumed by Black-Scholes, producing asymmetric upside/downside values and preventing negative prices
3. Historical volatility serves as a starting point for forecasting; implied volatility represents the market's consensus forecast embedded in option prices
4. Volatility scales with √t: daily σ = annual σ ÷ 16; weekly σ = annual σ ÷ 7.2
5. Realized volatility determines ultimate P&L at expiration; implied volatility determines interim mark-to-market — both must be understood and monitored
