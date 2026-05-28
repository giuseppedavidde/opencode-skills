# Stock-Based Strategies

## Strategy: Covered Call (Play 6)
### Outlook & Definition
Neutral to bullish. Own at least 100 shares of stock. Sell a call (strike A) against those shares. Obligates you to sell stock at strike A if assigned. Also known as "Buy/Write" when executed simultaneously.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike A - stock price) + premium received.
- **Max Loss**: Stock price - premium received (stock goes to zero). Also opportunity risk if stock skyrockets.
- **Breakeven**: Stock purchase price - premium received.

### When to Use
You own a stock that has appreciated, or you're willing to sell at a target price. Want income generation from your portfolio. Accept capped upside in exchange for immediate cash.

### Greeks Impact
- **Delta**: Positive but reduced by short call. Net delta = stock delta (1.0) - call delta.
- **Theta**: Friend. Time decay erodes the short call value daily.
- **Vega**: Want IV to decrease. Lower IV reduces call price.

### Time Decay Effect
Strongly positive. Sell 30-45 day calls for optimal theta. The short call loses value daily.

### Implied Volatility Impact
Negative (for the option leg). High IV = better premium collected. IV contraction good for your short position.

### Trade-off
Pros: Generates income, downside buffer from premium, simple strategy. Cons: Capped upside, stock can be called away, stock loss risk remains.

---

## Strategy: Protective Put (Play 7)
### Outlook & Definition
Bullish but nervous. Own stock. Buy a put to insure against downside. Also called "Married Put" when bought simultaneously. Like insurance — you pay premium for protection.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Theoretically unlimited (stock can keep rising).
- **Max Loss**: (Stock price - strike A) + premium paid = the "deductible."
- **Breakeven**: Stock price + premium paid.

### When to Use
Own stock with unrealized gains you want to protect. Uncertain about short-term but bullish long-term. Alternative to stop-loss orders (no gap risk).

### Greeks Impact
- **Delta**: Positive (long stock + long put = net long but protected).
- **Theta**: Enemy. Time decay erodes put value.
- **Vega**: Want IV to increase. Higher IV raises put value (good for protection).

### Time Decay Effect
Negative. The put loses value as expiration approaches. Cost of insurance decreases over time.

### Implied Volatility Impact
Positive. IV spike (market fear) increases put value — your protection becomes more valuable when needed.

### Trade-off
Pros: Defined downside protection, unlimited upside, no gap risk. Cons: Premium cost eats into profits, must decide on time horizon.

---

## Strategy: Collar (Play 8)
### Outlook & Definition
Bullish but nervous. Own stock. Buy an OTM put (strike A) and sell an OTM call (strike B). Same expiration. The call premium helps pay for the put. Can be established for net-zero cost (zero-cost collar).

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - stock price) - net debit or + net credit.
- **Max Loss**: (Stock price - strike A) + net debit or - net credit.
- **Breakeven**: Stock price - net credit received (credit collar) or + net debit paid (debit collar).

### When to Use
Want to protect a profitable stock position at low cost. Willing to cap upside. Typically after a significant run-up.

### Greeks Impact
- **Delta**: Positive but reduced by short call. Range-bound position.
- **Theta**: Somewhat neutral. Short call theta offsets long put theta.
- **Vega**: Somewhat neutral. Call vega and put vega partially offset.

### Time Decay Effect
Neutral overall. Short call benefits from decay; long put suffers. In a credit collar, net theta slightly positive.

### Implied Volatility Impact
Neutral overall. Rise in IV benefits put but hurts call. Fall in IV helps call but hurts put.

### Trade-off
Pros: Low-cost/zero-cost protection, defined risk range. Cons: Capped upside, must hold stock, complex to manage multiple legs.

---

## Strategy: Fig Leaf / Leveraged Covered Call (Play 9)
### Outlook & Definition
Mildly bullish. Buy a deep ITM LEAPS call (strike A, delta ≥ .80) as stock substitute. Sell short-term OTM calls (strike B, 30-45 DTE) against it. Acts like a covered call without buying the stock.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Premium from short calls + LEAPS appreciation. Cannot be precisely calculated at initiation.
- **Max Loss**: Debit paid to establish (limited).
- **Breakeven**: Requires pricing model — multiple variables.

### When to Use
Mildly bullish on an expensive stock. Want leverage instead of buying 100 shares. Generate income via repeated short-call sales.

### Greeks Impact
- **Delta**: Long LEAPS delta (.80+) minus short call delta. Net delta positive but lower than stock.
- **Theta**: Friend. Short-term call decays faster than LEAPS call.
- **Vega**: Somewhat neutral. Short-term vega < LEAPS vega, but offsetting.

### Time Decay Effect
Positive overall. The short front-month call decays faster than the long LEAPS call. You can sell multiple rounds of short calls.

### Implied Volatility Impact
Somewhat neutral. IV increase raises both long LEAPS (good) and short call (bad). IV decrease does the opposite.

### Trade-off
Pros: Leverage over expensive stock, income generation, less capital than buying stock. Cons: LEAPS eventually expire, assignment risk on short call without owning stock, complex management.
