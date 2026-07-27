# Chapter 2: Forward Pricing

## Core Idea
The fair price of a forward contract is determined by the costs and benefits of buying the underlying asset now versus on a future date. These costs and benefits are not eliminated in a forward contract — they are simply deferred, and must be reflected in the forward price.

## Frameworks Introduced
- **Forward Pricing Formula**: `F = Current Cash Price + Costs of Buying Now − Benefits of Buying Now`
- **Cash-and-Carry Arbitrage**: Buying in the cash market, selling in the futures market, and carrying the position to maturity to profit from mispricing
- **Basis Analysis**: `Basis = Cash Price − Forward Price` — normally negative (costs outweigh benefits), but can flip positive under certain conditions (convenience yield)
- **Implied Values**: Solving for an unknown input (implied spot price, implied interest rate, implied dividend) by assuming a fairly priced contract

## Key Concepts
- **Physical Commodities**: Forward price = `C × (1 + r × t) + (s × t) + (i × t)` where C = commodity price, r = interest rate, s = storage costs, i = insurance costs
- **Contango vs. Backwardation**: Contango = long-term futures at premium to short-term (normal); backwardation = futures at discount to cash (convenience yield exceeds costs)
- **Convenience Yield**: The benefit of having immediate access to a physical commodity; difficult to quantify but inferred from price relationships
- **Stock Forwards**: `F = [S × (1 + r × t)] − D` where D = total dividends; interest on dividends usually ignored for simplicity
- **Bond/Note Forwards**: Treated similarly to stock forwards, with coupon payments replacing dividends
- **Foreign Currency Forwards**: Must account for both domestic interest rate (cost) and foreign interest rate (benefit); `F = S × (1 + rd × t) / (1 + rf × t)`
- **Futures Options**: Forward price for a futures contract is simply the futures price itself — no additional calculation needed
- **Dividend Process**: Declared date → Record date → Ex-dividend date (2 business days before record) → Payable date
- **Short Sales and Rebates**: Short sellers receive only a portion of the interest on proceeds; the difference between long rate (r_l) and short rate (r_s) equals borrowing costs (r_bc)
- **Short-Stock Squeeze**: Difficulty or impossibility of borrowing stock for short sales

## Anti-patterns
- **Ignoring borrowing costs**: Assuming the same interest rate for long and short positions; short rebates reduce arbitrage profit windows
- **Treating carry trades as true arbitrage**: Carry trades (borrow low-rate currency, invest in high-rate) have significant interest rate and exchange rate risk
- **Miscalculating dividend dates**: When dividend dates fall near expiration, small errors in date estimation significantly alter derivative values
- **Using fixed rates blindly**: Assuming fixed-rate borrowing when most traders borrow at variable rates exposes the position to interest rate risk
- **Overlooking transaction costs**: Transportation, insurance, and storage costs can eliminate apparent arbitrage profits

## Key Takeaways
1. A fair forward price incorporates all deferred costs and benefits of ownership — interest, storage, insurance, dividends, and convenience yield
2. Cash-and-carry arbitrage enforces forward pricing relationships; deviations create profit opportunities (buy cheap, sell expensive, carry to maturity)
3. Implied values allow traders to back-solve for unknown market expectations (implied rates, dividends) from observable forward prices
4. Short sale constraints — borrowing costs, availability, exchange restrictions — create pricing bands where no arbitrage is possible
5. For option traders, the forward price of the underlying is the central reference point because all option values depend on it, not the spot price
