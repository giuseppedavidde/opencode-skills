# Chapter 24: Volatility Skews

## Core Idea
In real markets, implied volatility varies across exercise prices — a phenomenon called the volatility skew. This violates the Black-Scholes assumption of constant volatility but reflects real-world forces: hedging activity (protective puts, covered calls), market sentiment (fear of crashes), and distributional realities (fat tails, negative skewness). Understanding, modeling, and trading the skew is essential for professional option trading.

## Frameworks Introduced
- **Three Skew Types**:
  - **Investment Skew** (stocks/equity indexes): Higher IV at lower strikes (puts), lower IV at higher strikes. Caused by protective put buying + covered call selling. "Skew is to the downside"
  - **Demand/Commodity Skew**: Higher IV at higher strikes, lower IV at lower strikes. Caused by end-user hedging against rising prices (buying OTM calls, selling OTM puts)
  - **Balanced Skew** (currencies): Symmetrical IV around ATM. Both longs and shorts hedge equally
- **Skew Modeling Approaches**:
  - **Sticky-Strike**: IV at each strike remains fixed regardless of underlying movement — inconsistent with observed dynamics
  - **Floating Skew**: Entire skew shifts horizontally (with underlying price) or vertically (with overall IV level)
  - **Sticky-Delta**: Express strikes in standard deviation (moneyness) terms, then model skew. Accounts for relative magnitude of moves and time effects
- **Skew as Model Input**: `y = a + bx + cx² + dx³ + …` where a = base (ATM) volatility, b = skewness (tilt), c = kurtosis (curvature)
- **Volatility Surface**: Combined term structure (across expirations) + skew (across strikes) → 3D surface for comprehensive volatility visualization

## Key Concepts
- **Why Skews Exist**: Two primary causes — (1) Supply/demand from hedging (protective puts bid up lower strikes, covered calls suppress higher strikes), (2) Realized distribution non-normality (markets become more volatile when falling, fat tails in both directions)
- **Moneyness Calibration**: Express strikes as `ln(X/S) / (σ√t)` — standard deviations from ATM. Enables comparison across expirations and price levels
- **Volatility Calibration**: Express IVs as percent of ATM IV (e.g., 25% IV when ATM=20% → 125%) rather than absolute differences — preserves skew shape as vol levels change
- **Skewness (Tilt)**: Negative skewness = longer left tail → puts bid up. Positive skewness = longer right tail → calls bid up. Measured by 25Δ put IV minus 25Δ call IV
- **Kurtosis (Curvature)**: Positive kurtosis = fat tails → both OTM puts and calls bid up relative to ATM. Options at ±5Δ most sensitive to kurtosis changes
- **Skewed Risk Measures**: Including skew changes delta, gamma, vega. An OTM put with Δ=−20 in flat vol may have skewed Δ=−15 because rising underlying → put moves further OTM → IV rises → vega gain offsets some delta loss
- **Volatility-Versus-Price Relationship**: Stock indexes: inverse (price↓ → vol↑). Commodities: direct (price↑ → vol↑). This makes "delta-neutral" straddles not truly neutral — they benefit from movement in the high-volatility direction
- **Risk Reversals**: Buy OTM puts, sell OTM calls (or reverse), delta-hedge with underlying. Expresses a view on skewness. Commonly uses 25Δ options
- **Kurtosis Trading**: Buy strangles (positive kurtosis expected to increase) or sell strangles (expected decrease). Hedge vega with ATM straddles (kurtosis-neutral). 2×1 strangle:straddle ratio = "dragonfly"
- **Cross-Expiration Skew/Kurtosis Trades**: Buy skew in one month, sell in another. Combine with vol view: if June IV is low vs. March AND June puts are cheap on skew → buy June put calendars
- **Implied Distributions**: Butterfly prices across all strikes reveal the market-implied probability distribution. Non-flat IV skew → non-lognormal implied distribution

## Anti-patterns
- **Using Black-Scholes with flat vol**: Ignoring the skew generates incorrect theoretical values and risk measures — every professional trader incorporates some form of skew
- **Sticky-strike assumption**: IV at a given strike does not remain constant as underlying moves; floating or sticky-delta models are more realistic
- **Ignoring the skew direction for "delta-neutral" trades**: A straddle in stock indexes is actually short delta (benefits from down moves, which increase vol); in commodities, it's long delta
- **Trading kurtosis without vega hedging**: Buying strangles for kurtosis exposure also creates large positive vega — always offset with ATM straddles unless you also have a vol view
- **Using absolute IV differences across time**: IV differences change as overall vol levels change; use percentage-of-ATM calibration for consistent analysis
- **Assuming all skews are stable**: Skew shape changes with market conditions — steepens in crises, flattens in calm periods. Monitor skewness and kurtosis as separate risk factors

## Key Takeaways
1. Volatility skews exist because real markets violate Black-Scholes assumptions — hedging flows, crash fears, and non-lognormal distributions all contribute
2. Three skew types: investment (puts bid, stocks), demand (calls bid, commodities), balanced (symmetrical, currencies)
3. A skew model adds three parameters: base vol (a), skewness/tilt (b), and kurtosis/curvature (c) — each represents a distinct risk factor
4. The volatility surface (skew × term structure) is the professional trader's map — knowing how it shifts with price and time is essential for risk management
5. Skew trading strategies (risk reversals, kurtosis strangles, cross-expiration skew spreads) allow traders to express views on distribution shape independent of direction or overall vol level
