# Chapter 14: Synthetics

## Core Idea
Options can be combined with other options or with underlying contracts to replicate other instruments. These synthetic relationships are the foundation of option arbitrage, risk management, and strategy construction. Understanding synthetics reveals that calls and puts at the same strike are essentially the same volatility instrument — they differ only in delta sign, not in gamma or vega.

## Frameworks Introduced
- **Synthetic Underlying**: Long call + short put at same strike = synthetic long underlying (always buys at exercise price at expiration). Short call + long put = synthetic short underlying
- **Synthetic Options**: Long underlying + long put = synthetic long call; short underlying + short put = synthetic short call; short underlying + long call = synthetic long put; long underlying + short call = synthetic short put
- **Companion Option Hedge Rule**: Buy a call + sell underlying = synthetic long put; sell a call + buy underlying = synthetic short put; buy a put + buy underlying = synthetic long call; sell a put + sell underlying = synthetic short call
- **Gamma/Vega Identity**: Companion calls and puts (same strike, same expiration) have identical gamma and vega — volatility traders make no distinction between them

## Key Concepts
- **Delta Relationship**: `|Call Δ| + |Put Δ| ≈ 100` for companion options (e.g., if call Δ=75, put Δ≈−25)
- **Gamma/Vega Equality**: If June 100 call has gamma=5, June 100 put also has gamma=5. If June 105 put has vega=0.20, June 105 call also has vega=0.20. This is why volatility traders are indifferent between calls and puts at the same strike
- **Theta Differences**: Unlike gamma and vega, companion theta values may differ due to cost-of-carry on underlying or options (interest, dividends)
- **Cost of Carry**: Stock purchases incur interest cost (negative theta); futures have no carry cost; stock-type settled options have carry cost that creates theta differences in synthetics
- **Three Ways to Buy a Straddle**: (1) Buy call + buy put directly, (2) Buy call + synthetic long put (call + sell underlying), (3) Buy put + synthetic long call (put + buy underlying). The best method depends on pricing
- **Iron Butterfly**: Long strangle + short straddle centered in the middle. Equivalent to a traditional butterfly but done for a credit. Long butterfly = short iron butterfly
- **Iron Condor**: Long outside strangle + short inside strangle. Equivalent to a traditional condor but done for a credit
- **Christmas Trees**: Long call ratio spread; rewritten synthetically reveals a short strangle combined with a long put at lower strike — limited downside, unlimited upside
- **Vertical Spread Synthetic Equivalence**: Bull call spread written synthetically as puts reveals the equivalent bull put spread; call and put vertical spreads with same strikes have identical characteristics

## Anti-patterns
- **Ignoring settlement procedures**: Synthetic equivalence depends on settlement type; futures-type vs. stock-type settlement changes theta relationships
- **Assuming exact equivalence**: Synthetics are approximately, not exactly, equivalent; the "≈" acknowledges interest rate and early exercise effects
- **Trading synthetics without comparing prices**: The best synthetic route depends on execution prices; always check all three ways to construct a strategy
- **Forgetting the expiration condition**: A synthetic long underlying becomes an actual long position only at expiration — before expiration it has option risk characteristics
- **Confusing iron and traditional butterflies**: Long butterfly = debit, short iron butterfly = credit; both want the same outcome but differ in cash flow mechanics

## Key Takeaways
1. Six basic synthetic contracts exist (long/short underlying, long/short call, long/short put) — any strategy can be constructed multiple ways
2. Companion calls and puts have identical gamma and vega — a volatility trader can switch between them by trading the underlying
3. An iron butterfly/condor is a credit-position equivalent of a traditional debit butterfly/condor; the choice depends on execution prices
4. Synthetics explain why vertical call and put spreads are equivalent — the long/short underlying in the synthetic conversion cancels out
5. Write complex positions synthetically to reveal their true risk profile — a confusing call spread may simplify to a recognizable put structure
