# Butterfly Spreads (Three-Leg, Four-Option Spreads)

## Strategy: Long Butterfly Spread w/ Calls (Play 28)
### Outlook & Definition
Neutral. Buy 1 ITM call at A, sell 2 ATM calls at B, buy 1 OTM call at C. Same expiration. Equidistant strikes. Low-cost, defined-risk bet on stock finishing near B.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - A) - net debit. Achieved at strike B at expiration.
- **Max Loss**: Net debit paid.
- **Breakeven**: Strike A + debit (lower) and Strike C - debit (upper).

### When to Use
Expect stock to land near B at expiration. Low volatility outlook. Low cost, high probability if forecast is precise.

### Greeks Impact
- **Delta**: Near zero (neutral around B).
- **Gamma**: Negative at center (short gamma). Positive in wings.
- **Theta**: Mixed. Can be slightly positive or neutral.
- **Vega**: Near zero (long and short vega offset). Low IV sensitivity.

### Time Decay Effect
Low impact. Theta is minimal — butterfly is a "late-expiration" strategy. Closer to expiration, gamma risk increases.

### Implied Volatility Impact
Low impact. Vega is near zero — butterflies are relatively IV-insensitive.

### Trade-off
Pros: Low cost, defined risk, profit from pin action at B, low IV sensitivity. Cons: Must pin exactly at B for max profit, small max profit relative to risk.

---

## Strategy: Long Butterfly Spread w/ Puts (Play 29)
### Outlook & Definition
Neutral. Buy 1 put at A, sell 2 puts at B, buy 1 put at C. Same expiration. Same risk profile as call butterfly.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Strike B - A minus net debit.
- **Max Loss**: Net debit paid.
- **Breakeven**: Strike B ± debit.

### When to Use
Neutral outlook. Low cost.

### Greeks Impact
Same structure as call butterfly. Neutral delta, negative gamma at center, low vega.

### Time Decay Effect
Low.

### Implied Volatility Impact
Low.

### Trade-off
Same as call butterfly.

---

## Strategy: Iron Butterfly (Play 30)
### Outlook & Definition
Neutral. Sell an ATM put at B, sell an ATM call at B, buy an OTM put at A, buy an OTM call at C. Same expiration. Net credit. Short straddle + wings for protection.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received (stock at B at expiration).
- **Max Loss**: (Strike B - A) minus credit. Limited on both sides.
- **Breakeven**: Strike B ± credit.

### When to Use
Expect pin action at B. Want income with defined risk. More conservative than short straddle.

### Greeks Impact
- **Delta**: Near zero.
- **Gamma**: Negative. Short gamma at center.
- **Theta**: Positive. Time decay works for you.
- **Vega**: Negative. Want IV to decrease.

### Time Decay Effect
Positive. Both short options decay. The wings provide protection at low cost.

### Implied Volatility Impact
Negative. IV crush benefits the position. IV expansion hurts.

### Trade-off
Pros: Defined risk, credit received, high probability, time decay works. Cons: Limited profit, needs precise pin, short gamma.

---

## Strategy: Skip Strike Butterfly w/ Calls (Play 31)
### Outlook & Definition
Neutral to slightly bullish. Long butterfly where strikes are not equidistant — one strike is "skipped." Buy A, sell B and C (skip gap), buy D.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Wider than regular butterfly but higher cost. Occurs between B and C.
- **Max Loss**: Net debit paid.
- **Breakeven**: Complex.

### When to Use
Neutral outlook with wider expected range. Veteran+ level.

### Greeks Impact
Broader gamma profile than standard butterfly. Wider profit zone.

### Time Decay Effect
Low to moderate.

### Implied Volatility Impact
Low.

### Trade-off
Pros: Wider profit zone than regular butterfly. Cons: Higher cost than regular butterfly.

---

## Strategy: Skip Strike Butterfly w/ Puts (Play 32)
Same concept as call version but with puts. Neutral to slightly bearish.

## Strategy: Inverse Skip Strike Butterfly w/ Calls (Play 33)
### Outlook & Definition
Neutral to slightly bearish. Inverse of skip strike butterfly. Sell 2 or buy different ratios of skipped strikes. Different risk/reward skew.

### Greeks Impact
Opposite gamma profile to regular skip strike.

### Trade-off
Pros: Profit from stock NOT pinning in skipped zone. Cons: Complex, limited profit.

## Strategy: Inverse Skip Strike Butterfly w/ Puts (Play 34)
Same as inverse skip but constructed with puts. Neutral to slightly bullish.

## Strategy: Christmas Tree Butterfly w/ Calls (Play 35)
### Outlook & Definition
Slightly bullish. Asymmetrical butterfly where strikes are not equally spaced. Wider call wing on the upside. For example, buy A, sell B, sell C, buy D where D-C > B-A.

### Max Profit / Max Loss / Breakeven
Skewed profit zone. Wider on the upside.

### When to Use
Slightly bullish with defined range. Expect upside drift.

### Greeks Impact
Asymmetrical gamma. Positive delta skew.

### Trade-off
Pros: Upside profit potential with defined risk. Cons: Higher cost than standard butterfly.

## Strategy: Christmas Tree Butterfly w/ Puts (Play 36)
Same as Christmas Tree but with puts. Slightly bearish skew. Wider profit zone on downside.
