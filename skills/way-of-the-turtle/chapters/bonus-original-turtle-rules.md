# Bonus Chapter: Original Turtle Trading Rules

## Core Idea
The original Turtle trading system was a complete mechanical system covering every decision: what markets to trade, how much to buy, when to enter and exit, and how to execute orders tactically. Its completeness—leaving no decision to discretion—was a major factor in the Turtles' success.

## Frameworks Introduced
- **Complete Trading System Architecture**: A system is complete only when it specifies (1) Markets, (2) Position Sizing, (3) Entries, (4) Stops, (5) Exits, and (6) Tactics. Most "trading systems" sold commercially address only entries.
- **N-Based Position Sizing Algorithm**: Position size = Account Equity × Risk% / (N × Dollars per Point). N is in price points; N × Dollars per Point is the dollar volatility of one contract. This normalizes dollar volatility across all markets so that a 1N move in any instrument has equal portfolio impact.
- **Unit Pyramiding System**: Positions are built in up to 4 units, each added at ½N intervals beyond the initial entry. This layers into trends rather than committing full size at breakout.

## Key Concepts
- **Markets Traded**: All liquid U.S. futures except grains (position limit constraints) and meats (floor corruption): 30Y and 10Y Treasuries, currencies (CHF, DEM, GBP, FRF, JPY, CAD), metals (gold, silver, copper), energies (crude, heating oil, gasoline), softs (coffee, cocoa, sugar, cotton), S&P 500, eurodollars, T-bills.
- **N Calculation**: N = 20-day exponential moving average of true range. True range = max(H-L, H-PDC, PDC-L). Initial N is a 20-day simple average of true range; subsequent values use N = (19 × PDN + TR) / 20.
- **Position Sizing Formula**: Unit size = 1% of account / (N × dollars per point). Heating oil example: the contract is 42,000 gallons and the price is in dollars per gallon, so 1 point ($1.00/gallon) = **$42,000**. With N = 0.0141, dollar volatility = 0.0141 × $42,000 = $592.20. For a $1M account: unit = $10,000 / $592.20 = 16.9 → **16 contracts** (rounded down). With $420 per point the same formula gives 1,688 contracts: a 100× error. Always check the contract size and the price unit.
- **Entry Rules (System 1 & System 2)**: System 1 enters on a 20-day breakout. **System 1 filter**: skip the signal if the last 20-day breakout in that market (taken or not, long or short) would have been a winning trade; if the skipped move continues, enter at the 55-day breakout (failsafe) so a major trend is not missed. System 2 enters on a 55-day breakout and takes every signal. The original rules have **no** 50/300-day moving-average filter: Curtis Faith tests that trend filter later in *Way of the Turtle* (ch. 5 and ch. 9) as an addition.
- **Pyramiding**: Add a unit each ½N move in the trade's favor, up to 4 total units maximum. Stop-loss for the entire position is placed at 2N from the most recent entry price.
- **Stop Rules**: Initial stop at 2N from entry. If the market moves favorably by ½N, tighten stop to 2N from the new (higher for longs, lower for shorts) entry price. This locks in partial gains while allowing room for trend continuation.
- **Exit Rules**: System 1 exits on a 10-day breakout against the position (low for longs, high for shorts). System 2 exits on a 20-day breakout against the position.
- **Tactical Execution**: Use limit orders, not market orders. For large positions, enter during quiet periods. Vary entry timing slightly across Turtles to obfuscate aggregate positioning from floor traders.

## Anti-patterns
- **Trading Incomplete Systems**: Using entry signals without predetermined stops, exits, and position sizing rules. This delegates critical decisions to emotion during live trading when fear and greed are strongest.
- **Ignoring Liquidity Constraints**: Trading markets with insufficient volume for position size. Rich Dennis excluded markets where Turtle-sized orders would cause excessive market impact.
- **Inconsistent Market Participation**: Choosing to trade a market sometimes but not others. Turtles could opt out of a market entirely but could not trade it inconsistently—partial participation destroys the statistical basis of diversification.

## Key Takeaways
1. A complete trading system must specify all six components: markets, sizing, entries, stops, exits, tactics.
2. N-based position sizing ensures a 1N move in gold equals a 1N move in bonds in dollar terms.
3. Pyramiding (up to 4 units at ½N intervals) layers into trends rather than committing full size at once.
4. System 1 (20-day breakout with the skip-after-winner filter, 10-day exit) and System 2 (55-day breakout, 20-day exit) provide dual time-horizon exposure.
5. Mechanical systems succeed because they remove discretion—fear and greed cannot override predetermined rules.
