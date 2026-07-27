# Chapter 8: Risk and Money Management

## Core Idea
Money management is the art of keeping ruin risk acceptable while maximizing profit potential. It's more art than science — there are no "right" answers, only trade-offs between risking too much (blowup) and too little (leaving money on the table). The primary goal: **stay in the game**.

## Frameworks Introduced

### The Two Paths to Trading Death
1. **Slow painful death**: Extended drawdowns that exceed psychological limits → trader quits in anguish.
2. **Spectacular rapid death (blowup)**: A sudden price shock wipes the account overnight.

### The N Factor — Volatility-Based Position Sizing
The Turtle innovation: size positions so that **1 ATR of price movement = 1% of account equity** across ALL markets.

- **N** = ATR in dollar terms for a specific market
- **Unit size** = (1% of account) ÷ N
- Example: $1M account, 1% = $10,000. If gold ATR = $1,000 per contract → unit = 10 contracts
- Volatile markets get SMALLER positions automatically — no need to guess

**Critical advantage over stop-distance sizing**: In the October 1987 crash, markets gapped through stops. Curtis used a ½-ATR stop vs. others' 2-ATR — if sized by stop distance, his position would have been 4× larger. Volatility-based sizing saved him.

### The Turtle Risk Limits (Hard Caps)
| Limit | Rule |
|-------|------|
| Per market | Maximum 4 units |
| Correlated markets | Maximum 6 units total |
| Per direction | Maximum 10 units (long or short); 12 if uncorrelated markets |
| **Purpose** | Filter out lagging markets (2nd/3rd signals in correlated groups nearly always lose) |

These limits saved Rich Dennis over **$100 million** on Black Monday 1987.

### The Drawdown-Risk Relationship
Historical simulation shows: risking **3% per trade** on the Donchian Trend system would have caused **total ruin** during the 1987 interest-rate shock. Recommendation: trade at a level where simulated drawdown ≤ 50% of your psychological tolerance.

## Key Concepts
- **Compounding is powerful but fragile**: 30% CAGR turns $50K into ~$10M in 20 years, but only if you never blow up.
- **Doctors and dentists disproportionately fail at trading**: High intelligence → unrealistic expectations → excessive risk. Trading is simple but NOT easy.
- **Oversimplified position sizing breaks**: "1 contract per $20K" ignores volatility changes. The same formula creates wildly different risk levels across decades.
- **Correlated markets cluster at trend reversals**: Everything moves against you simultaneously at the worst moments. Unit limits are insurance against this.

## Anti-patterns
- **Sizing by stop distance alone**: Gap risk makes this lethal in price shocks.
- **100%+ return targets**: Greatly increases blowup probability. Stick to 20-30% CAGR.
- **Equal contracts per market**: A natural gas contract (ATR $7,500) dwarfs a corn contract. Must normalize.
- **No unit limits**: "I implemented everything except the unit limits" — this IS the system. Without limits, you hold too many correlated positions.
- **Ignoring tail risks**: Nuclear bombs, terrorist attacks, flash crashes — plan for the unthinkable.

## Key Takeaways
1. Volatility-based position sizing (N factor) is the single most important Turtle innovation.
2. Unit limits are NOT optional — they filter losing trades and prevent correlation blowups.
3. Trade at 50% of your psychological drawdown tolerance based on historical simulation.
4. The primary goal is survival: time is on your side with a positive-expectation system.
5. 30% annual returns compound to enormous wealth — chasing 100%+ returns is a path to ruin.
