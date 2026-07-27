# Option Trading Patterns & Strategies — Natenberg Framework

## When to Use Each Strategy
This reference organizes option strategies by market view and volatility regime, following Natenberg's principle that volatility awareness must accompany every trading decision.

---

## 1. Volatility Strategies (Delta-Neutral)

### Long Straddle / Strangle
- **When**: Expect large move in either direction; IV is low relative to forecast; high uncertainty events (earnings, FDA, elections)
- **How**: Buy ATM call + ATM put (straddle) or OTM call + OTM put (strangle). Delta-neutral at inception
- **Trade-offs**: +Gamma, −Theta, +Vega. Profits from realized movement exceeding implied. Time decay is the enemy — need movement fast. Loss limited to premium paid
- **Risk**: If IV drops after entry, position loses even if underlying moves. Maximum loss if underlying stays at strike through expiration

### Short Straddle / Strangle
- **When**: Expect range-bound market; IV is high relative to forecast; want to collect time decay
- **How**: Sell ATM call + ATM put (straddle) or OTM call + OTM put (strangle). Delta-neutral at inception
- **Trade-offs**: −Gamma, +Theta, −Vega. Profits from time decay and IV contraction. Gamma risk is catastrophic — large moves create exponentially growing losses. Unlimited risk
- **Risk**: A volatility explosion (e.g., 2008-style event) can destroy months of premium collection in days. Position sizing critical — never sell more than you can survive being wrong on

### Long Butterfly
- **When**: Expect market to pin near a specific strike; IV is high; want defined-risk range-bound play
- **How**: Buy 1× lower wing, sell 2× body, buy 1× upper wing (all calls or all puts). Ratio always 1×2×1
- **Trade-offs**: −Gamma, +Theta, −Vega (like short straddle but with limited risk). Max value at expiration = distance between strikes. Max loss = debit paid. Can be done in large size due to limited risk
- **Risk**: Must be right about pin location. Iron butterfly (credit version) has identical characteristics

### Ratio Spreads
- **When**: IV is high (sell more than buy); want volatility exposure with directional bias
- **How**: Example — buy 1 ATM call, sell 2 OTM calls (1×2 ratio). Delta-neutral at inception
- **Trade-offs**: −Gamma, +Theta initially. Delta can invert from neutral/flat to short if underlying rallies through short strike. Profit zone is capped between strikes; unlimited risk beyond short strike
- **Risk**: Gamma inversion — bullish ratio becomes bearish if market moves too far. Must monitor and potentially adjust

### Calendar / Time Spreads
- **When**: Expect IV of near month to decline faster than far month; near-term event risk will pass
- **How**: Sell near-month option, buy far-month option (same strike, same type). Long calendar = +Vega
- **Trade-offs**: Profits from time decay differential and IV convergence. Sensitive to underlying pinning near strike at near expiration. Delta can invert if underlying moves through strike
- **Risk**: If IV rises in near month (crisis event), spread loses. Vega-positive means rising IV helps

---

## 2. Directional Strategies (Bull/Bear)

### Vertical Spreads (Call/Put Spreads)
- **When**: Have directional view; want defined-risk defined-reward. Low IV → buy ATM option; High IV → sell ATM option
- **How — Bull**: Buy lower strike, sell higher strike (calls or puts). **Bear**: Buy higher strike, sell lower strike
- **Trade-offs**: Delta never inverts — purely directional. In-the-money spreads: +Theta, profiting if market sits still. Out-of-the-money spreads: −Theta, requiring movement to profit
- **Risk**: Limited to debit paid (or width minus credit received). Directional risk only — no gamma catastrophe possible

### Risk Reversals
- **When**: Have view on skewness; want to express volatility asymmetry view
- **How**: Buy OTM puts, sell OTM calls (bearish skew view), delta-hedge with underlying. Often uses 25Δ options
- **Trade-offs**: Profits if skew steepens (puts become relatively more expensive). Essentially a bet on the shape of the volatility surface
- **Risk**: Overall IV changes affect position even if skew view is correct

### Protective Put / Covered Call
- **When**: Own underlying; want downside protection (protective put) or income enhancement (covered call)
- **How**: Protective put: long stock + long put = synthetic long call. Covered call: long stock + short call = synthetic short put
- **Trade-offs**: Protective put = insurance — costs premium but caps loss. Covered call = income — collects premium but caps upside
- **Risk**: Protective put: premium cost drags returns in calm markets. Covered call: stock called away in strong rallies, missing upside

---

## 3. Arbitrage & Synthetics

### Conversion / Reversal
- **When**: Put-call parity is violated; synthetic underlying mispriced vs. actual underlying
- **How — Conversion**: Buy underlying, sell call, buy put (all same strike/expiry). **Reversal**: Sell underlying, buy call, sell put
- **Trade-offs**: Risk-free arbitrage in theory; in practice, subject to interest rate, dividend, and execution risk. Requires low transaction costs
- **Risk**: Typically institutional strategy — retail commissions destroy edge. Settlement and interest rate risks persist

### Box Spread
- **When**: Mispricing between call spread and put spread at same strikes
- **How**: Buy call spread + buy put spread at same strikes. Creates synthetic risk-free loan
- **Trade-offs**: Locks in interest rate arbitrage. Extremely capital-intensive
- **Risk**: Early exercise of American options can break the box. Margin requirements can be prohibitive

---

## 4. Advanced Skew/Kurtosis Strategies

### Kurtosis / "Dragonfly"
- **When**: Expect kurtosis to increase (fat tails getting fatter) or decrease
- **How**: Buy/sell strangles, vega-hedge with ATM straddles. 2×1 strangle:straddle ratio for vega neutrality
- **Trade-offs**: Pure kurtosis exposure — profits from changes in curvature of the skew independent of overall IV level
- **Risk**: Complex position management; vega hedge ratios change as market moves

### Cross-Expiration Skew Trades
- **When**: Skew shapes differ between expiration months
- **How**: Buy skew in underpriced month, sell skew in overpriced month (e.g., buy June OTM puts, sell March OTM puts)
- **Trade-offs**: Can combine with term structure view — if June IV is also cheap vs. March, position benefits from both skew and vol convergence
- **Risk**: Multiple dimensions of risk (skewness, kurtosis, overall IV term structure); requires sophisticated monitoring

---

## Decision Framework

```
Market View:
├─ Directional (Bull/Bear) → Vertical Spreads
│   ├─ Low IV  → Buy ATM option
│   └─ High IV → Sell ATM option
├─ Volatility (move magnitude) → Straddle/Strangle
│   ├─ Low IV  → Buy (Long Gamma)
│   └─ High IV → Sell (Short Gamma)
├─ Range-Bound (pin) → Butterfly/Condor
│   └─ Always for credit or limited debit
├─ Skew View (distribution shape) → Risk Reversal
└─ Kurtosis View (tail fatness) → Strangle + Straddle hedge
```
