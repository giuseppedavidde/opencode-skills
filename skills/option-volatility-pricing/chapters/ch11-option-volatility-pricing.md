# Chapter 11: Volatility Spreads

## Core Idea
Volatility spreads are multi-leg option positions designed to profit from changes in implied volatility rather than directional price movement. By combining options to create delta-neutral positions with specific gamma, theta, and vega profiles, traders isolate volatility as the primary profit driver.

## Frameworks Introduced
- **Straddle**: A call and put at the same strike and expiration. Long straddle: +gamma, -theta, +vega (wants movement and volatility increase). Short straddle: -gamma, +theta, -vega (wants stillness and volatility decrease).
- **Strangle**: A call and put at different strikes, typically OTM. Similar risk characteristics to straddles but with a wider profit zone (for shorts) or requiring more movement (for longs). A strangle using ITM options is called a "guts."
- **Butterfly**: A three-legged spread (1×2×1 ratio) with equally spaced strikes. Long butterfly: -gamma, +theta, -vega (wants the underlying to stay near the middle strike). Maximum value equals the distance between strikes; bounded risk/reward in both directions.
- **Ratio Spread**: Unequal numbers of long and short options (e.g., buy 1, sell 2). Enables tailoring of the risk profile beyond simple symmetrical structures.
- **Calendar/Time Butterfly**: Spreads across different expiration months rather than different strikes, capturing time decay differentials.

## Key Concepts
- **Delta-Neutral Construction**: All volatility spreads aim for approximate delta neutrality at initiation, often using ATM options or delta-weighted ratios.
- **Risk-Reward Profiles**: Long straddles/strangles have limited risk (premium paid) and unlimited profit; short straddles/strangles have limited profit and unlimited risk. Butterflies are bounded in both directions.
- **Size vs. Risk**: Larger position sizes do not always mean larger risk—a 300-lot butterfly may be safer than a 100-lot short straddle because the butterfly's risk is bounded.
- **Strategy Selection**: Depends on volatility outlook: long volatility (+gamma/+vega) for expected large moves, short volatility (-gamma/-vega) for expected range-bound markets.

## Anti-patterns
- Choosing long straddles/strangles solely for "limited risk, unlimited profit" appeal without assessing the probability of sufficient movement to overcome theta decay.
- Executing straddles without checking that they are actually delta-neutral—non-ATM strikes require ratio adjustments.
- Ignoring that butterflies, while risk-limited, require much larger position sizes to generate meaningful returns, increasing transaction costs.

## Key Takeaways
1. Volatility spreads isolate volatility as the primary profit driver by creating delta-neutral positions.
2. Long volatility positions (+gamma, -theta, +vega) profit from large moves; short volatility positions (-gamma, +theta, -vega) profit from stability.
3. Straddles and strangles are unbounded in one direction; butterflies are bounded in both.
4. Risk depends on strategy characteristics, not just position size.
5. All volatility strategies require active monitoring—changing market conditions alter delta, gamma, and vega.
