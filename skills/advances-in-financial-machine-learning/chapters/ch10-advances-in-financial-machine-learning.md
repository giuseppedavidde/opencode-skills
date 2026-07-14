# Chapter 10: Bet Sizing

## Core Idea
Even with a profitable signal, **bet sizing determines success** — poker players know that sizing edge is as important as finding edge. The chapter converts a classifier's predicted probabilities into position sizes via a concave function, then averages concurrent active bets, discretizes the result to suppress overtrading, and finally links size to a **limit price** so the order rewards patience.

## Frameworks Introduced
- **Strategy-independent sizing**: reserve cash for future opportunities; size bets so that no single position can wipe out the book.
- **Bet sizing from predicted probabilities**: `f[p, I, d] = concave(p)` — map a probability p∈[0,1] to a bet size, calibrated against the number of concurrent longs/shorts and a divergence d between actual and average bet.
- **Averaging active bets**: when several overlapping bets are live, use the average signal across them — reduces excess turnover.
- **Size discretization**: `m' = round(m / d)·d`, d ∈ (0,1] — snap bet sizes to a grid; prevents small unnecessary overtrading (Figure 10.2).
- **Dynamic bet sizes & limit prices**: for order size ω, compute a breakeven limit price and a sigmoid-based price schedule consistent with the size calibration; for ω>1 the function flips concave-to-convex.

## Key Concepts
- Bet sizing separates alpha from its monetization: a correct {−1,1} meta-label with bad sizing still loses.
- A small edge repeated with over-sized bets → ruin risk; concavity caps exposure near full confidence.
- Discretization trades a small amount of optimality for a large reduction in turnover/commissions/slippage.
- Limit-price schedule: market pays you to provide liquidity. A larger order → more patient (more aggressive rebate) limit price.
- Concave-to-convex vs convex-to-concave (Figure 10.3): f[x]=sgn[x]|x|² flips at the tipping point — choose the branch consistent with the divergence between p and the average signal.

## Anti-patterns
- Bet sizing proportional to probability without concavity (linear sizing → fat-tailed ruin).
- Ignoring the count of concurrent active bets and sizing each in isolation.
- Trading every fractional size — turnover and costs eat the edge.
- Using only market orders when limit orders would capture spread/rebate.
- Sizing without considering the strategy's maximum capacity and cash reserve for future bets.

## Key Takeaways
1. Size as a concave function of the model's certainty, then average and discretize.
2. Discretization with d∈(0.1,0.2] crushes turnover at negligible optimality cost.
3. Tie size to a limit-price schedule — liquidity provision monetizes the edge.
4. Reserve capacity for future opportunities; full-all-in sizing is a ruin recipe.
5. Bet sizing is the bridge between a meta-label classifier (Ch.3) and live execution (Ch.11).