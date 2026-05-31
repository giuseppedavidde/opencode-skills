---
name: options-playbook
description: "Knowledge base from 'The Options Playbook' by Brian Overby. 40+ option strategies reference for all market outlooks."
allowed-tools:
  - read
  - grep
argument-hint: [strategy name, Greek, or outlook]
orchestrator:
  parallel: false
  type: kb
---

# The Options Playbook, Expanded 2nd Edition
**Author**: Brian Overby | **Strategies**: 40 | **Generated**: 2026-05-28

## Core Frameworks & Mental Models

### Options Basics
An **option** is a contract giving the owner the right to buy or sell an asset at a fixed price (the **strike price**) for a specific period of time. The seller has the **obligation** to take the opposite side. One contract normally represents 100 shares.

- **Call**: Right to BUY stock at strike price. Buy calls when bullish.
- **Put**: Right to SELL stock at strike price. Buy puts when bearish.
- **Premium**: The price paid for an option. Consists of intrinsic value + time value.
- **Intrinsic Value**: The amount an option is ITM. Only ITM options have intrinsic value.
- **Time Value**: The portion of premium based on time to expiration. OTM options have 100% time value.
- **ITM (In-the-Money)**: Call – stock above strike. Put – stock below strike.
- **OTM (Out-of-the-Money)**: Call – stock below strike. Put – stock above strike.
- **ATM (At-the-Money)**: Stock price equals (or is closest to) strike price.
- **Open Interest**: Number of option contracts that exist for a given stock/strike/expiration. Higher OI = better liquidity.

### Strategy Selection Framework
1. **Determine your outlook**: Which of the 4 outlooks matches your forecast?
2. **Assess risk tolerance**: Can you accept unlimited risk? Limited loss?
3. **Pick the time frame**: Short-term (30-45 days) for time decay sellers; long-term (LEAPS) for stock substitutes.
4. **Select the strategy**: Match the outlook + risk profile to the appropriate play.

### The Four Outlooks
- **Bullish**: Expect stock to rise. Strategies: Long Call, Bull Call Spread, Short Put, Short Put Spread.
- **Bearish**: Expect stock to fall. Strategies: Long Put, Bear Put Spread, Short Call, Short Call Spread.
- **Neutral**: Expect minimal/no movement. Strategies: Short Straddle, Short Strangle, Iron Butterfly, Iron Condor.
- **Volatile**: Expect big move but unsure direction. Strategies: Long Straddle, Long Strangle, Back Spreads.

### Risk Profiles
| Strategy | Max Loss | Max Profit | Risk Level |
|---|---|---|---|
| Long Call/Put | Premium paid | Unlimited/substantial | Limited |
| Short Call | Unlimited | Premium received | Unlimited |
| Short Put | Strike minus premium | Premium received | Substantial |
| Spreads (debit) | Net debit paid | Width minus debit | Limited |
| Spreads (credit) | Width minus credit | Net credit received | Limited |
| Straddle/Strangle (long) | Premium paid | Unlimited/substantial | Limited |
| Straddle/Strangle (short) | Unlimited/substantial | Premium received | Unlimited |

### Greeks Overview
- **Delta (Δ)**: Expected price change of option per $1 stock move. Calls: 0 to +1. Puts: -1 to 0. ATM ≈ 0.50. Also interpreted as probability of finishing ITM.
- **Gamma (Γ)**: Rate of change of delta per $1 stock move. Highest for ATM near-term options. "Acceleration."
- **Theta (Θ)**: Daily time decay. Option buyer's enemy, seller's friend. ATM options decay fastest. Decay accelerates near expiration.
- **Vega (ν)**: Price change per 1-point change in IV. Longer-term options have higher vega. Only affects time value.
- **Rho (ρ)**: Price change per 1% change in interest rates. Negligible for short-term; matters for LEAPS.

