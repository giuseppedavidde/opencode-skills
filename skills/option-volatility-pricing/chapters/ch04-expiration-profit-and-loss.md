# Chapter 4: Expiration Profit and Loss

## Core Idea
At expiration, an option's value is exactly its intrinsic value — zero if out-of-the-money, or the difference between underlying price and exercise price if in-the-money. Parity graphs (hockey-stick diagrams) and expiration P&L graphs are the fundamental visual tools for understanding option position characteristics.

## Frameworks Introduced
- **Parity Graphs**: Visual representation of option position value at expiration as a function of underlying price; display intrinsic value only
- **Expiration P&L Graphs**: Parity graphs shifted by the debit (purchase) or credit (sale) of the option position; show actual profit/loss
- **Slope Analysis**: `ΔValue / ΔUnderlying Price` — determines how position value changes with underlying movement across exercise price intervals
- **Breakeven Calculation**: For simple positions: `Exercise Price ± Option Premium`; for complex positions: use slope analysis from a known P&L point

## Key Concepts
- **Four Basic Parity Graphs**:
  - Long call: zero below strike, +1 slope above strike (limited risk, unlimited profit)
  - Short call: zero below strike, −1 slope above strike (limited profit, unlimited risk)
  - Long put: −1 slope below strike, zero above strike (limited risk, unlimited profit to zero)
  - Short put: +1 slope below strike, zero above strike (limited profit, unlimited risk to zero)
- **Hockey-Stick Diagrams**: The characteristic bend at the exercise price, reflecting the insurance feature of options
- **Combining Positions**: Total slope at any underlying price = sum of individual contract slopes. Construct by determining slopes below lowest strike, above highest strike, and between all intermediate strikes
- **Long Call + Long Put (Straddle)**: Gains value in both directions away from exercise price — sensitive to magnitude, not direction
- **Long Call + Short Put (Synthetic Long Underlying)**: Total slope = +1 everywhere; identical to owning the underlying
- **Complex Positions**: Use slope tables across exercise price intervals; determine P&L at one point (usually an exercise price), then propagate using slopes
- **Unlimited Risk/Reward Asymmetry**: Buyers have limited risk/unlimited profit; sellers have limited profit/unlimited risk — but probability determines whether this is truly advantageous

## Anti-patterns
- **Focusing only on risk/reward asymmetry**: New traders see "limited risk, unlimited profit" and only buy options, ignoring that sellers win far more frequently due to probability
- **Ignoring probability**: The hockey-stick shape shows what *can* happen, not what is *likely* to happen
- **Misidentifying position slopes**: Especially with puts, new traders often reverse buy/sell sign conventions; always verify slopes against parity graph logic
- **Assuming complex positions are unpredictable**: All positions, regardless of complexity, can be decomposed into slope segments; the procedure is always the same
- **Neglecting breakeven calculations**: Multiple breakevens exist for multi-leg positions; failing to calculate all of them leads to blind spots

## Key Takeaways
1. Parity graphs show value at expiration; P&L graphs add trade prices to show actual profit/loss — both are essential diagnostic tools
2. The slope of any position is the sum of individual contract slopes; this holds for any combination of options and underlying
3. A long call + short put at the same strike = synthetic long underlying (always +1 slope); this is the foundation of put-call parity
4. Breakeven prices are calculated by finding where P&L crosses zero, using known P&L at a reference point and the slope in that interval
5. The "limited risk" of option buying is meaningful only when considered alongside probability — sellers win on frequency, buyers win on magnitude
