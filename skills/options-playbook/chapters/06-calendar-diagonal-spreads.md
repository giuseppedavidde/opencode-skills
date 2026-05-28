# Calendar & Diagonal Spreads

## Strategy: Long Calendar Spread w/ Calls (Play 24)
### Outlook & Definition
Neutral to slightly bullish. Sell a short-term call at strike A, buy a longer-term call at same strike A. Different expiration months. Profit from time-decay differential between months.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Maximum when stock is at strike A at front-month expiration. Achieved when short call decays to zero and long call retains time value.
- **Max Loss**: Net debit paid.
- **Breakeven**: Hard to specify — depends on pricing model.

### When to Use
Expect neutral activity near strike A during front month. Want to profit from time decay of short-term option. Prefer ATM strikes.

### Greeks Impact
- **Delta**: Near zero ATM. Slightly bullish if mildly bullish.
- **Theta**: Strongly positive. Front-month decays faster than back-month.
- **Vega**: Positive (long option has more time → higher vega). Want IV stable or rising.

### Time Decay Effect
Positive. The short front-month call decays faster than the long back-month call. This is the primary profit engine.

### Implied Volatility Impact
Somewhat positive. Long option has higher vega than short option (more time to expiration). Rising IV helps overall position.

### Trade-off
Pros: Defined risk, benefits from time decay, neutral outlook works. Cons: Complex, IV changes affect differently, max profit requires stock at strike.

---

## Strategy: Long Calendar Spread w/ Puts (Play 25)
### Outlook & Definition
Neutral to slightly bearish. Sell a short-term put, buy a longer-term put at same strike A. Different months.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Stock at strike A at front expiration.
- **Max Loss**: Net debit paid.
- **Breakeven**: Model-dependent.

### When to Use
Expect neutral activity. Mildly bearish view. Same mechanics as call calendar but with puts.

### Greeks Impact
- **Delta**: Near zero. Slightly bearish if mildly bearish.
- **Theta**: Positive. Front-month decays faster.
- **Vega**: Positive. Long put has higher vega.

### Time Decay Effect
Positive. Short-term put decays faster than long-term put.

### Implied Volatility Impact
Somewhat positive. Long vega > short vega.

### Trade-off
Pros: Low risk, theta positive. Cons: Need stock near strike at front expiration.

---

## Strategy: Diagonal Spread w/ Calls (Play 26)
### Outlook & Definition
Slightly bullish. Buy a longer-term call at strike A, sell a shorter-term call at different strike B. Different strikes AND months. Combines calendar + vertical spread logic.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Limited — depends on strikes and time. Typically achieved when stock is near short strike at front expiration.
- **Max Loss**: Net debit paid (limited).
- **Breakeven**: Model- dependent.

### When to Use
Slightly bullish. Want flexibility of different strikes and months. Similar to fig leaf but with more strike flexibility.

### Greeks Impact
- **Delta**: Positive but complex.
- **Theta**: Positive. Short-term decays faster.
- **Vega**: Mixed. Depends on strike relative to stock.

### Time Decay Effect
Positive overall due to shorter time decay on short leg.

### Implied Volatility Impact
Variable. Depends on IV term structure and strike skew.

### Trade-off
Pros: More flexible than calendar, defined risk. Cons: Complex to manage, model-dependent P&L.

---

## Strategy: Diagonal Spread w/ Puts (Play 27)
### Outlook & Definition
Slightly bearish. Buy longer-term put, sell shorter-term put at different strikes. Different months.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Limited. Depends on strikes and time.
- **Max Loss**: Net debit paid.
- **Breakeven**: Model-dependent.

### When to Use
Slightly bearish. Want diagonal flexibility with puts. Veteran+ level.

### Greeks Impact
- **Delta**: Negative.
- **Theta**: Positive.
- **Vega**: Mixed.

### Time Decay Effect
Positive. Short decay > long decay.

### Implied Volatility Impact
Variable. Watch term structure and skew.

### Trade-off
Pros: Flexible bearish strategy. Cons: Complex management.
