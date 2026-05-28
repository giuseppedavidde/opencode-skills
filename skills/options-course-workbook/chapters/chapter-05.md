# Chapter 5: Introducing Vertical Spreads

## Core Idea
Vertical spreads simultaneously buy and sell two options of the same type (calls or puts) with different strikes but the **same expiration**. They limit both risk and reward. Two categories: **debit spreads** (pay to enter) and **credit spreads** (receive premium to enter).

## Frameworks Introduced
- **Bull Call Spread**: Buy lower strike call + sell higher strike call. Debit. Max risk = net debit. Max profit = width − net debit. Breakeven = lower strike + net debit
- **Bull Put Spread**: Sell higher strike put + buy lower strike put. Credit. Max reward = net credit. Max risk = width − net credit. Breakeven = higher strike − net credit
- **Bear Call Spread**: Sell lower strike call + buy higher strike call. Credit. Max reward = net credit. Max risk = width − net credit. Breakeven = lower strike + net credit
- **Bear Put Spread**: Buy higher strike put + sell lower strike put. Debit. Max reward = width − net debit. Max risk = net debit. Breakeven = higher strike − net debit

## Key Concepts
- **Debit spreads**: Bull call and bear put. Use options with **90+ days** to expiration. Better reward-to-risk ratios
- **Credit spreads**: Bear call and bull put. Use options with **<45 days** to expiration. Higher probability of success but risk often exceeds reward
- Always use **limit orders** to get the price you want; slippage from bid-ask spreads kills profitability
- Legging in (entering each side separately) adds execution risk

## Key Takeaways
1. Vertical spreads are **great beginner strategies** — limited risk, limited reward, easy to manage
2. Paper trade spreads before using real capital
3. A bull put spread profits in sideways or higher markets due to time decay
4. Aim for maximum profit to be at least **2x maximum risk** on debit spreads
