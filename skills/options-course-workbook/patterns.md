# Strategy Application Patterns

## Directional Bullish

### Long Call
**When to use**: Strongly bullish, high conviction, stock expected to rise significantly. Low IV environment so you're not overpaying.
**How**: Buy ATM or slightly OTM call with 90+ DTE. Risk = premium paid. Breakeven = strike + premium.
**Trade-offs**: Theta decay works against you. Must be right on direction AND timing. Needs >90 DTE to mitigate time decay.
**Variants**: Deep ITM call (acts like stock with less capital). LEAPS call (long-term bullish, less theta per day).

### Bull Call Spread
**When to use**: Moderately bullish, want defined risk/reward. Expect price to reach but not exceed the short strike.
**How**: Buy lower-strike call + sell higher-strike call (same expiration). Net debit.
**Trade-offs**: Limited upside compared to long call. Lower cost = better risk control. Prefer strikes 2× reward-to-risk ratio.
**Best for**: Earnings plays where you expect a moderate move.

### Bull Put Spread (Credit)
**When to use**: Bullish or neutral. Expect stock to stay above the short put strike. Higher probability of success.
**How**: Sell higher-strike put + buy lower-strike put. Net credit. Use <45 DTE.
**Trade-offs**: Risk > reward (but wins more often). Defined risk. Time decay works for you.

## Directional Bearish

### Long Put
**When to use**: Strongly bearish, high conviction. Low IV.
**How**: Buy ATM or slightly OTM put with 90+ DTE. Breakeven = strike − premium.
**Trade-offs**: Theta works against you. Stock can only fall to zero (limited max gain). Needs downside catalyst.

### Bear Put Spread
**When to use**: Moderately bearish. Defined risk.
**How**: Buy higher-strike put + sell lower-strike put. Net debit.
**Trade-offs**: Limited profit but lower cost than straight put. Risk defined upfront.

### Bear Call Spread (Credit)
**When to use**: Bearish or neutral. Expect stock to stay below short call strike.
**How**: Sell lower-strike call + buy higher-strike call. Net credit. <45 DTE.
**Trade-offs**: Higher probability of success. Time decay works for you. Risk > reward per trade.

## Non-Directional / Volatility

### Long Straddle
**When to use**: Expecting a large move but unsure of direction. Low IV (so options are cheap) with catalyst ahead (earnings, FDA, economic report).
**How**: Buy ATM call + ATM put (same strike, same expiration). Net debit.
**Breakevens**: Strike ± net premium (combined).
**Trade-offs**: Expensive (two premiums). Theta is double-negative. Needs move > total premium to profit. U-shaped risk = unlimited upside, limited downside.

### Long Strangle
**When to use**: Same as straddle but cheaper. Expect VERY large move.
**How**: Buy OTM call + OTM put (different strikes). Lower cost but needs larger move.
**Trade-offs**: Wider breakevens = less likely to profit. Better cost structure. Max loss = total premium.
**Selection**: Strike distance determines cost vs probability. Wide strangle = cheap, needs big move.

### Long Synthetic Straddle
**When to use**: Want adjustability that fixed straddles don't offer. Long-term volatility play.
**How**: (A) Buy 100 shares + buy 2 ATM puts. (B) Short 100 shares + buy 2 ATM calls.
**Trade-offs**: Adjustable — can sell/buy shares or options to rebalance delta. More complex position management.

### Short Straddle / Strangle
**When to use**: **NOT RECOMMENDED** (unlimited risk). Theoretical use: extremely high IV, expecting compression, and willing to accept unlimited risk.
**How**: Sell ATM call + put (straddle) or OTM call + put (strangle). Net credit.
**Trade-offs**: Limited profit (credit collected). Unlimited risk. One bad move wipes account.

## Range-Bound / Theta

### Long Butterfly
**When to use**: Stock is range-bound between identified support/resistance. Low volatility. Expect price to land exactly at middle strike at expiration.
**How**: Buy 1 ITM + sell 2 ATM + buy 1 OTM (calls or puts). Net debit.
**Risk**: Net debit paid. **Reward**: Width − net debit.
**Trade-offs**: Very specific profit zone. Small max loss but also limited max profit. Low cost of entry.

### Long Condor
**When to use**: Range-bound but want wider profit zone than butterfly. Less precision needed.
**How**: Buy 1 ITM + sell 1 ITM-body + sell 1 OTM-body + buy 1 OTM (4 strikes).
**Trade-offs**: Wider profit zone = lower max profit. More strikes = more commissions.

### Long Iron Butterfly
**When to use**: Range-bound, want credit instead of debit. Neutral outlook.
**How**: Bear call spread + bull put spread (same strikes for the short legs).
**Trade-offs**: Net credit at entry. Defined risk on both sides. Maximum profit = credit received.

### Calendar Spread
**When to use**: Neutral direction, want to profit from time decay acceleration in short-term option.
**How**: Buy long-term option + sell short-term option (same strike). Net debit.
**Trade-offs**: Profits if stock stays near strike. Theta positive after short leg decays. Can be rolled.

### Collar
**When to use**: Own stock, want downside protection, willing to cap upside. Zero-cost if balanced.
**How**: OTM put (protective) + OTM call (covered call). Net zero or small credit/debit.
**Trade-offs**: Upside capped at call strike. Protected below put strike. Ideal for long-term shareholders.

## Advanced / Ratio

### Call Ratio Backspread
**When to use**: Anticipating explosive upside move. Low IV environment with catalyst.
**How**: Sell 1 lower-strike call + buy 2+ higher-strike calls. Net credit preferred.
**Trade-offs**: Limited risk (debit or max loss zone). Unlimited upside reward. Adjustable if stock moves.

### Put Ratio Backspread
**When to use**: Anticipating explosive downside move. Low IV.
**How**: Sell 1 higher-strike put + buy 2+ lower-strike puts.
**Trade-offs**: Limited risk. Large downside profit (but limited as stock can only hit zero).

### Ratio Call Spread
**When to use**: Bearish on moderately volatile stock. Want wide profit zone. **WARNING**: Unlimited upside risk.
**How**: Buy 1 lower-strike call + sell 2+ higher-strike calls. Net credit.
**Trade-offs**: Wide profit zone. Unlimited risk above breakeven. Not for beginners.

### Ratio Put Spread
**When to use**: Bullish on moderately volatile stock. Wide profit zone.
**How**: Buy 1 higher-strike put + sell 2+ lower-strike puts. Net credit.
**Trade-offs**: Wide profit zone. Risk if stock drops sharply (to zero). Not for beginners.

## Trade Management Patterns

- **High IV + Bearish** → Bear call spread or long put
- **Low IV + Bullish** → Bull call spread or long call
- **Low IV + Neutral** → Calendar spread or butterfly
- **High IV + Neutral** → Iron condor or short strangle (hedged)
- **Earnings play, unsure direction** → Long straddle/strangle (if IV low), or double calendar
- **Protect stock position** → Collar or protective put
- **Generate income on stock** → Covered call (if neutral-bullish)

## Common Mistakes
1. Buying options with IV too high (volatility crush kills profit even if direction is right)
2. Holding long options past 30 DTE (theta accelerates)
3. Selling naked options without understanding unlimited risk
4. Not checking the risk graph before entry
5. Overtrading / using too many strategies without mastery
6. Ignoring liquidity — trading options with wide bid-ask spreads
7. Letting emotions override exit plan
