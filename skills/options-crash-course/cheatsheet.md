# Options Trading Cheatsheet

## Strategy Decision Table

| Market Outlook | Strategy | Risk Level | Max Loss | Max Profit |
|---|---|---|---|---|
| Bullish | Buy Call | Medium | Premium paid | Unlimited |
| Bullish | Bull Call Spread | Low | Net debit | Spread width - debit |
| Bullish (cautious) | Married Put | Medium | Stock loss + put premium | Unlimited |
| Bearish | Buy Put | Medium | Premium paid | Strike - premium |
| Bearish | Bear Put Spread | Low | Net debit | Spread width - debit |
| Neutral / Mildly Bearish | Covered Call | Low-Med | Stock value - premium | Strike + premium - stock cost |
| Neutral (range-bound) | Short Straddle | High | Unlimited | Premium collected |
| Neutral (low vol) | Iron Condor | Low | Spread width - credit | Credit collected |
| Neutral (tight range) | Butterfly | Low | Max debit | Middle strike width |
| High volatility (direction?) | Long Straddle | Medium | Both premiums | Unlimited |
| High volatility (direction?) | Long Strangle | Low-Med | Both premiums | Unlimited |
| Protect gains | Protective Collar | Low | Put strike floor | Capped at call strike |

## Greeks for Beginners

| Greek | Symbol | What It Measures | Trader Notes |
|---|---|---|---|
| Delta | Δ | Price change per $1 move in underlying | ATM calls ≈ 0.50 delta. Deep ITM ≈ 1.0. Deep OTM ≈ 0. |
| Gamma | Γ | Rate of delta change | High gamma near expiry. Positions become unpredictable. |
| Theta | Θ | Time decay per day | Works AGAINST long options. Works FOR short options. |
| Vega | ν | Price change per 1% vol change | High vega near expiry. Important before earnings/news. |
| Rho | ρ | Price change per 1% interest rate change | Least important for short-term trades. Matters for LEAPs. |

**Quick Rules**
- Long options: Positive delta, negative theta (lose value daily)
- Short options: Negative delta, positive theta (gain from time decay)
- ATM options: Highest gamma and vega
- Theta accelerates in the final 30 days before expiry

## Exit Rules

**When to Close a Trade**

**Rule 1: Predefine Exit Before Entry**
Set a target profit (% or $) and max loss BEFORE you open the trade. Write them down. Stick to them.

**Rule 2: The 10% Max Loss Rule**
Never risk >10% of your total investment fund on one trade. If a trade hits this loss limit, close it.

**Rule 3: Time Stop**
If the thesis hasn't played out by 50% of the remaining time, consider closing. Theta decay accelerates.

**Rule 4: News Stop**
Close immediately if news contradicts your thesis. Don't wait to "see if it recovers."

**Rule 5: Profit Taking**
Take partial profits at 50-100% gain. Let the rest run with a trailing stop.

**General Exit Signals**
- Trade hits your predefined profit target → take profit
- Trade hits your max loss → exit immediately
- Underlying price invalidates your thesis → exit
- IV crashes after earnings/news (long options) → exit
- Time remaining < 7 days and trade is OTM → exit (theta has crushed value)
- Underlying gaps against you overnight → review at open, cut if thesis broken

**Golden Rule**: "Focus on not losing money rather than on making money." (Ch.9)
