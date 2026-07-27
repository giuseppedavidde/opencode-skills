# Chapter 1: Financial Contracts

## Core Idea
Financial derivatives—forwards, futures, and options—are contracts whose values are derived from underlying assets. They enable market participants to manage risk, speculate on price movements, or transfer obligations across time. The fundamental distinction is: a forward/futures contract obligates both parties to transact at a future date, while an option gives the buyer the right (but not the obligation) to transact.

## Frameworks Introduced
- **Cash vs. Forward Transactions**: Spot transactions involve immediate exchange; forward contracts defer exchange to a maturity date, with the price negotiated today.
- **Call and Put Options**: A call gives the right to buy an asset at a fixed price; a put gives the right to sell. The buyer pays a premium to the seller, who keeps the premium regardless of the buyer's decision.
- **Insurance Analogy**: Options function like insurance—the buyer pays a premium for the right to exercise. Pricing depends on probabilities of certain outcomes.
- **Derivative Contract Types**: Forwards (OTC), futures (exchange-traded and standardized), options (rights without obligations), and swaps (cash flow exchanges).

## Key Concepts
- **Opening vs. Closing Trades**: An opening trade establishes a position; a closing trade reverses it. You can open by selling first (short) and close by buying later.
- **Open Interest**: The number of contracts not yet closed out. Long and short open interest are always equal.
- **Premiums**: The price paid by the option buyer to the seller. The seller keeps the premium irrespective of the buyer's exercise decision.
- **Expected Value Foundations**: The theoretical value of a derivative depends on probabilities assigned to different price outcomes.

## Anti-patterns
- Treating an option purchase as "free" because the premium is a sunk cost—ignoring that the seller always retains this payment regardless of exercise.
- Confusing the right to buy/sell (option) with the obligation to buy/sell (futures contract).
- Assuming the order of buy/sell always follows cash-market convention—in derivatives, selling first and buying later is routine.

## Key Takeaways
1. Derivatives transfer risk from one party to another, with value derived from an underlying asset.
2. Options are asymmetric: all rights belong to the buyer, all obligations to the seller.
3. The premium is the price of this asymmetry and is kept by the seller regardless of outcome.
4. Expected value and probability are the conceptual foundations of all option pricing.
5. Opening a short position (selling first) is normal in derivative markets and does not require prior ownership.
