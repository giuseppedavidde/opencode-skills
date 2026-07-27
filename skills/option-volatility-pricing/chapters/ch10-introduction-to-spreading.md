# Chapter 10: Introduction to Spreading

## Core Idea
Spreading — taking opposing positions in related instruments — is the primary method by which option traders control risk while maintaining profit potential. Unlike directional speculation, spreading allows traders to profit from relative mispricing rather than outright price movement, protecting against the short-term effects of "bad luck" inherent in probability-based trading.

## Frameworks Introduced
- **Spread Definition**: A strategy involving opposing positions in different but related instruments where values change at different rates under changing market conditions
- **Intramarket Spreads**: Same underlying, different maturities (e.g., calendar spreads in futures); based on cost-of-carry relationships
- **Intermarket Spreads**: Different but related instruments (e.g., crude oil vs. products, gold vs. silver, 10-year vs. 30-year Treasuries); based on historical price relationships
- **Ratio Strategies**: Unequal numbers of contracts to account for price-level differences between instruments (e.g., 3:1 commodity A vs. B spread)
- **Crack/Crush Spreads**: Multi-leg commodity processing spreads (3:2:1 crack = 3 crude : 2 gasoline : 1 heating oil)

## Key Concepts
- **Arbitrage-Based Spreads**: Cash-and-carry — buy physical, sell overpriced forward, lock in profit; profit equals exact amount of mispricing regardless of price fluctuations
- **Futures Calendar Spreads**: Buy near month, sell far month (or reverse); value driven by cost-of-carry changes (interest rates, storage, insurance)
- **Yield Curve Spreads**: NOB spread (notes over bonds) — sell the spread if long rates expected to rise faster than short rates
- **Ratio Relationship Spreads**: Identify historical price ratio (e.g., Commodity B = 3 × Commodity A); buy/sell when ratio deviates from historical norm
- **Execution Sequence**: Execute the more difficult (less liquid) leg first; completing the spread with the easier leg reduces execution risk
- **Spread Pricing**: Market makers often quote tighter bid-ask for the complete spread than the sum of individual legs — always trade the spread as one transaction when possible
- **Piecemeal Risk**: Trading legs separately exposes the trader to adverse price moves until the spread is complete

## Key Concepts — Option Spreads
- **Beyond Directional Spreads**: Option spreads can hedge gamma (volatility of underlying), vega (implied volatility changes), theta (time decay), or rho (interest rates)
- **Static vs. Dynamic Spreads**: Static spreads are carried to expiration without adjustment; dynamic spreads (like Chapter 8 hedges) require periodic rebalancing
- **Volatility as Mis pricing Metric**: Compare implied volatilities rather than dollar prices; an option at 8.00 with 26% IV may be less overpriced than one at 6.75 with 28% IV
- **Margin for Error**: Spreading increases the breakeven volatility range, allowing larger position sizes. A trader comfortable with 5 vol points error can increase size 10× if spread increases breakeven to 10 points
- **Casino Analogy**: 38 players betting $1,000 each on all 38 roulette numbers = perfect spread, guaranteed $2,000 profit. Same edge (5%) as one $38,000 bet, but zero variance

## Anti-patterns
- **Assuming fixed relationships**: Cost-of-carry (interest, storage) can change after spread initiation, widening/narrowing spreads unexpectedly
- **Treating correlation as causation**: Historical price ratios may break down; intermarket spreads carry greater uncertainty
- **Ignoring execution risk**: Piecemeal leg execution can leave positions naked; always execute difficult legs first
- **Over-leveraging**: A small theoretical edge does not justify unlimited size — always consider margin for error in volatility/directional estimates
- **Confusing spread safety with zero risk**: Spreading reduces, but does not eliminate, risk; changes in correlations, rates, and market structure can create losses
- **Settling for sum-of-legs pricing**: Individual leg execution at posted bid-ask destroys edge; always seek a single spread market

## Key Takeaways
1. Most successful option traders are spread traders — spreading maintains probability edge while reducing short-term variance
2. Option spreads can be designed around gamma, vega, theta, or rho — each addresses a different risk dimension
3. Compare mispricing in volatility terms (IV), not dollar terms; the at-the-money option is always most sensitive in total points to vol changes
4. The casino's ideal: spread bets around the table to guarantee profit regardless of which number hits; option traders spread across strikes/expirations for the same reason
5. Margin for error in volatility estimates determines position sizing — larger spreads allow more aggressive sizing at equivalent risk
