# Chapter 13: Risk Considerations

## Core Idea
Choosing an option strategy requires balancing theoretical edge against multiple risk dimensions. Equalizing theoretical edge across candidate strategies reveals their true comparative risk profiles. Risk analysis extends beyond current conditions—a trader must ask how risks change as market conditions evolve.

## Frameworks Introduced
- **Five Risk Categories Summarized**: (1) Delta risk—directional exposure; (2) Gamma risk—curvature/sensitivity to large moves; (3) Theta risk—time decay pressure; (4) Vega risk—sensitivity to volatility estimation error; (5) Rho risk—interest rate exposure (least important).
- **Theoretical Edge Normalization**: Comparing strategies fairly requires adjusting position sizes so theoretical edge is equal; only then can risk profiles be compared apples-to-apples.
- **Breakeven Volatility Analysis**: The implied volatility at which a spread's theoretical profit becomes zero. Higher breakeven volatility = greater margin for error in volatility estimation.
- **Scenario Analysis via Graphs**: Plotting theoretical P&L across a range of underlying prices and volatilities reveals divergence points where strategies behave differently under stress.

## Key Concepts
- **Volume of Analysis**: Three strategies with identical theoretical edge (~6.00) can have vastly different risk profiles—unlimited downside (straddle), unlimited upside only (ratio spread), or fully bounded (butterfly).
- **Volatility Misestimation Impact**: If realized volatility exceeds the estimate, negative vega positions suffer. The vega, like gamma, changes as volatility changes—static vega analysis is insufficient.
- **Strategy Selection Logic**: The "best" spread depends on what the trader fears most—a large down move (choose ratio spread), large moves in either direction (choose butterfly), or is willing to accept the highest risk/reward (choose straddle).
- **Practical Risk Management**: Considerations include margin requirements, position liquidity, adjustment costs, and the ability to maintain the position through adverse conditions.

## Anti-patterns
- Selecting a strategy based solely on theoretical edge without equalizing for risk—a high-edge strategy may carry disproportionate risk.
- Treating vega as constant—as volatility rises, ITM/OTM option vegas increase while ATM vega remains stable, altering the total position vega.
- Ignoring the gamma-theta tradeoff: high theta collection (positive theta) always comes with negative gamma, which means accelerating losses in a large move.
- Focusing on current risk measures without projecting how they change under stress scenarios.

## Key Takeaways
1. Theoretical edge alone is an insufficient criterion; strategies must be compared on a risk-equalized basis.
2. Breakeven volatility indicates the volatility estimation error a position can absorb before becoming unprofitable.
3. Risk measures are dynamic—a spread's behavior in a 2-sigma move may differ radically from its behavior in a 5-sigma move.
4. The best strategy depends on which specific risks (direction, magnitude, volatility) the trader is most concerned about.
5. Practical constraints (margin, liquidity, transaction costs) must be factored into any strategy evaluation.
