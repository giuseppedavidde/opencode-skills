# Chapter 23: Models and the Real World

## Core Idea
Theoretical pricing models are built on six key assumptions that rarely hold in practice: frictionless markets, constant interest rates, constant volatility, continuous trading, volatility independent of price, and lognormally distributed returns. A trader who understands these limitations can adapt strategies to real-world conditions; one who ignores them risks catastrophic failure. The model is an approximation—useful but imperfect.

## Frameworks Introduced
- **The Six Core Assumptions**:
  1. **Frictionless Markets**: No transaction costs, unrestricted buying/selling, unlimited borrowing/lending at the same rate, no taxes.
  2. **Constant Interest Rates**: One rate applies to all cash flows over the option's life.
  3. **Constant Volatility**: Price changes of all magnitudes are evenly distributed over time.
  4. **Continuous Trading**: No gaps in underlying prices; hedging can be adjusted instantly.
  5. **Volatility Independent of Price**: Underlying price level does not affect volatility (contradicted by the leverage effect).
  6. **Lognormal Distribution at Expiration**: Percent price changes are normally distributed over small intervals.
- **Real-World Violations**:
  - Locked markets (daily price limits) prevent trading when hedging is needed most.
  - Short-sale restrictions (e.g., uptick rules) inflate put prices and distort parity.
  - Differential borrowing/lending rates mean model-calculated fair values are imprecise for real traders.
  - Margin requirements can force liquidation before a theoretically profitable position reaches expiration.

## Key Concepts
- **Volatility Path Dependency**: Two periods with identical close-to-close volatility (28%) but different intra-period patterns (rising vs. falling) produce radically different P&L for dynamic hedgers, yet the model treats them identically.
- **Gap Risk**: When prices jump discontinuously (e.g., overnight gaps, news events), continuous hedging is impossible. The model's assumption of smooth price transitions breaks down.
- **Interest Rate Sensitivity (Rho)**: Most significant for long-dated, deep ITM stock options. Short-term options are relatively insensitive to rate changes—rho is typically the least important Greek.
- **Model as "Candle in a Dark Room"**: The model illuminates but distorts. Traders must use it while acknowledging its limitations, especially as position size and complexity increase.

## Anti-patterns
- Blindly trusting model outputs without stress-testing against assumption violations.
- Ignoring liquidity constraints—a theoretically optimal hedge may be impossible to execute in a locked or illiquid market.
- Assuming continuous rebalancing is feasible—transaction costs and gap risk make continuous hedging a theoretical construct only.
- Neglecting the impact of margin calls on position viability—the model assumes you can always hold to expiration.
- Trading based on implied volatility without recognizing that the model's constant-volatility assumption is known to be false.

## Key Takeaways
1. Models are approximations; six major assumptions are routinely violated in real markets.
2. The frictionless-market assumption is the most practically problematic—costs, constraints, and funding differences matter.
3. Volatility is not constant; the path of volatility changes affects dynamic hedging P&L even when terminal volatility is the same.
4. Gap risk destroys the continuous-hedging premise—real markets gap, and hedges slip.
5. Use models as tools, not as truth—increase skepticism as position size and complexity grow.
