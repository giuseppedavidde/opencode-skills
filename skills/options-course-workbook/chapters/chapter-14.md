# Chapter 14: Margin and Risk

## Core Idea
**Margin is leverage** — using borrowed money to control larger positions. While it amplifies returns, it also amplifies losses. Options cannot be bought on margin (100% cash), but stocks and spreads involve margin calculations.

## Frameworks Introduced
- **Cash Account**: 100% of trade cost required upfront
- **Margin Account**: Put up a percentage (typically 50% for stocks); broker lends the rest
- **Margin Call**: If equity drops below maintenance level, deposit more funds or positions are **liquidated**
- **Margin Requirement**: Amount needed to secure a position. Higher perceived risk = higher margin. Naked options have the highest requirements
- **Leverage**: Using less capital to control a larger position. Options inherently provide leverage (e.g., control $2,000 of stock for $200)

## Key Concepts
- **Marginable securities**: Most exchange-traded stocks qualify. **Options are not marginable** (except spreads)
- Combining long and short options + underlying **decreases** margin requirements (hedged positions are less risky)
- Each point of option premium = $100 (multiplier of 100)
- Naked call selling: unlimited risk, highest margin. Naked put selling: risk limited to stock falling to zero
- **Margin debt**: Total borrowed from brokers. A market indicator — high margin debt can signal excess

## Key Takeaways
1. Buying options is a **cash trade** — no margin required beyond premium
2. Combining options with underlying stock **reduces** margin vs naked positions
3. A margin call requiring additional funds — if unmet, positions are liquidated
4. Leverage is a double-edged sword: 25% drop = 50% loss in a 50% margin account
