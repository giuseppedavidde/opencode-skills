# Chapter 22: Stock Index Futures and Options

## Core Idea
Stock index futures and options are among the most actively traded derivatives. Understanding index construction (price-weighted, capitalization-weighted, equal-weighted), index arbitrage, dividend estimation, and the delta of index futures is essential for correctly pricing and hedging these instruments.

## Frameworks Introduced
- **Index Construction Methods**:
  - **Price-Weighted**: Sum of stock prices / divisor. Higher-priced stocks dominate. Changes per point are uniform (1/divisor)
  - **Capitalization-Weighted**: Sum of market caps / divisor. Larger companies (more shares) dominate. Most modern indexes use this method
  - **Equal-Weighted**: Each stock contributes equally; requires periodic rebalancing
- **Index Divisor**: Normalizes raw index value to a target round number. Adjusted for stock splits, component changes, and (for total-return indexes) dividends
- **Index Forward Pricing**: `F = S × [1 + (r − d) × t]` where d = annualized dividend yield. Approximation adequate for long contracts; for short contracts, discrete dividend timing creates large errors
- **Index Arbitrage (Program Trading)**: Buy/sell mispriced futures vs. basket of component stocks. Settled at expiration via AM settlement (opening prices) or PM settlement (closing prices)
- **Futures Delta**: Stock index futures have delta = `1 + r × t` (ignoring dividends). Hedging requires holding more stock than the notional futures value due to futures-type vs. stock-type settlement mismatch

## Key Concepts
- **Total-Return Index**: Dividends assumed reinvested; divisor adjusted for each dividend payment. German DAX is the best-known example
- **Impact of Individual Stock Changes**: `%ΔIndex = Σ(%ΔStock_i × Weight_i)`. For price-weighted: each point change = 1/divisor points in index regardless of stock price level
- **VWAP Settlement**: Volume-Weighted Average Price over closing period used when last trade is anomalous
- **Dividend Estimation Challenges**: Annualized dividend yield approximation works for long-term contracts but fails for short-term — discrete dividend clusters create periodic over/understatement (see DJIA daily dividend chart)
- **Index Arbitrage Mechanics**: Fair value = index × (1 + r × t) − dividends. Mispricing triggers buy programs (buy stocks, sell futures) or sell programs (sell stocks, buy futures). Carried to expiration with market-on-close orders
- **AM vs. PM Expiration**: AM settlement (opening prices) now standard for most index derivatives — reduces end-of-day order imbalances from arbitrage unwinding
- **Futures Delta Hedge Ratio**: `Stock holding = Futures notional × (1 + r × t)`. Required stock position changes as time passes (t→0) and as interest rates change. At expiration, ratio = 1:1
- **Index Replication**: Price-weighted: equal shares per stock. Cap-weighted: shares proportional to (target_value × weight_i / price_i)
- **Settlement Risk in Index Arbitrage**: Stock side has unrealized P&L; futures side has daily realized variation with interest implications. Exact replication ≠ perfect hedge due to settlement asymmetry

## Anti-patterns
- **Using annualized dividend yield for short-term contracts**: Discrete dividend payments cause large estimation errors — always model actual dividend dates and amounts
- **Ignoring futures delta in index arbitrage**: Replicating the index, not the futures, results in a mismatched hedge; must adjust for 1+r×t delta
- **Assuming settlement parity**: Futures-type (variation) and stock-type (MTM only) settlements don't match; interest on variation creates P&L drift
- **Overlooking divisor adjustments**: Stock splits, index component changes, and special dividends all change the divisor — stale divisors produce incorrect index values
- **Trading halted stocks at last price**: Index value based on stale price; use estimated reopening price and stock weighting to calculate "true" index value
- **Neglecting free-float vs. total shares**: Cap-weighted indexes typically use free-float shares (excluding treasury, insider, restricted holdings), not total outstanding

## Key Takeaways
1. Index construction method (price vs. cap vs. equal weight) determines how individual stock moves affect index value
2. Futures on indexes have delta > 1 due to interest: hedge ratio = 1 + r × t, requiring more stock than notional futures value
3. Dividend yield approximation works for long horizons but fails for short-term contracts — model discrete dividend dates for accuracy
4. Index arbitrage is not riskless: interest rate changes, dividend estimation errors, and execution risk (slippage on basket trades) all affect profitability
5. AM settlement on index derivatives was adopted specifically to reduce market-on-close disruptions from program trading unwinding
