# Chapter 17: Hedge Funds

## Core Idea
Hedge funds (HFs) are **not an asset class**. HF returns have large exposure to *dynamic factors* — especially **volatility risk**. After taking these nonlinear risks into account, the average HF is unlikely to add value. HF fees are high but, contrary to popular perception, only a *minority* of HF manager compensation comes from incentive fees — most comes from fixed management fees on AUM. The 2007 "quant meltdown" shows how crowded dynamic-factor strategies can fail spectacularly with no obvious market trigger.

## Frameworks Introduced
- **HF as dynamic-factor portfolios, not an asset class** — decode HFs into their market, size, value, momentum, credit, and especially *volatility* factor loadings before judging return.
- **Quant meltdown (Aug 2007)** — quant funds lost 30% in three days with no market-wide decline; crowding in similar factor portfolios produced de-leveraging spirals ("25-sigma" moves, Rothman).
- **Statistical arbitrage / market-neutral styles** — high-freq stat-arb (seconds-days) vs longer-horizon market-neutral (weeks-months) using value, size, momentum, volatility, and credit factors.
- **Industry characteristics** — secretive, performance-fee + management-fee structure, 40-Act exempt; long/short, leverage, derivatives.
- **HF flows and fragility** — inflows chase past returns; outflows forced by gates/lock-ups/redemptions de-leverage crowded factor positions, amplifying losses (Liang-Park flow data).
- **Data biases in HF databases** — survivorship, backfill, selection, and liquidation biases inflate reported HF returns by ~3–7%/yr; funds stop reporting before they die.
- **HF failures and contagion** — Long-Term Capital Management (1998), Amaranth (2006), quant meltdown (2007); systemically important failures cluster at volatility regime shifts.
- **HF performance (net)** — pre-fee gross returns look impressive; *net* of fees and biases the average HF has underperformed equity benchmarks since ~2002; alphas concentrate pre-2002 institutionalization.
- **HF factors (Hasanhodzic-Lo, Fung-Hsieh)** — replicating HFs with trend-following, equity market, size, value, credit-spread, and volatility factors explains most return at far lower cost.
- **Deeper look at volatility risk** — many HF styles (convert arb, fixed-income arb, merger arb, short-vol) are *short volatility*; long-vol-of-vol factor risk is the unifying bad time.
- **Leverage** — leveraged factor portfolios lose when funding tightens; leverage + crowded factors + funding constraints = the quant-meltdown formula.
- **Agency contracts in HFs** — 2/20 structure, high-water marks, hurdles; the asymmetry of carry incentivizes risk-taking after drawdowns and funds-of-funds layer fees.
- **Fees** — although carry is salient, on average ~2/3 of compensation is the fixed management fee; AUM-based revenue dominates large HFs even without performance gains.
- **Cost of illiquidity** — gates, lock-ups, and side pockets impose real costs redeemable-asset premia that often exceed the (small) reported illiquidity premium.
- **The future of HFs** — clones, factor ETFs, and separately managed accounts compete with opaque funds; first versions may fail, the idea is right, and outsiders will popularize.

## Key Concepts
- **Short-volatility nature** — most HF styles deliver steady small gains then large losses in vol spikes; this is *option-selling*, not skill.
- **Volatility factor risk** — the dominant systematic exposure of HF returns; controlling for it shrinks residual alpha toward zero.
- **Vol-of-vol / higher-moment risk** — even returns that look uncorrelated to market beta are short vol-of-vol; tail risk is endogenous to most HFs.
- **De-leveraging spirals** — when crowded factor strategies all try to exit at once, illiquidity + leverage + margin calls compound into multi-standard-deviation moves with no fundamental news.
- **Crowding** — popular factors (low-vol, value, momentum) lose their premia as AUM accumulates; the size premium's disappearance is the precedent.
- **Net-of-fee, net-of-bias reality** — after survivorship/backfill/selection adjustment and fees, most HFs do not beat public factor clones.
- **Carry ≠ most of pay** — though carry dominates the public perception of HF pay, fixed management fees drive most GP revenue at scale; incentive is misaligned.
- **HF clones** — mechanical replicating portfolios of HF factors deliver ~70–80% of HF returns at <20bp in some categories, exposing the "alpha" as factor beta.
- **Smoothing & stale prices** — some HF styles (especially illiquid-credit and side-pocketed positions) report smoothed returns with understated volatility.

## Anti-patterns
- **Treating HFs as an asset class** — allocating a fixed "HF bucket" ignores that HFs are bundles of replicable dynamic factors, mostly short volatility.
- **Reading HF database returns naïively** — survivorship, backfill, and selection biases inflate averages by several percent per year; demand bias-adjusted track records.
- **Buying smoothed-return strategies as low-risk** — stable reported returns of convert/fixed-income arb hide left-tail vol-of-vol risk; unsmooth before judging risk.
- **Paying 2/20 for factor exposure** — if a 20bp factor clone captures the bulk of returns, the alpha slice does not justify full fees; factor-adjust first.
- **Ignoring crowding** — allocating to the popular HF styles of the moment (2007 stat-arb) is precisely when the de-leveraging-spiral risk is highest.
- **Underestimating illiquidity cost of lock-ups** — gates/side pockets/lock-ups do not pay you enough to forego liquidity in the bad times when you most need it.
- **Chasing recent winners** — flows follow recent returns exactly when the de-leveraging risk is largest; flows themselves create the next meltdown.

## Key Takeaways
1. **Decode HFs into factors** — replicate HF returns with market, size, value, momentum, credit, and especially volatility factor portfolios before paying active HF fees.
2. **Short volatility is the unifying HF bad time** — most HF strategies are short vol-of-vol; size positions assuming vol-spike losses, not normal-path Sharpe.
3. **Adjust HF data for survivorship, backfill, and selection biases** — true net alpha is near zero on average and concentrates before 2002; pay the average HF accordingly.
4. **Prefer cheap factor clones / SMAs over opaque HF vehicles** — they capture most of the return without the high-water-mark, lock-up, and opacity rents.
5. **Crowding is itself a risk factor** — when flows concentrate in popular styles, de-leveraging spirals (2007) become likely; diversify across factors and across manager types, and limit the crowded style.
6. **Treat HF illiquidity (gates, lock-ups, side pockets) as a real cost** — demand a premium in excess of the (bias-free) expected return before accepting it; often the premium is smaller than the cost.