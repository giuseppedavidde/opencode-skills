# Chapter 4: Orders, Target and Stop

## Core Idea
Simple, rigid order management removes emotional interference. The recommended approach is market order entry + bracket OCO with fixed 20-pip target and 10-pip stop.

## Frameworks Introduced
- **Market order entry**: Fire "at the market" when the break triggers. Agility is critical — limit orders risk missing the fill.
- **Bracket OCO (one-cancels-other)**: Target and stop attached to entry automatically. When one side hits, the other is cancelled.
- **20/10 bracket standard**: 20-pip target (aligns with average double-pressure pop), 10-pip stop (tight but survivable). These are starting defaults, not absolutes.

## Key Concepts
- **Slippage**: Market orders may fill at worse price in fast conditions. Accept as a minor cost of business (1-2 pipettes normally).
- **3:1 target selection**: For discretionary exits, aim for obvious technical levels within the 20-pip framework — cluster lows/highs, round numbers, pattern boundaries.
- **Stop as market order**: Ensures exit under all conditions. Connection failure or gap risk is mitigated by automatic protection.

## Anti-patterns
- **Using limit orders for entry**: Misses too many breaks. Market order ensures you ride the breakout.
- **Widening the stop beyond 10 pips**: Breaks the discipline. If a trade needs wider protection, the setup is not good enough.
- **Scaling in/out arbitrarily**: Complicates management. The bracket is simple and effective.

## Key Takeaways
1. Fire at market on the break; use bracket OCO for exit discipline.
2. 20-pip target / 10-pip stop is the standard — learn why before customizing.
3. Slippage is a cost of business, not a flaw in the method.
