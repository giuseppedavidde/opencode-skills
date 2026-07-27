# Chapter 7: Risk Measurement I

## Core Idea
Option traders face risks from multiple dimensions—underlying price direction, time decay, volatility changes, and interest rates. The "Greeks" (delta, gamma, theta, vega, rho) quantify each risk dimension, enabling traders to construct, hedge, and manage positions with precision. Understanding these sensitivities is the foundation of professional options trading.

## Frameworks Introduced
- **The Five Primary Greeks**:
  - **Delta (Δ)**: Rate of change in option value per unit change in underlying price. Calls: 0 to 100; Puts: -100 to 0. The underlying always has a delta of 100.
  - **Gamma (Γ)**: Rate of change in delta per unit change in underlying price. Always positive for long options, negative for short. Measures curvature.
  - **Theta (Θ)**: Rate of time decay—how much value the option loses per day as expiration approaches. Long options have negative theta.
  - **Vega**: Sensitivity to a 1% change in volatility. Long options have positive vega; volatility increases benefit option holders.
  - **Rho (ρ)**: Sensitivity to interest rate changes. Least important of the Greeks for most short-term strategies.
- **Four Delta Interpretations**: (1) Rate of change, (2) Hedge ratio (100/delta = contracts needed to hedge), (3) Equivalent underlying position (each 100 deltas ≈ one underlying contract), (4) Approximate probability of finishing in-the-money.
- **Gamma as Curvature**: Gamma tells you how fast delta changes. A high gamma means directional risk can reverse rapidly—critical for position sizing and risk management.

## Key Concepts
- **Delta-Neutral Hedging**: Total portfolio delta of zero means no directional bias. This is the starting point for volatility-based strategies.
- **Interest Rate Effects**: For stock options, rising rates increase call values and decrease put values (forward price effect dominates). For futures options with futures-type settlement, interest rates are irrelevant.
- **Short Stock Complication**: Carrying a short stock position changes the effective interest rate, altering option values. Natenberg's rule: whenever possible, avoid short stock positions.
- **Gamma-Delta Interaction**: A positive gamma position gains deltas as the market rises and loses them as it falls—acting as a natural hedge.

## Anti-patterns
- Interpreting delta as a static number—it changes continuously due to gamma, time, and volatility changes.
- Ignoring the difference between stock-type and futures-type settlement when assessing interest rate risk.
- Using delta as the sole risk metric while ignoring gamma, theta, and vega exposure—all Greeks must be considered together.

## Key Takeaways
1. The five Greeks (delta, gamma, theta, vega, rho) provide a complete first-order risk decomposition.
2. Delta has four valid interpretations; choose the one that matches your trading approach.
3. Gamma, theta, and vega are always aligned: long options = +gamma, -theta, +vega; short options = the opposite.
4. Delta-neutral positions eliminate directional bias but retain exposure to volatility, time, and curvature.
5. Avoid short stock positions when possible—they complicate interest rate calculations and hedging.
