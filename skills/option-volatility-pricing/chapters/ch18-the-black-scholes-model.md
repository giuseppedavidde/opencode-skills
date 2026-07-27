# Chapter 18: The Black-Scholes Model

## Core Idea
The Black-Scholes model is the foundational option pricing framework that values European options using five inputs: exercise price, time, underlying price, interest rate, and volatility. It works by separating the option value into two components — the expected value of the stock above the exercise price (if exercised) and the expected payment of the exercise price — both adjusted for a lognormal distribution and discounted to present value.

## Frameworks Introduced
- **Black-Scholes Differential Equation**: Expresses how changes in stock price (S) and time (t) affect call value (C), incorporating delta, gamma, theta, volatility, and interest rate effects
- **Model Inputs (5)**: Exercise price, time to expiration, underlying price, interest rate, volatility — volatility being the only unobservable input
- **Riskless Hedge Concept**: For every option position, there is a theoretically equivalent underlying position such that, for small price changes, the two move identically; this hedge ratio (delta) is the cornerstone of the model
- **Standard Normal Distribution Functions**: n(x) = standard normal density curve (bell shape, μ=0, σ=1, total area=1); N(x) = cumulative normal distribution (area under curve from −∞ to x). N(+∞)=1.00, N(0)=0.50, N(x)=1−N(−x)
- **Black-Scholes Formula Variations**: Original (non-dividend stocks), Black model (futures), Garman-Kohlhagen (foreign currencies) — all differ only in forward price calculation and settlement adjustments

## Key Concepts
- **d1 and d2**: d1 adjusts S/X for interest (forward shift) and lognormal skew (σ²t/2 shift), then divides by `σ√t` to express in standard deviations. d2 = d1 − `σ√t`. N(d1) = delta; N(d2) = risk-neutral probability of exercise
- **Two-Question Decomposition**:
  1. What is the average value of all stock above the exercise price at expiration? → S × e^(rt) × N(d1)
  2. What is the likelihood of paying the exercise price? → N(d2)
  Expected call value = S × e^(rt) × N(d1) − X × N(d2). Discount to present: C = S × N(d1) − X × e^(−rt) × N(d2)
- **The b (Cost-of-Carry) Adjustment**: Generalized model uses parameter b: stock options b=r, futures options b=0, currency options b=r−rf. Affects d1/d2 calculation and all sensitivities
- **At-the-Forward Approximation**: For an exactly at-the-forward option: Expected Value ≈ 0.004 × F × σ × √t. Theoretical Value ≈ 0.004 × F × σ × √t / (1+r×t). The "40% rule": expected value ≈ 40% of one standard deviation
- **Delta = N(d1)**: Always greater than N(d2) for calls; at-the-forward call delta > 50 (lognormal skew). Put delta = N(d1) − 1 (or call delta − 1 for futures-type settlement)
- **Delta-Neutral Straddle**: Forward price must be below exercise price for exact delta neutrality: `S = X × e^[−(r+σ²/2)×t]`
- **Theta Components (3)**: (1) Volatility decay — always dominant, same sign for calls and puts; (2) Spot-to-forward drift (b−r term); (3) Present value discounting. Under futures-type settlement, only component (1) remains ("driftless theta")
- **Maximum Gamma, Theta, Vega Locations**: Not exactly at-the-money. At r=0: max gamma/theta above strike, max vega below strike. At r>0: critical prices shift
- **Vega Decay Anomaly**: For stock options with high interest rates, vega can *decline* as time to expiration increases — counterintuitive but caused by the option moving away from at-the-forward

## Anti-patterns
- **Treating 0.00399 as exact**: The 40% rule approximation diverges at high volatility and long time — vega of ATM options actually declines slightly with increasing σ
- **Assuming N(d1) = probability of exercise**: The true risk-neutral probability is N(d2); N(d1) is the delta, which is always larger
- **Using the wrong model variant**: Stock, futures, and currency options require different cost-of-carry (b) parameters; using wrong b produces incorrect values
- **Ignoring that vega can decrease with time**: Long-dated stock options can have lower vega than shorter-dated ones if interest rates are high — this violates the usual intuition
- **Relying on models near expiration**: As t→0, discrete time increments fail to capture continuous passage of time — many traders abandon model values very close to expiration
- **Confusing model precision with accuracy**: The model is mathematically precise but its assumptions (constant vol, continuous trading, frictionless markets) limit real-world accuracy

## Key Takeaways
1. The Black-Scholes model answers two questions: average stock value above strike, and probability of paying the strike — their difference is the expected option value
2. All Black-Scholes variants differ only in forward price calculation and settlement procedure — the core probability framework is identical
3. Delta = N(d1) is always greater than the probability of finishing ITM = N(d2); this reflects the fact that when the option is ITM, it's "more ITM" on average
4. The 40% rule provides a powerful mental approximation: ATM option value ≈ 0.4 × F × σ × √t (undiscounted)
5. A model is a candle in a dark room — it reveals general layout but distorts details. Use models for insight, but never confuse them with reality
