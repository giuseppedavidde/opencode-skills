# Chapter 8: Dynamic Hedging

## Core Idea
Dynamic hedging is the process of maintaining a delta-neutral position by periodically adjusting the hedge ratio as the underlying price changes and time passes. It transforms a single option bet into a series of small bets, all at favorable theoretical odds, allowing the trader to capture the difference between an option's price and its theoretical value.

## Frameworks Introduced
- **Delta-Neutral Hedging**: Establishing an initial position where the option delta is offset by an opposing underlying position (e.g., buy 100 calls with Δ=50, sell 50 underlying contracts)
- **Dynamic Rebalancing**: At regular intervals or when delta exceeds a threshold, recalculate delta and trade the underlying to return to neutrality
- **Replication Principle**: Through dynamic hedging, an option position can be replicated; the cost of replication equals the sum of all adjustment cash flows, whose present value equals the option's theoretical value
- **Breakeven Volatility**: The implied volatility at which total P&L from the hedge exactly equals zero — identical to the option's implied volatility at trade entry

## Key Concepts
- **Adjustment P&L dominates**: In the Natenberg example, buying 100 June 100 calls at 5.00 (theoretical 5.89) produced: original hedge loss −422.50, but adjustments profit +467.55, net +89.21 (vs. expected +89.00)
- **Buy low, sell high mechanically**: Positive delta from price rise → sell underlying; negative delta from price fall → buy underlying; the hedging process forces profitable trades
- **Five P&L Components**: (1) Original hedge P&L, (2) Adjustment P&L, (3) Interest on option position, (4) Interest on stock/futures position, (5) Interest on adjustment cash flows + dividends
- **Futures Options**: No initial cash outlay but variation credits/debits generate interest; total interest on variation replaces stock interest components
- **Gamma as the profit engine**: Option curvature (gamma) creates mismatch between option's changing delta and fixed delta of underlying; each adjustment captures this unhedged amount
- **Time decay vs. adjustments**: The hedge is a race between option time decay and adjustment cash flow; the theoretical edge determines which wins
- **Implied volatility reevaluation**: If implied vol rises to target after trade entry, position can be closed immediately for full theoretical profit — no need to hold to expiration
- **Adverse volatility moves**: Implied volatility may move against the position even when realized vol moves favorably; discipline is required to hold through temporary mark-to-market losses

## Anti-patterns
- **Assuming frictionless markets**: Real-world violations — short sale restrictions, lock limits, interest rate spreads, transaction costs — all reduce or eliminate theoretical edge
- **Over-adjusting**: Continuous rehedging is impossible; transaction costs eat profits. Adjust too frequently and costs exceed edge
- **Under-adjusting**: Too few adjustments increase short-term variance; actual results diverge significantly from predicted results (good or bad luck dominates)
- **Ignoring short stock rebates**: Full interest is not received on short sale proceeds; forward price calculations must use the short rate, not the long rate
- **Treating one hedge as definitive**: A single dynamic hedge may lose money even with a positive edge — probability works over many iterations, not individual trades
- **Hedging puts backwards**: Buy puts → buy underlying (same direction); sell puts → sell underlying. New traders often reverse this, creating double exposure instead of a hedge

## Key Takeaways
1. Dynamic hedging converts a theoretical edge into realized profit by forcing the trader to buy low and sell high through delta-neutral rebalancing
2. `Option value ≈ Σ(small adjustment profits)` — the sum of all gamma scalps approximates the option's time premium
3. Breakeven volatility = implied volatility at trade price; above this, the hedge profits; below, it loses
4. Retail vs. professional: both have same expected return, but professionals adjust more frequently (lower transaction costs), reducing variance
5. Implied volatility reevaluation is the fastest path to profit — if the market reprices to your vol estimate, close immediately
