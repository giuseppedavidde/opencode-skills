# Combination & Ratio Spreads

## Strategy: Long Combination / Synthetic Long Stock (Play 18)
### Outlook & Definition
Bullish. Buy a call at strike A and sell a put at strike A. Same expiration. Risk/reward nearly identical to owning 100 shares — but with leverage (less capital tied up).

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Theoretically unlimited (stock rises).
- **Max Loss**: Substantial — Strike A + debit or - credit (stock to zero).
- **Breakeven**: Strike A + net debit or - net credit.

### When to Use
Strongly bullish. Want leverage like long stock but with less capital. Understand short put risk. Usually closed before expiration.

### Greeks Impact
- **Delta**: ~1.0 (like owning stock). Call delta + (-put delta) ≈ 1.
- **Theta**: Somewhat neutral. Long call theta (bad) offset by short put theta (good).
- **Vega**: Somewhat neutral. Offsetting legs.

### Time Decay Effect
Neutral overall. Theta of long call and short put partially cancel.

### Implied Volatility Impact
Neutral overall. Vega of both legs cancels.

### Trade-off
Pros: Stock-like exposure with leverage, less capital than buying stock. Cons: Short put risk, dividends affect pricing, margin requirements.

---

## Strategy: Short Combination / Synthetic Short Stock (Play 19)
### Outlook & Definition
Bearish. Sell a call and buy a put at same strike A. Same expiration. Mimics short stock risk/reward with less margin.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Substantial — Strike A + credit or - debit (stock to zero).
- **Max Loss**: Theoretically unlimited (stock rises).
- **Breakeven**: Strike A + credit or - debit.

### When to Use
Bearish without wanting to short stock directly. Avoid paying dividends (no short stock dividend liability). Less margin than short stock.

### Greeks Impact
- **Delta**: ~ -1.0 (like short stock).
- **Theta**: Somewhat neutral.
- **Vega**: Somewhat neutral.

### Time Decay Effect
Neutral. Call and put theta partially offset.

### Implied Volatility Impact
Neutral overall.

### Trade-off
Pros: Less margin than short stock, no dividend liability, stock-like short exposure. Cons: Unlimited upside risk, complex.

---

## Strategy: Front Spread w/ Calls (Play 20)
### Outlook & Definition
Slightly bullish — want stock to rise to strike B and stop. Buy 1 call at A, sell 2 calls at B. Same expiration. Net credit or small debit.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - A) + net credit (or minus debit).
- **Max Loss**: Unlimited if stock goes way up. Limited to debit if stock goes down.
- **Breakeven**: Depends on credit/debit. Multiple BEs.

### When to Use
Slightly bullish but expect rally to stall at B. **All-Stars only** due to uncovered call. Consider index options.

### Greeks Impact
- **Delta**: Positive but limited. Starts positive, turns negative past B.
- **Theta**: Friend. Two short calls decay faster than one long.
- **Vega**: Want IV decreases. Hurts 2 short calls more than 1 long.

### Time Decay Effect
Positive overall (2 short vs 1 long). Benefits from time passing.

### Implied Volatility Impact
Negative overall. Want IV to fall.

### Trade-off
Pros: Can be established for credit, time decay works. Cons: Unlimited risk above B, All-Stars only.

---

## Strategy: Front Spread w/ Puts (Play 21)
### Outlook & Definition
Slightly bearish — want stock to fall to strike A and stop. Sell 2 puts at A, buy 1 put at B. Same expiration.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: (Strike B - A) + net credit (or minus debit).
- **Max Loss**: Substantial (stock to zero). Limited on upside.
- **Breakeven**: Depends on credit/debit.

### When to Use
Slightly bearish but expect decline to halt at A. All-Stars only.

### Greeks Impact
- **Delta**: Negative but limited. Reversal below A.
- **Theta**: Friend. Two short puts decay faster.
- **Vega**: Want IV decrease.

### Time Decay Effect
Positive. Short puts dominate.

### Implied Volatility Impact
Negative. Want IV contraction.

### Trade-off
Pros: Credit potential, time decay helps. Cons: Substantial downside risk.

---

## Strategy: Back Spread w/ Calls (Play 22)
### Outlook & Definition
Extremely bullish on volatile stock. Sell 1 call at A, buy 2 calls at B. Same expiration. Net credit preferred.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Theoretically unlimited (stock above B).
- **Max Loss**: Limited — (Strike B - A) + debit if established for debit.
- **Breakeven**: If net credit, two BEs: A + credit and B + max risk.

### When to Use
Expect massive upside breakout. Precede major news events (FDA, legal, patent). **Seasoned Veterans and higher**.

### Greeks Impact
- **Delta**: Turns from neutral to strongly positive above B.
- **Gamma**: Positive. Benefits from explosive moves.
- **Theta**: Enemy if stock sits around B.
- **Vega**: Positive. Want IV to rise.

### Time Decay Effect
Negative if stock doesn't move. Risk if stock stays near B.

### Implied Volatility Impact
Positive. IV expansion amplifies profit if stock moves.

### Trade-off
Pros: Unlimited upside, cheap to establish, credit possible. Cons: Loses if stock only moves moderately.

---

## Strategy: Back Spread w/ Puts (Play 23)
### Outlook & Definition
Extremely bearish on volatile stock. Sell 1 put at B, buy 2 puts at A. Same expiration.

### Max Profit / Max Loss / Breakeven
- **Max Profit**: Substantial — stock to zero.
- **Max Loss**: Limited — (Strike B - A) minus credit.
- **Breakeven**: Depends on net credit/debit.

### When to Use
Expect massive downside crash. Seasoned Veterans and higher.

### Greeks Impact
- **Delta**: Negative. Accelerates below A.
- **Gamma**: Positive on downside.
- **Theta**: Enemy if stock sits.
- **Vega**: Positive. Need IV expansion.

### Time Decay Effect
Negative if stock doesn't move.

### Implied Volatility Impact
Positive. IV spike during crash multiplies profit.

### Trade-off
Pros: Substantial profit potential on crash, limited loss. Cons: Needs huge move to profit.
