# Chapter 9: Advanced Delta Neutral Strategies

## Core Idea
Ratio spreads and backspreads use **uneven numbers** of bought and sold options. Ratio spreads are bearish/bullish with wide profit zones but unlimited risk. Ratio backspreads are the opposite — limited risk with unlimited reward potential.

## Frameworks Introduced
- **Ratio Call Spread**: Buy 1 lower-strike call, sell 2+ higher-strike calls. Net credit. Bearish. Wide profit zone but **unlimited upside risk**
- **Ratio Put Spread**: Buy 1 higher-strike put, sell 2+ lower-strike puts. Net credit. Bullish. Wide profit zone but downside risk to zero
- **Call Ratio Backspread**: Sell 1 lower-strike call, buy 2+ higher-strike calls. U-shaped risk. **Limited risk, unlimited upside reward**. Best in low IV anticipating upside breakout
- **Put Ratio Backspread**: Sell 1 higher-strike put, buy 2+ lower-strike puts. U-shaped risk. Limited risk, limited downside reward. Best in low IV anticipating downside breakout
- **Volatility Skew**: Options with different strikes/expirations have different IV levels
  - **Forward skew**: Higher strikes have higher IV
  - **Reverse skew**: Lower strikes have higher IV

## Key Concepts
- Common ratios: 1:2 or 2:3 (long:short)
- Ratio spreads aim to collect premium decay; backspreads aim for explosive moves
- Never place ratio backspreads in low-volatility markets without adjustments
- Use volatility skew to select strikes — sell overpriced options, buy underpriced ones

## Key Takeaways
1. Ratio spreads = sell more than you buy (credit, but unlimited risk). Backspreads = buy more than you sell (debit/credit, but limited risk)
2. Call ratio backspreads are **ideal for anticipating upward breakouts** with low IV
3. Ratio put spreads work in bullish markets; ratio call spreads work in bearish markets
4. Understanding volatility skew helps you pick the right strikes
