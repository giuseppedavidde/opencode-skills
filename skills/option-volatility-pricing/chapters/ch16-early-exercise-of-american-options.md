# Chapter 16: Early Exercise of American Options

## Core Idea
American options carry the right of early exercise, which has value only when there is an advantage to holding the underlying position rather than the option — typically from dividends (stock) or interest earned on intrinsic value (futures). Understanding arbitrage boundaries, early exercise criteria, and optimal timing is essential for pricing American options correctly and avoiding leaving money on the table.

## Frameworks Introduced
- **Arbitrage Boundaries**: Lower boundary = minimum price without arbitrage opportunity; Upper boundary = maximum price. American options ≥ European boundaries, bounded by intrinsic value
- **Call/Put Value Decomposition**: Call value = intrinsic value + volatility value + interest value − dividend value. Put value = intrinsic value + volatility value − interest value + dividend value
- **Early Exercise Criteria (Stock Calls)**: Exercise when `Dividend value > volatility value + interest value`. Optimal day: day before ex-dividend date — on no other day is exercise optimal for calls
- **Early Exercise Criteria (Stock Puts)**: Exercise when `Interest value > volatility value + dividend value`. Blackout period exists: don't exercise within (dividend ÷ daily interest) days before dividend payment
- **Futures Options (Stock-Type Settlement)**: Exercise when `Interest value > volatility value`; requires theta of companion option < daily interest earned

## Key Concepts
- **American Option Lower Boundaries**:
  - Call: `max[0, S−X, (F−X)/(1+r×t)]`
  - Put: `max[0, X−S, (X−F)/(1+r×t)]`
- **European Calls Can Trade Below Parity**: With high dividends, a European call can be worth less than intrinsic value. American calls have early exercise value to capture this
- **Stock Call Exercise Timing**: Only the day before ex-dividend. Exercising any other day gives up volatility and interest value without receiving dividend — strictly suboptimal
- **Stock Put Blackout Period**: `Dividend ÷ (X × daily_rate)` days before ex-dividend, no exercise because interest earned < dividend lost
- **Futures Option Exercise**: Only when options are stock-type settled; no advantage under futures-type settlement (no cash flow from either side)
- **Immediate Early Exercise**: Must satisfy criteria over the next day, not just over option life. Daily interest > daily theta (companion OTM option)
- **Sell vs. Exercise**: If the option trades above intrinsic value (liquid market), selling the option and buying the underlying dominates exercising directly
- **Protective Value of Not Exercising**: Exercising a 90 call is equivalent to selling the 90 put. If the 90 put is cheap (low IV), buy it simultaneously to maintain downside protection at a net credit
- **Short Stock Impact**: Lower interest rate on short stock makes call exercise more likely (reduces interest penalty), put exercise less likely (reduces interest benefit)

## Anti-patterns
- **Exercising calls on any day other than day before ex-dividend**: There is never a reason to exercise a call on a non-dividend day — it always destroys value
- **Exercising puts during the blackout period**: Interest earned cannot offset the lost dividend within the blackout window
- **Assuming American = European value**: For futures-type settlement, American and European values are identical. For stock options with dividends, American > European
- **Ignoring implied volatility in exercise decisions**: If IV is low and the companion option is cheap, buy it when exercising to maintain protective value
- **Overlooking that lower boundary can exceed intrinsic value**: European calls can have lower boundaries above zero even when out of the money if the forward is high enough
- **Not comparing sell vs. exercise**: When option bid > intrinsic value, selling is better than exercising — capture the extra time premium

## Key Takeaways
1. Early exercise is only valuable when carrying the underlying is superior to carrying the option — dividends and interest are the drivers
2. Stock calls: only exercise the day before ex-dividend. Stock puts: never exercise within the blackout period
3. Futures options subject to futures-type settlement have zero early exercise value — American = European
4. The lower arbitrage boundary for American options is at least intrinsic value, but may be higher if the European boundary exceeds intrinsic value
5. Exercising an option = selling the companion OTM option at a synthetic price; always compare this price with the actual market to find the best execution
