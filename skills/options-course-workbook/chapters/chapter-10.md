# Chapter 10: Trading Techniques for Range-Bound Markets

## Core Idea
In sideways markets, profit from **theta decay** — options are wasting assets that lose value over time. Butterflies, condors, iron butterflies, calendar spreads, and collars are designed to generate returns when the underlying stays within a range.

## Frameworks Introduced
- **Long Butterfly**: Buy 1 ITM + sell 2 ATM + buy 1 OTM (same type, same expiration). Low-cost debit. Max profit at middle strike. Risk = net debit
- **Long Condor**: Buy 1 ITM + sell 1 ITM-body + sell 1 OTM-body + buy 1 OTM (4 strikes). Wider profit zone than butterfly. Risk = net debit
- **Long Iron Butterfly**: Bear call spread + bull put spread. Net credit. Limited risk. Profits within a range
- **Calendar Spread**: Buy long-term option + sell short-term option (same strike). Benefits from time decay of short leg. Net debit
- **Diagonal Spread**: Like calendar but with different strikes. Combines time and directional exposure
- **Collar**: Covered call + protective put (own stock, sell OTM call, buy OTM put). Limited risk, limited reward. Zero-cost if strikes are chosen to offset premiums

## Key Concepts
- **Body** = middle strike(s) sold; **Wings** = outer strikes bought
- Identify support/resistance levels to position the body between them
- Range-bound strategies work best when IV is low but not about to spike
- Use the "Quiet" stock screener to find low-volatility candidates

## Key Takeaways
1. Long butterfly = best when stock stays **right at the middle strike** at expiration
2. Long condor = wider profit zone, more forgiving than butterfly
3. Calendar spread profits from **time decay acceleration** in the short leg
4. Collar is ideal for protecting a long stock position while capping upside
