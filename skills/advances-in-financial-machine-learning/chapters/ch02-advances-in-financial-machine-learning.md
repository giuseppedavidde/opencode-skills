# Chapter 2: Financial Data Structures

## Core Idea
The starting point of any financial ML project should be **raw, unstructured data**, not someone else's processed dataset. Consuming pre-processed bars guarantees you only rediscover what others already know. The chapter teaches how to transform irregular inhomogeneous tick streams into a homogeneous table ("bars") amenable to ML, and how to model multi-product baskets (futures rolls, spreads) as a single cash-like series.

## Frameworks Introduced
- **Four essential data types**: Fundamental, Market, Analytics, Alternative — ordered by increasing diversity and informational value.
- **Standard bars**: Time, Tick, Volume, Dollar bars — sampling as a subordinated process of trading activity.
- **Information-driven bars**: Tick/Volume/Dollar Imbalance Bars (TIB/VIB/DIB) and Tick/Volume/Dollar Runs Bars (TRB/VRB/DRB) — sample more frequently when informed trading arrives.
- **Tick rule**: sign every tick as buy/sell from price changes (b_t ∈ {−1,1}) to build imbalance/run statistics.
- **ETF trick**: represent any basket/spread/rolled-future as the value of $1 invested, strictly positive, with embedded carry, rebalance costs and bid-ask.
- **PCA weights**: derive hedging allocations from a target risk distribution across principal components.
- **Single-future roll**: cumulative roll-gap series detracted from prices; build non-negative rolled series via (1+r).cumprod().
- **CUSUM filter**: event-based sampling — trigger a bar only when a cumulative run-up/run-down of length h occurs.

## Key Concepts
- Time bars oversample low-activity periods and under-sample high-activity periods → serial correlation, heteroscedasticity, non-normality.
- Dollar bars are robust to splits, buybacks and price appreciation; bar count stays stable over time.
- Imbalance bars = "buckets of trades containing equal amounts of information" — frequency rises with asymmetric/informed trading.
- Fundamental data is backfilled/reinstated; must align to the **release date**, never the reporting-period end — a common reproducibility killer in factor research.
- Raw prices size positions; rolled prices simulate PnL/mark-to-market.
- Linspace vs uniform sampling reduce data but ignore relevance; event-based sampling feeds the ML only catalytic, informative examples.

## Anti-patterns
- Using time bars as the default bar structure for ML.
- Treating fundamental data as if published at period-end (look-ahead bias).
- Backfilling/reinstating values as if known at first release.
- Modeling a futures spread with raw prices (negative values, fictitious PnL from weight convergence).
- Sampling uniformly at random and feeding every bar to the classifier regardless of informational content.
- Confusing tick, volume and dollar bars when the security's price or share count changed materially.

## Key Takeaways
1. Dollar and imbalance bars yield returns closer to IID Gaussian than time bars.
2. The ETF trick lets every downstream object treat any basket as a single non-expiring cash instrument.
3. CUSUM filtering produces event-driven samples that reduce heteroscedasticity relative to threshold-crossing signals (e.g. Bollinger bands).
4. Hard-to-store, infrastructure-annoying datasets are the most promising — competitors gave up or processed them wrong.
5. The structured feature matrix is the foundation; every later chapter assumes bars + correct roll + event sampling done right.