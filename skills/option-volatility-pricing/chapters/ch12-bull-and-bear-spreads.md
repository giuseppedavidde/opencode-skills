# Chapter 12: Bull and Bear Spreads

## Core Idea
Traders can express directional opinions through options while maintaining awareness of volatility implications. The choice between naked positions, ratio spreads, and vertical spreads depends on whether volatility or direction is the primary concern. Vertical spreads (call or put spreads at different strikes, same expiration) are the purest directional instrument: they remain bullish or bearish under all market conditions.

## Frameworks Introduced
- **Naked Directional Positions**: Buy calls/sell puts = bullish; buy puts/sell calls = bearish. Simple but with minimal margin for error
- **Bull/Bear Ratio Spreads**: Delta-neutral or delta-biased ratio spreads (e.g., 2×3 calls); can invert from bullish to bearish if market moves too far too fast (negative gamma effect)
- **Bull/Bear Butterflies and Calendar Spreads**: Choose inside exercise price above/below current price; positions invert delta when market crosses the strike (negative gamma)
- **Vertical Spreads (Credit/Debit Spreads)**: Buy one option, sell another of same type and expiration, different strike. Bull: buy lower strike, sell higher. Bear: buy higher strike, sell lower. Delta never inverts
- **At-the-Money Selection Rule**: The at-the-money option is most sensitive to volatility changes in total points. When IV is low, buy the ATM option. When IV is high, sell the ATM option

## Key Concepts
- **Delta Inversion in Ratio Spreads**: A 1×2 call ratio (buy 100 call Δ=56, sell two 110 calls Δ=28) is initially Δ=0 but becomes Δ=−100 if the market rallies dramatically — volatility characteristics eventually dominate directional intent
- **Delta Inversion from Time/Volatility Decay**: In a 2×1 ratio (buy two 110 calls, sell one 100 call), time passage can invert delta from +28 to −25 as deltas move away from 50
- **Vertical Spread Value Range**: Always between 0 and the amount between exercise prices at expiration. A 100/105 call spread is worth 0 to 5.00; a 95/105 put spread is worth 0 to 10.00
- **Call vs. Put Spread Equivalence**: A bull call spread and bull put spread with same strikes and expiration have nearly identical delta and P&L characteristics
- **Debit vs. Credit**: Bull call spread = debit (lower strike call costs more); bull put spread = credit (lower strike put costs less but sold for higher strike)
- **Exercise Price Selection**: Wider strikes = larger delta, larger max profit/loss. The specific spread choice depends on IV regime:
  - Low IV (20%): Buy ATM (100 strike) → 100/105 call spread has positive edge
  - High IV (30%): Sell ATM (100 strike) → 95/100 call spread has positive edge
- **In-the-Money vs. Out-of-the-Money**: Spreads with in-the-money options profit from no movement (+theta, −gamma); spreads with out-of-the-money options profit from movement (−theta, +gamma)
- **Forward Consideration**: For stock options with high interest rates, the at-the-forward option (not at-the-money) should be the focus

## Anti-patterns
- **Choosing spread by price alone**: A cheaper spread (100/105 at 1.92) may seem better than expensive (95/100 at 2.91) but the edge depends on IV regime
- **Ignoring gamma inversion**: Ratio spreads, butterflies, and calendar spreads that start bullish/bearish can reverse delta — never assume directional characteristics persist
- **Using vertical spreads without vol awareness**: Even though vertical spreads never invert delta, they still have vega and theta exposure that affects profitability
- **Focusing on spot not forward**: In high-interest-rate environments, at-the-money ≠ at-the-forward; option selection should center on the forward
- **Over-leveraging far-OTM spreads**: Deep OTM spreads are cheap and can be executed many times, but the probability of max profit is correspondingly low

## Key Takeaways
1. Vertical spreads are the only directional option strategy where delta never inverts — they are purely directional instruments
2. The golden rule: buy the ATM option when IV is low, sell the ATM option when IV is high, then choose the companion strike to complete the spread
3. A spread that includes an in-the-money option profits even if the market sits still (+theta); a spread with out-of-the-money options requires movement (−theta)
4. The 95/100 spread is always more valuable than the 100/105 spread because it profits in more scenarios — it only requires the market "not to fall"
5. Even in directional trading, volatility awareness separates winning traders from those who would be better off trading the underlying directly