### Time Decay (Theta) — The Master Concept
Time decay is the gradual erosion of an option's time value as expiration approaches.
- Option buyers lose money from time decay (theta is negative for longs).
- Option sellers profit from time decay (theta is positive for shorts).
- At-the-money options have the most time value → decay fastest in dollar terms.
- Decay accelerates in the final 30-45 days → sweet spot for premium sellers.
- Calendar spreads exploit the difference in decay rates between expirations.

### Implied Volatility (IV) — The Second Master Concept
IV reflects the market's expectation of future stock movement magnitude (not direction).
- High IV → expensive options → good for sellers, bad for buyers.
- Low IV → cheap options → good for buyers, bad for sellers.
- Vega measures IV sensitivity. Multi-option strategies can neutralize IV risk.
- IV typically rises before events (earnings, FDA rulings) and collapses after ("volatility crush").
- Compare IV to historical volatility to gauge whether options are over/underpriced.

## Strategy Index (by Outlook)

### Bullish Strategies
| Strategy | File | Max Risk |
|---|---|---|
| Long Call | chapters/01-directional-strategies.md | Premium |
| Short Put | chapters/01-directional-strategies.md | Strike - premium |
| Cash-Secured Put | chapters/01-directional-strategies.md | Strike price |
| Bull Call Spread | chapters/03-vertical-spreads.md | Net debit |
| Bull Put Spread | chapters/03-vertical-spreads.md | Width - credit |
| Covered Call (neutral-bullish) | chapters/02-stock-based-strategies.md | Stock loss |
| Long Combination | chapters/05-combination-ratio-spreads.md | Strike + debit |
| Back Spread w/ Calls | chapters/05-combination-ratio-spreads.md | Limited/calculated |

### Bearish Strategies
| Strategy | File | Max Risk |
|---|---|---|
| Long Put | chapters/01-directional-strategies.md | Premium |
| Short Call | chapters/01-directional-strategies.md | Unlimited |
| Bear Put Spread | chapters/03-vertical-spreads.md | Net debit |
| Bear Call Spread | chapters/03-vertical-spreads.md | Width - credit |
| Short Combination | chapters/05-combination-ratio-spreads.md | Unlimited |
| Back Spread w/ Puts | chapters/05-combination-ratio-spreads.md | Limited/calculated |

### Neutral Strategies
| Strategy | File | Max Risk |
|---|---|---|
| Short Straddle | chapters/04-volatility-strategies.md | Unlimited |
| Short Strangle | chapters/04-volatility-strategies.md | Unlimited |
| Iron Butterfly | chapters/07-butterfly-spreads.md | Width - credit |
| Iron Condor | chapters/08-condor-four-leg-spreads.md | Width - credit |
| Short Call Spread | chapters/03-vertical-spreads.md | Width - credit |
| Short Put Spread | chapters/03-vertical-spreads.md | Width - credit |

### Volatile (Direction-Uncertain) Strategies
| Strategy | File | Max Risk |
|---|---|---|
| Long Straddle | chapters/04-volatility-strategies.md | Premium |
| Long Strangle | chapters/04-volatility-strategies.md | Premium |
| Long Call Butterfly | chapters/07-butterfly-spreads.md | Net debit |
| Long Put Butterfly | chapters/07-butterfly-spreads.md | Net debit |
| Long Condor | chapters/08-condor-four-leg-spreads.md | Net debit |
| Calendar Spread | chapters/06-calendar-diagonal-spreads.md | Net debit |

## Greek Reference
- **Delta**: Directional sensitivity. Used for position sizing and hedging (position delta).
- **Gamma**: Convexity risk. High gamma = rapid delta changes. ATM near-term = highest gamma.
- **Theta**: Time decay. Key for premium sellers. Sell 30-45 day options for optimal theta.
- **Vega**: IV sensitivity. Buy when IV low, sell when IV high. Calendar spreads reduce vega exposure.
- **Rho**: Interest rate sensitivity. Skip for short-term trades.

## Supporting Files
- **glossary.md**: Complete options terminology reference
- **patterns.md**: Strategy selection patterns by scenario
- **cheatsheet.md**: Quick-reference strategy→outlook table, Greeks, exit rules
