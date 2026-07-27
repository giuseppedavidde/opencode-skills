# Chapter 9: Risk Measurement II

## Core Idea
The Greeks are not static—they change as market conditions change, creating higher-order risks. Understanding how delta, gamma, theta, and vega evolve with price, time, and volatility is essential for managing positions through changing regimes. Today's small risk can become tomorrow's large risk.

## Frameworks Introduced
- **Delta Dynamics**: As volatility rises, all deltas converge toward 50 (calls) or -50 (puts). As time passes or volatility falls, deltas diverge toward 0 (OTM) or 100/-100 (ITM). An at-the-money option's delta is relatively stable around 50.
- **Vanna (Δ/∂σ)**: Sensitivity of delta to changes in volatility. Greatest for deltas around 20 and 80 (calls) or -20 and -80 (puts); near zero for deltas of 50/-50. Options with these deltas will shift most rapidly toward 50 as volatility rises.
- **Charm (Δ/∂t)**: Sensitivity of delta to the passage of time, also called "delta decay." Similar profile to vanna—greatest for intermediate deltas. As expiration nears, charm accelerates dramatically.
- **Theta Characteristics**: Theta is greatest for at-the-money options and declines as options move ITM or OTM. Late in an option's life, at-the-money theta accelerates toward infinity at expiration, while ITM/OTM theta slows.
- **Theta-Volatility Relationship**: For at-the-money options, theta is directly proportional to volatility—double the vol, double the theta.

## Key Concepts
- **Time and Volatility Equivalence**: More time ≈ higher volatility in terms of effect on delta. If you cannot determine the effect of changing one, consider the effect of changing the other.
- **Implied Delta**: Using implied volatility to calculate delta means delta changes as the market's volatility assessment changes, even if the underlying price is unchanged.
- **Gamma Dynamics**: Gamma interacts with theta and vega; a position with +gamma has -theta and typically +vega. These relationships are structural, not coincidental.
- **Higher Exercise Price Theta**: For equally OTM calls and puts, the call (higher exercise price) carries more time premium and therefore decays faster, due to the lognormal distribution assumption.

## Anti-patterns
- Assuming a delta-neutral position will remain delta-neutral—even without price movement, passage of time and volatility changes alter delta.
- Using a single "best guess" volatility for delta calculations without acknowledging that the true future volatility is unknown.
- Ignoring the acceleration of theta near expiration for at-the-money options—a seemingly stable position can hemorrhage value in the final days.
- Focusing on individual Greek values without understanding their interdependencies (vanna, charm, gamma-theta relationship).

## Key Takeaways
1. Risk measures are dynamic; a delta-neutral position today may not be delta-neutral tomorrow.
2. Delta converges toward 50/-50 with higher volatility or more time; diverges toward 0/100 with lower volatility or less time.
3. Vanna and charm are the second-order sensitivities—understanding them is critical for large or long-dated positions.
4. At-the-money theta is proportional to volatility and accelerates near expiration.
5. Implied delta (using implied volatility) changes with market sentiment even if the underlying is static.
