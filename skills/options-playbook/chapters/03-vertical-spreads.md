# Vertical Spreads (Two-Leg, Same Expiration)

## Strategy: Long Call Spread / Bull Call Spread (Play 10)
### Outlook & Definition
Bullish with a defined upside target. Buy a call at strike A, sell a call at higher strike B. Same expiration. Net debit. Reduces cost of long call while capping profit.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - Strike A) - net debit paid.
- **Max Loss**: Net debit paid.
- **Breakeven**: Strike A + net debit paid.

### When to Use
Bullish with specific price target. Want to reduce cost of a long call. Expect moderate upside, not a moonshot. Prefer 30-45 DTE.

### Greeks Impact
- **Delta**: Positive but lower than long call alone.
- **Theta**: Somewhat neutral. Long call theta (bad) offset by short call theta (good).
- **Vega**: Mixed. Depends on where stock is relative to strikes.

### Time Decay Effect
Neutral-ish. Spread's value holds better than a naked long call as expiration approaches, especially if stock is near/above strike B.

### Implied Volatility Impact
If correct (stock above B): want IV decrease. If wrong (stock below A): want IV increase. Neutral overall due to offsetting legs.

### Trade-off
Pros: Lower cost than long call, defined risk/reward, less time decay impact. Cons: Capped profit, max profit only at expiration if at/above B.

---

## Strategy: Long Put Spread / Bear Put Spread (Play 11)
### Outlook & Definition
Bearish with a defined downside target. Sell a put at strike A, buy a put at higher strike B. Same expiration. Net debit.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - Strike A) - net debit paid.
- **Max Loss**: Net debit paid.
- **Breakeven**: Strike B - net debit paid.

### When to Use
Bearish with floor target. Alternative to long put with reduced cost. Good when IV is high (the short put offsets IV cost). Prefer 30-45 DTE.

### Greeks Impact
- **Delta**: Negative. Profits from stock decline.
- **Theta**: Somewhat neutral.
- **Vega**: Partially neutralized by the two legs.

### Time Decay Effect
Neutral-ish. Less decay impact than naked long put.

### Implied Volatility Impact
If correct (stock below A): want IV decrease. If wrong (stock above B): want IV increase.

### Trade-off
Pros: Lower cost than long put, defined risk, IV neutralized. Cons: Capped profit, spread width limits gain.

---

## Strategy: Short Call Spread / Bear Call Spread (Play 12)
### Outlook & Definition
Bearish to neutral. Sell a call at strike A, buy a call at higher strike B. Same expiration. Net credit. Risk-limited alternative to naked short call.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received.
- **Max Loss**: (Strike B - Strike A) - net credit.
- **Breakeven**: Strike A + net credit.

### When to Use
Bearish or neutral outlook. Want defined risk instead of naked short call. Strike A ~1 SD OTM. 30-45 DTE for time decay acceleration.

### Greeks Impact
- **Delta**: Negative. Benefits from stock decline or staying below A.
- **Theta**: Somewhat positive. Both options benefit from decay.
- **Vega**: Want IV to decrease. Both options lose value.

### Time Decay Effect
Positive. Want both options to expire worthless. Decay accelerates near expiration.

### Implied Volatility Impact
Negative. IV decrease helps. IV spike can hurt. The long call caps IV damage.

### Trade-off
Pros: Defined risk compared to naked short call, time decay works for you, high probability. Cons: Lower credit than naked short call, profit capped at credit.

---

## Strategy: Short Put Spread / Bull Put Spread (Play 13)
### Outlook & Definition
Bullish to neutral. Sell a put at strike B, buy a put at lower strike A. Same expiration. Net credit. Defined-risk alternative to naked short put.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received.
- **Max Loss**: (Strike B - Strike A) - net credit.
- **Breakeven**: Strike B - net credit.

### When to Use
Bullish or neutral. Collect credit with defined risk. Strike B ~1 SD OTM. 30-45 DTE.

### Greeks Impact
- **Delta**: Positive. Benefits from stock rise or staying above B.
- **Theta**: Somewhat positive. Time decay helps.
- **Vega**: Want IV to decrease.

### Time Decay Effect
Positive. Both puts decay with time. You want them to expire worthless.

### Implied Volatility Impact
Negative. IV contraction reduces premium. The long put at A limits risk from IV expansion.

### Trade-off
Pros: Defined risk, high probability, time decay works. Cons: Capped profit, margin requirement.
