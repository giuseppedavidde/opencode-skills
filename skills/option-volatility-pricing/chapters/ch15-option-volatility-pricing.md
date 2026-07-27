# Chapter 15: Option Arbitrage

## Core Idea
Option arbitrage exploits mispricing between options and their underlying instruments using synthetic relationships. The cornerstone is put-call parity: for European options with the same strike and expiration, the difference between call and put prices must equal the present value of the difference between the forward price and exercise price. Violations of this relationship create risk-free (in theory) profit opportunities.

## Frameworks Introduced
- **Put-Call Parity (General Form)**: C - P = (F - X) / (1 + r × t). For futures options with futures-type settlement (r = 0): C - P = F - X. For stock options: the difference equals the present value of (forward price minus exercise price).
- **Conversion (Synthetic Short + Long Underlying)**: Sell call, buy put, buy underlying. Profits when the synthetic is overpriced relative to the underlying.
- **Reverse Conversion / Reversal**: Buy call, sell put, sell underlying. Profits when the synthetic is underpriced relative to the underlying.
- **Combo (Combination)**: A long call + short put (synthetic long underlying) or short call + long put (synthetic short underlying). The combo value C - P is the central pricing relationship.

## Key Concepts
- **Arbitrage-Free Condition**: All credits and debits from the conversion/reversal must balance. Any deviation creates an arbitrage opportunity that market forces will quickly eliminate.
- **Settlement Procedure Impact**: Futures-type settlement (common outside North America) simplifies parity to C - P = F - X because no money changes hands. Stock-type settlement (common in North America) requires discounting.
- **Locked Futures Markets**: When a futures market hits its daily price limit and cannot trade, options can be used synthetically to establish the desired futures position. A trader wanting to buy a locked-up futures contract can sell a put and buy a call at the same strike.
- **Arbitrage Risk**: Even mathematically perfect arbitrage carries real-world risks—execution slippage, inability to borrow/lend at the theoretical rate, early exercise of American options, and counterparty risk.

## Anti-patterns
- Assuming put-call parity holds exactly in real time—bid-ask spreads, transaction costs, and execution timing create practical deviations.
- Ignoring settlement procedure differences when calculating parity across different exchanges (US vs. European futures options).
- Attempting arbitrage without accounting for the cost of carry (borrowing costs for stock, margin requirements for futures).
- Assuming European-style exercise for American options when calculating parity—early exercise can invalidate the relationship.

## Key Takeaways
1. Put-call parity is the central arbitrage relationship: C - P must equal the present value of (F - X).
2. Conversions and reversals are the primary arbitrage strategies, exploiting synthetic mispricing.
3. Settlement type (stock-type vs. futures-type) determines whether interest rates enter the parity calculation.
4. Locked futures markets can be accessed synthetically using options.
5. Real-world frictions (costs, execution, borrowing constraints) mean theoretical arbitrage rarely delivers risk-free profits in practice.
