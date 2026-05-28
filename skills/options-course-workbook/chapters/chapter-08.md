# Chapter 8: Straddles, Strangles, and Synthetics

## Core Idea
Non-directional strategies profit from **magnitude of movement** regardless of direction. They form the core of delta neutral trading. Long positions have U/V-shaped risk (limited risk, unlimited reward); short positions have upside-down U-shape (limited reward, unlimited risk).

## Frameworks Introduced
- **Long Straddle**: Buy ATM call + ATM put same strike/expiration. Profits from sharp moves in either direction. Breakeven: strike ± net debit
- **Short Straddle**: Sell ATM call + ATM put. Profits from sideways movement. Limited reward (credit), unlimited risk — **not recommended**
- **Long Strangle**: Buy OTM call + OTM put. Cheaper than straddle but needs larger move to profit. Wider max-loss zone
- **Short Strangle**: Sell OTM call + OTM put. Similar risk profile to short straddle
- **Long Synthetic Straddle**: 100 shares + 2 ATM puts (or short 100 shares + 2 ATM calls). Adjustable; unlike fixed straddles, can be rebalanced

## Key Concepts
- Delta neutral to start: position delta = 0. As underlying moves, one side gains faster than the other loses
- Best in **low IV environments** expecting a volatility increase
- ADX indicator can identify trending vs sideways markets
- Fixed straddles cannot be adjusted; synthetic straddles can be rebalanced to delta neutral
- Range of profitability = between downside breakeven and upside breakeven

## Key Takeaways
1. Long straddles/strangles: best when expecting **big moves from low IV**
2. Synthetic straddles offer **adjustability** — a key advantage over fixed straddles
3. Straddle = ATM call + ATM put (narrower breakeven). Strangle = OTM call + OTM put (wider, cheaper)
4. Always check risk graph before entering — understand max loss zone and breakevens
