# Chapter 19: Binomial Option Pricing

## Core Idea
The binomial model (Cox-Ross-Rubinstein) provides an intuitive, accessible alternative to Black-Scholes that can price American options (with early exercise). By building a tree of possible underlying prices and working backward from expiration, the model computes option values step by step without requiring advanced calculus. It converges to the Black-Scholes value as the number of steps increases.

## Frameworks Introduced
- **Risk-Neutral Valuation**: In a risk-neutral world, the expected return of the underlying equals the risk-free rate. Risk-neutral probabilities p and (1-p) are derived such that the discounted expected value equals the current price: p = (1 + r×t - d)/(u - d).
- **One-Period Binomial Tree**: The underlying can move up to Su or down to Sd. Option value = present value of [p × payoff_up + (1-p) × payoff_down].
- **Multi-Period Expansion**: Using n periods, with u and d as multiplicative inverses (d = 1/u). Terminal prices are Su^j d^(n-j). The number of paths to each terminal price follows the binomial distribution: n!/(j!(n-j)!).
- **Backward Induction**: Fill terminal nodes with intrinsic values, then work backward using the one-period formula at each node to compute earlier option values.

## Key Concepts
- **Binomial Notation**: Si,j represents the price at time i (steps from start) and level j (steps up from bottom). Ci,j and Pi,j represent corresponding option values.
- **u and d Determination**: The up/down multipliers are calibrated to the underlying's volatility and time step: u = e^(σ√(t/n)), d = 1/u.
- **American Option Pricing**: At each node, compare the value from holding (the backward-induction value) with the value from early exercise (intrinsic value). Take the maximum—this handles the early exercise feature naturally.
- **Greeks from Binomial Trees**: Delta, gamma, and theta can be approximated by comparing option values at adjacent nodes in the tree.
- **Convergence to Black-Scholes**: As n → ∞, the binomial value approaches the Black-Scholes value for European options.

## Anti-patterns
- Using too few periods—coarse binomial trees produce inaccurate option values, especially for longer-dated or volatile options.
- Applying European-style backward induction to American options without checking for early exercise at each node.
- Ignoring dividend adjustments—stock dividends must be incorporated into the forward price calculation at each step.
- Assuming u and d are arbitrary—they must be calibrated to volatility and time step for the model to be valid.

## Key Takeaways
1. The binomial model prices options through backward induction on a discrete price tree.
2. Risk-neutral probabilities ensure the tree is arbitrage-free and consistent with the forward price.
3. Multi-period trees produce a binomial distribution of terminal prices that approximates the lognormal distribution.
4. American options are naturally priced by comparing continuation value vs. exercise value at each node.
5. The binomial model converges to Black-Scholes for European options as periods increase, but uniquely handles early exercise.
