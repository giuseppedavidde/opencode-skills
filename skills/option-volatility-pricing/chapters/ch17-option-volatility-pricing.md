# Chapter 17: Hedging with Options

## Core Idea
Options serve as insurance contracts, enabling market participants to transfer specific risks while retaining others. Unlike futures (which transfer nearly all risk), options allow hedgers to tailor protection—sacrificing upside potential for downside protection (or vice versa). The choice between protective options (buying insurance) and covered writes (selling insurance for premium) involves a fundamental risk-reward tradeoff.

## Frameworks Introduced
- **Protective Put**: Long underlying + long put = synthetic long call. Protects downside below the strike; retains unlimited upside minus the premium cost. The strike acts as a deductible.
- **Protective Call**: Short underlying + long call = synthetic long put. Protects against upside risk (for short positions); retains downside profit potential.
- **Covered Call (Buy/Write)**: Long underlying + short call = synthetic short put. Generates immediate income (the premium) that provides limited downside protection; caps upside at the strike price.
- **Covered Put**: Short underlying + short put = synthetic short call. Income-generating hedge for a short position.
- **Caps and Floors**: Interest-rate applications—a borrower buys a call (cap) to limit maximum borrowing cost; a lender buys a put (floor) to guarantee minimum return.
- **Collar**: Long underlying + long protective put + short covered call. The short call premium offsets the long put cost, creating a zero-cost or low-cost hedge with both upside and downside bounds.

## Key Concepts
- **Hedger Types**: Natural longs (producers, lenders) profit from price/rate increases; natural shorts (consumers, borrowers) profit from declines. Each can use options to protect against adverse moves.
- **Cost of Protection**: ITM options offer more protection but cost more (higher premium); OTM options cost less but provide less protection (larger deductible). The hedger chooses the balance.
- **Synthetic Equivalence**: Every hedged position is synthetically equivalent to another option position. Understanding these equivalences reveals the true risk profile.
- **Portfolio Insurance**: Using index options or futures to protect an entire portfolio against market declines—a macro hedging approach vs. individual position hedging.

## Anti-patterns
- Buying protective puts without considering the premium cost—frequent hedging can erode returns even if the underlying performs well.
- Selling covered calls for income without understanding that you've sold upside potential and retained significant downside risk (only partially offset by the premium).
- Hedging with options that expire before the underlying exposure ends, leaving the position unhedged during the most critical period.
- Failing to consider the synthetic equivalence: a covered call has the same risk profile as a naked short put.

## Key Takeaways
1. Options provide partial risk transfer—unlike futures, you choose which risks to hedge and which to retain.
2. Protective options = buying insurance (limited risk, cost is the premium); covered writes = selling insurance (generate income, but risk remains).
3. Every hedged position is synthetically equivalent to another option position.
4. The strike price represents the deductible in an insurance analogy—higher strikes mean lower premiums but less protection.
5. Collars combine protective and covered strategies to achieve cost-neutral hedging with bounded outcomes.
