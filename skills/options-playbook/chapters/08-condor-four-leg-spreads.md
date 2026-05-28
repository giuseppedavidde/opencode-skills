# Condors & Four-Leg Spreads

## Strategy: Long Condor Spread w/ Calls (Play 37)
### Outlook & Definition
Neutral. Buy 1 call at A, sell 1 call at B, sell 1 call at C, buy 1 call at D. Same expiration. B-C is the body (profit zone). Like a butterfly with a flat top.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - A) minus net debit. Achieved when stock is anywhere between B and C at expiration.
- **Max Loss**: Net debit paid.
- **Breakeven**: Strike A + debit (lower), Strike D - debit (upper).

### When to Use
Neutral with a wider "don't care" zone than butterfly. Lower precision required. Expect stock in range B-C.

### Greeks Impact
- **Delta**: Near zero when range-bound.
- **Gamma**: Negative between B and C (short gamma), positive in wings.
- **Theta**: Slightly positive or neutral.
- **Vega**: Very low. IV-insensitive.

### Time Decay Effect
Low. Less theta impact than butterfly due to wider spread.

### Implied Volatility Impact
Very low. Condors are among the most IV-neutral strategies.

### Trade-off
Pros: Wide profit zone, low IV sensitivity, defined risk, lower precision needed than butterfly. Cons: Lower potential return than butterfly, requires larger account for multiple legs.

---

## Strategy: Long Condor Spread w/ Puts (Play 38)
### Outlook & Definition
Neutral. Same profile as call condor but constructed with puts. Buy put at A, sell put at B, sell put at C, buy put at D.

### Max Profit / Max Loss / Breakeven
Same as call condor: Max profit between B and C.

### When to Use
Neutral with wider range.

### Greeks Impact
Same structure as call condor.

### Trade-off
Same as call condor. Choose puts if put prices are more favorable.

---

## Strategy: Iron Condor (Play 39)
### Outlook & Definition
Neutral. Sell an OTM put at B, sell an OTM call at C, buy a further OTM put at A, buy a further OTM call at D. Same expiration. Net credit. The most popular neutral strategy.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received (stock between B and C at expiration).
- **Max Loss**: (Strike B - A) - credit (put side) or (Strike D - C) - credit (call side). Typically equal width.
- **Breakeven**: Strike B - credit (lower), Strike C + credit (upper).

### When to Use
Expect stock to stay within a range. Collect credit with defined risk. High probability trade. Sell strikes ~1 SD OTM. 30-45 DTE.

### Greeks Impact
- **Delta**: Near zero when stock between B and C.
- **Gamma**: Negative. Short gamma between B and C. Increases near expiration.
- **Theta**: Strongly positive. Both credit spreads decay with time.
- **Vega**: Negative. Want IV to decline. IV expansion hurts.

### Time Decay Effect
Strongly positive. Both short options benefit from time decay. Theta accelerates in the final 30 days.

### Implied Volatility Impact
Negative. IV crush benefits iron condor. IV expansion (before events) hurts. Avoid holding through events.

### Trade-off
Pros: Defined risk, credit received, high probability of profit (60-80%), time decay works, wide profit zone. Cons: Limited profit (credit only), need account approval for spreads, can suffer from tail risk.

---

## Strategy: Double Diagonal (Play 40)
### Outlook & Definition
Neutral to slightly directional. Combines two diagonal spreads — one call diagonal above market and one put diagonal below. Different expirations and strikes.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Complex. Depends on stock price at front expiration and back-month pricing.
- **Max Loss**: Typically limited but depends on strikes.
- **Breakeven**: Multiple BEs — model-dependent.

### When to Use
Neutral with time decay advantage. More advanced than iron condor. Veteran+ only.

### Greeks Impact
- **Delta**: Near zero if symmetrical.
- **Theta**: Positive. Front-month decays faster than back-month on both sides.
- **Vega**: Mixed. Long options have longer time → higher vega.

### Time Decay Effect
Positive on both sides. Front-month options (short) decay faster than back-month options (long).

### Implied Volatility Impact
Variable. Higher IV on long options (more time) means net positive vega in normal markets.

### Trade-off
Pros: Theta positive on both sides, defined risk, profit from time decay. Cons: Highly complex, model-dependent P&L, multiple expirations to manage.
