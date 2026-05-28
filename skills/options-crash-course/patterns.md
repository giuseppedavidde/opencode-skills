# Options Trading Patterns (Beginner-Friendly)

## 1. Covered Call (Buy/Write)
**When to use**: Moderate bearish/bullish market. You already own the stock and want to generate extra income.
**How**: Buy 100 shares of underlying stock. Sell 1 call option against those shares at a strike price above your purchase price.
**Trade-offs**: Caps upside (you must sell if stock exceeds strike). Provides downside cushion equal to premium collected. Max loss = stock value - premium (if stock goes to zero).
**Best for**: turning stagnant holdings into income-generating positions.

---

## 2. Married Put
**When to use**: Bullish but cautious. You want upside exposure with a defined floor.
**How**: Buy 100 shares of underlying stock. Buy 1 put option at a strike price that represents your max acceptable loss.
**Trade-offs**: Put premium is an upfront cost. Acts as insurance — if stock drops, put guarantees you can sell at strike price. If stock rises, you lose only the put premium.
**Best for**: protecting a new position against unexpected drops.

---

## 3. Bull Call Spread
**When to use**: Moderately bullish. You expect price to rise but not explosively.
**How**: Buy 1 call at lower strike (ATM or slightly OTM). Sell 1 call at higher strike (same expiry, same underlying).
**Trade-offs**: Lower cost than buying a naked call. Profit capped at (higher strike - lower strike - net debit). Max loss = net debit paid.
**Best for**: bullish plays with defined risk and capped upside.

---

## 4. Bear Put Spread
**When to use**: Moderately bearish. You expect a decline but not a crash.
**How**: Buy 1 put at higher strike. Sell 1 put at lower strike (same expiry, same underlying).
**Trade-offs**: Lower cost than a naked put. Profit capped at (higher strike - lower strike - net debit). Max loss = net debit paid.
**Best for**: bearish bets with controlled risk.

---

## 5. Protective Collar
**When to use**: Bullish/bearish but primarily protecting existing gains on a long position.
**How**: Buy 1 OTM put (protection). Sell 1 OTM call (funds the put). Both same expiry, same underlying.
**Trade-offs**: Low or zero net cost (call premium offsets put cost). Limits upside (shares called away if price exceeds call strike). Locks in profit range.
**Best for**: protecting a winning position without paying cash for insurance.

---

## 6. Long Straddle
**When to use**: Expect a major move in either direction (earnings, news event) but don't know which way.
**How**: Buy 1 ATM call + Buy 1 ATM put (same strike, same expiry).
**Trade-offs**: Expensive (two premiums). Profit requires a large move past breakeven in EITHER direction. Theta decay works against you fast.
**Best for**: binary events where you're sure volatility will spike.

---

## 7. Long Strangle
**When to use**: Same as long straddle but cheaper. Expect big move, direction unknown.
**How**: Buy 1 OTM call + Buy 1 OTM put (different strikes, same expiry).
**Trade-offs**: Cheaper than straddle. Needs an even larger move to profit (both strikes must be breached). Lower premium cost.
**Best for**: high-volatility expectations on a budget.

---

## 8. Short Straddle
**When to use**: Expect low volatility / range-bound market. Price will NOT move much.
**How**: Sell 1 ATM call + Sell 1 ATM put (same strike, same expiry).
**Trade-offs**: Collects premium upfront (time decay works FOR you). Unlimited loss potential (if price moves hard in either direction). Requires active management.
**Best for**: experienced traders in low-volatility markets.

---

## 9. Butterfly Spread
**When to use**: Neutral outlook. Expect price to stay near a specific level.
**How**: Buy 1 OTM call, Sell 2 ATM calls, Buy 1 ITM call (or same structure with puts). Three strike prices.
**Trade-offs**: Low cost, defined risk. Max profit at middle strike. Profit erodes quickly outside narrow range.
**Best for**: range-bound markets with low volatility.

---

## 10. Iron Condor
**When to use**: Neutral to slightly bearish/bullish. Expect price to stay within a range.
**How**: Sell 1 OTM put spread + Sell 1 OTM call spread (four options total).
**Trade-offs**: Collects credit upfront. Defined risk on both sides. Best with index options (lower volatility). Narrow profit zone.
**Best for**: collecting premium in low-volatility environments.

---

## 11. Repair Strategy
**When to use**: You have an unrealized loss on a long call and want to lower breakeven.
**How**: Roll the position into a bull call spread (sell a higher call, keep lower call) or convert to a butterfly.
**Trade-offs**: Lowers breakeven but caps upside. Adds small additional risk. Not viable if loss exceeds 70%.
**Best for**: rescuing underwater positions with time remaining before expiry.
