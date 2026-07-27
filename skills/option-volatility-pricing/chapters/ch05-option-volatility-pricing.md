# Chapter 5: Theoretical Pricing Models

## Core Idea
Option pricing models determine fair value by computing the discounted expected payoff of an option, given a probability distribution of underlying prices at expiration. The Black-Scholes model, introduced in 1973, remains the most widely used framework, requiring five inputs: exercise price, time to expiration, underlying price, interest rate, and volatility. A model is a candle in a dark room—imperfect but invaluable.

## Frameworks Introduced
- **Expected Value Framework**: Multiply each possible option payoff at expiration by its probability and sum to get expected value; discount to present value for the theoretical price.
- **Four-Step Model Development**: (1) Propose possible expiration prices, (2) assign probabilities ensuring the expected value equals the forward price (arbitrage-free condition), (3) calculate expected option payoff, (4) discount by the interest rate.
- **Black-Scholes Model Inputs**: Exercise price, time remaining, underlying price, interest rate, and volatility. Volatility is the only unobservable input—it represents the "speed" of the market.
- **Riskless Hedge Concept**: For every option position, there exists an equivalent underlying position such that, for small price changes, gains and losses offset. The hedge ratio determines the correct proportion.

## Key Concepts
- **Direction vs. Speed**: Option traders must be right about both market direction AND speed; a favorable directional move insufficiently fast still results in loss due to time decay.
- **Forward Price as Expected Value**: In arbitrage-free markets, the forward price is the expected future value of the underlying, anchoring the probability distribution.
- **Theoretical Value vs. Market Price**: The goal is to identify mispriced options—buying below theoretical value or selling above it—to capture a theoretical edge.
- **Model Limitations**: All models require assumptions (continuous trading, constant volatility, frictionless markets). A trader must understand both model strengths and weaknesses.

## Anti-patterns
- Relying on model-generated values without understanding the assumptions behind them ("garbage in, garbage out").
- Trading based on expected value alone without accounting for risk—the model assumes "long run" outcomes; short-term variance can bankrupt a trader before the long run arrives.
- Ignoring the speed component: buying options purely for leveraged directional exposure without assessing whether the move will occur fast enough.
- Treating the model as infallible—the candle analogy reminds us that models illuminate but also distort.

## Key Takeaways
1. Theoretical value = present value of the probability-weighted expected option payoff at expiration.
2. The forward price of the underlying is the anchor point for any option pricing model.
3. Black-Scholes requires five inputs; volatility is the only one that must be estimated.
4. The riskless hedge is central: an option is a substitute for a dynamic position in the underlying.
5. A model is a tool for gaining an edge, not a guarantee of profit—risk management is equally important.
