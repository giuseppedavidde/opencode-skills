# Volatility Strategies: Straddles & Strangles

## Strategy: Long Straddle (Play 14)
### Outlook & Definition
Expect a big move but unsure direction. Buy an ATM call and an ATM put at the same strike A. Same expiration. Profit if stock makes a large move either way.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Unlimited upside (stock → ∞). Limited to strike minus debit on downside.
- **Max Loss**: Net debit paid (total premium for call + put).
- **Breakeven**: Strike A ± net debit paid.

### When to Use
Expecting major volatility (earnings, FDA decision, merger). IV is low and you anticipate IV expansion. Stock has made large moves on similar events historically.

### Greeks Impact
- **Delta**: Near zero initially (long call + long put = neutral). Becomes directional as stock moves.
- **Gamma**: Positive. Benefits from large moves — gamma accelerates profits.
- **Theta**: Double enemy. Time decay works against both legs.
- **Vega**: Strongly positive. IV expansion increases value of both options.

### Time Decay Effect
Strongly negative. Two options decaying = double theta damage. This is the main risk — you need the move to happen quickly.

### Implied Volatility Impact
Strongly positive. You want IV to rise (volatility expansion). If IV drops (volatility crush), you get hit doubly.

### Trade-off
Pros: Profit from big moves in either direction, unlimited upside, benefits from IV expansion. Cons: Expensive premium, double time decay, need large move just to break even.

---

## Strategy: Short Straddle (Play 15)
### Outlook & Definition
Expect minimal movement. Sell an ATM call and an ATM put at the same strike A. Same expiration. Collect double premium. **All-Stars only** — unlimited risk.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received.
- **Max Loss**: Unlimited upside; substantial downside (strike minus credit at zero).
- **Breakeven**: Strike A ± net credit.

### When to Use
Strong conviction stock will not move. IV is high and you expect mean reversion. Market professionals who monitor full-time.

### Greeks Impact
- **Delta**: Near zero initially (short call + short put = neutral).
- **Gamma**: Enemy. Large moves accelerate losses rapidly.
- **Theta**: Double friend. Time decay profits on both legs.
- **Vega**: Strongly negative. IV expansion is dangerous — increases both option values.

### Time Decay Effect
Strongly positive. Two options decaying = double theta profit. Maximum benefit if stock stays at strike.

### Implied Volatility Impact
Strongly negative. You want IV to fall (volatility crush). IV spike is your worst enemy.

### Trade-off
Pros: High premium collected, double time decay, wide profit zone. Cons: Unlimited upside risk, substantial downside risk, IV expansion can destroy position.

---

## Strategy: Long Strangle (Play 16)
### Outlook & Definition
Expect a big move but unsure direction. Buy an OTM put (strike A) and an OTM call (strike B). Same expiration. Cheaper than straddle but needs larger move.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Unlimited upside. Limited to strike A minus debit on downside.
- **Max Loss**: Net debit paid (lower cost than straddle).
- **Breakeven**: Strike A - debit (downside) and strike B + debit (upside).

### When to Use
Same as long straddle but with a lower premium cost when you expect an very large move. Options are OTM so cheaper.

### Greeks Impact
- **Delta**: Near zero. Neutral at initiation.
- **Gamma**: Positive but lower than straddle (OTM options have less gamma initially).
- **Theta**: Double enemy. Time decay works against both legs.
- **Vega**: Positive. Benefits from IV expansion.

### Time Decay Effect
Strongly negative. Even more punishing than straddle because OTM options lose value faster percentage-wise.

### Implied Volatility Impact
Strongly positive. IV rise increases both option values.

### Trade-off
Pros: Cheaper than straddle, unlimited upside, benefits from volatility. Cons: Needs larger move than straddle, wider break-even points, double time decay.

---

## Strategy: Short Strangle (Play 17)
### Outlook & Definition
Expect minimal movement. Sell an OTM put (strike A) and an OTM call (strike B). Same expiration. Wider profit zone than short straddle. **All-Stars only**.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Net credit received.
- **Max Loss**: Unlimited upside; substantial downside (strike A minus credit at zero).
- **Breakeven**: Strike A - credit and strike B + credit.

### When to Use
Expect stock to stay within a defined range. IV is high. Want wider profit zone than short straddle. Sell strikes ~1 SD OTM.

### Greeks Impact
- **Delta**: Near zero initially (if strikes equidistant from stock).
- **Theta**: Double friend. Time decay on both options.
- **Vega**: Strongly negative. IV expansion dangerous.

### Time Decay Effect
Strongly positive. Two options decaying. Wider profit zone means less precision needed.

### Implied Volatility Impact
Strongly negative. Want IV crush. OTM options have high vega proportionally — IV spike is dangerous.

### Trade-off
Pros: Higher probability than short straddle (wider profit zone), double time decay. Cons: Unlimited upside risk, substantial downside risk, needs constant monitoring.
