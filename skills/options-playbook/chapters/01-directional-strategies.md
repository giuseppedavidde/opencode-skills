# Directional Strategies: Single-Option Plays

## Strategy: Long Call (Play 1)
### Outlook & Definition
Bullish. Buy a call to gain the right to buy stock at strike price A. Alternative to buying stock outright with limited downside (premium only). Leverage over greater number of shares.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Theoretically unlimited (stock to infinity).
- **Max Loss**: Premium paid for the call.
- **Breakeven**: Strike A + premium paid.

### When to Use
Strongly bullish with defined risk. Want leverage without full stock cost. Prefer ITM calls (delta ≥ .80) for closer stock-like behavior.

### Greeks Impact
- **Delta**: Positive (0 to 1). ITM calls have higher delta.
- **Gamma**: Highest for ATM near-term options. Accelerates delta changes.
- **Theta**: Enemy. Time decay erodes long option value daily.
- **Vega**: Want IV to rise. Increases option value.

### Time Decay Effect
Negative. Theta works against you every day. Decay accelerates as expiration nears. Avoid short-term OTM calls.

### Implied Volatility Impact
Positive. Higher IV increases option price. IV expansion reflects greater potential for price swing.

### Trade-off
Pros: Limited risk, unlimited upside, leverage. Cons: Time decay works against you, wrong direction = total loss, must be right on timing.

---

## Strategy: Long Put (Play 2)
### Outlook & Definition
Bearish. Buy a put to gain the right to sell stock at strike price A. Alternative to short stock with limited risk. Also used as portfolio hedge (protective put).

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Substantial, limited to strike A minus premium (stock to zero).
- **Max Loss**: Premium paid for the put.
- **Breakeven**: Strike A - premium paid.

### When to Use
Bearish view with defined risk. Hedge existing long positions. Prefer ITM puts (delta ≤ -.80) for better tracking.

### Greeks Impact
- **Delta**: Negative (0 to -1). ITM puts approach -1.
- **Gamma**: High for ATM near-term puts. Rapid delta acceleration.
- **Theta**: Enemy. Time decay erodes put value.
- **Vega**: Want IV to rise. Increases put value.

### Time Decay Effect
Negative. Accelerates near expiration. OTM short-term puts are high-risk lottery tickets.

### Implied Volatility Impact
Positive. IV increase raises put prices. IV spike during market fear benefits put buyers.

### Trade-off
Pros: Limited risk, profit from downside, hedge protection. Cons: Time decay, timing requirement, premium cost.

---

## Strategy: Short Call / Naked Call (Play 3)
### Outlook & Definition
Bearish to neutral. Sell a call, obligating you to sell stock at strike A if assigned. Collect premium upfront. **All-Stars only** — unlimited risk.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Premium received.
- **Max Loss**: Theoretically unlimited (stock rises indefinitely).
- **Breakeven**: Strike A + premium received.

### When to Use
Bearish-neutral outlook. High probability of small profit. Sell OTM calls ~1 standard deviation out. Consider index options (less volatile).

### Greeks Impact
- **Delta**: Negative (short call has negative delta). Benefits from stock decline.
- **Gamma**: Enemy if stock rises toward strike. Accelerates losses.
- **Theta**: Friend. Time decay erodes short option value daily.
- **Vega**: Enemy. Want IV to decrease. IV rise increases option value (bad for short).

### Time Decay Effect
Strongly positive. Maximum benefit from decay. Sell 30-45 day options for optimal theta.

### Implied Volatility Impact
Negative. IV decrease = option price falls = good. IV spike = dangerous.

### Trade-off
Pros: High probability of profit, collects premium, time decay works for you. Cons: Unlimited risk, margin required, must monitor constantly.

---

## Strategy: Short Put / Naked Put (Play 4)
### Outlook & Definition
Bullish to neutral. Sell a put, obligating you to buy stock at strike A if assigned. Collect premium. **All-Stars only** — substantial risk.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Premium received.
- **Max Loss**: Substantial — strike A minus premium (stock to zero).
- **Breakeven**: Strike A - premium received.

### When to Use
Bullish-neutral outlook. Sell ~1 standard deviation OTM. High probability trade.

### Greeks Impact
- **Delta**: Positive (short put has positive delta). Benefits from stock rise.
- **Gamma**: Enemy if stock falls toward strike.
- **Theta**: Friend. Time decay erodes short put.
- **Vega**: Enemy. Want IV to decrease.

### Time Decay Effect
Strongly positive. Sell 30-45 day OTM puts for max theta benefit.

### Implied Volatility Impact
Negative. IV contraction reduces put price. Avoid selling before events when IV is elevated and poised to drop.

### Trade-off
Pros: High win rate, collects premium, time decay works for you. Cons: Substantial downside risk, margin required.

---

## Strategy: Cash-Secured Put (Play 5)
### Outlook & Definition
Slightly bearish short-term, bullish long-term. Sell an OTM put with cash reserved to buy the stock if assigned. A limit order alternative — you profit if wrong AND if right.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Premium received (if put expires OTM).
- **Max Loss**: Strike A minus premium (if stock goes to zero).
- **Breakeven**: Strike A - premium received.

### When to Use
Want to buy a stock below current price. Have cash available. Willing to hold the stock long-term. Collect premium while waiting.

### Greeks Impact
- **Delta**: Positive. Benefits from stock staying above strike or rising.
- **Theta**: Friend. Time decay helps you.
- **Vega**: Want IV to decrease. Lower IV reduces put value.

### Time Decay Effect
Positive. You want the put to expire worthless. 30-45 day timeframe balances premium vs. time.

### Implied Volatility Impact
Negative. High IV gives better premium. IV contraction hurts premium but helps your short position.

### Trade-off
Pros: Buy stock below market, collect premium even if wrong, lower cost basis. Cons: Must have cash available, opportunity cost if stock rallies, stock can continue falling.
