# Chapter 4: Basic Trading Strategies

## Core Idea
All complex option strategies are built from **8 basic positions**: long stock, short stock, long call, short call, covered call, long put, short put, covered put. Every trade has a corresponding **risk graph** showing profit/loss across price.

## Frameworks Introduced
- **Risk Graphs**: Horizontal axis = market price; vertical axis = P/L. Each strategy has a unique curve shape:
  - **Long Stock**: Upward 45° line, unlimited profit, limited risk (to zero)
  - **Short Stock**: Downward 45° line, limited profit, unlimited risk
  - **Long Call**: Upward slope starting at strike + premium; limited risk, unlimited profit
  - **Short Call**: Downward slope; limited profit (premium), unlimited risk — never recommended
  - **Long Put**: Downward slope; limited risk (premium), limited profit (to zero)
  - **Short Put**: Upward slope; limited profit (premium), significant risk
- **Breakeven Formulas**: Long call = strike + premium; Long put = strike − premium

## Key Concepts
- Stock has **1-to-1** price movement (delta = 1), no time decay, no premium
- Options provide **leverage**: controlling $2,000 of stock for $200 (10:1) is common
- **Long call**: Zero margin required; risk = premium only
- **Covered call**: Own stock + sell call; limited risk, limited profit
- **Options calculator**: Use CBOE or similar to compute theoretical prices

## Key Takeaways
1. Always view a risk graph before entering any trade — identify maximum risk, maximum reward, and breakeven
2. Favor strategies with **limited risk and high rewards**; avoid unlimited risk / limited reward profiles
3. Long call breakeven = strike + premium; Long put breakeven = strike − premium
4. The long stock has unlimited upside but full downside risk to zero
