# Chapter 7: Factors

## Core Idea
Factors drive risk premiums. One set of factors describes fundamental, economy-wide variables — growth, inflation, volatility, productivity, and demographic risk. Another set consists of tradeable investment styles — the market portfolio, value-growth, and momentum. The economic theory behind factors can be *rational* (high long-run returns compensate for low returns during bad times) or *behavioral* (premiums result from agent behavior not arbitraged away). The chapter grounds each factor in its bad times and distinguishes whether its premium is structurally persistent or potentially ephemeral.

## Frameworks Introduced
- **Macro factors** — fundamental, economy-wide risks: economic growth, inflation, volatility, productivity, demographics. Each defines its own bad times; an asset is attractive iff it pays off when these bad times strike.
- **Economic growth factor** — assets that lose when GDP growth collapses carry a positive growth premium; equities are the canonical growth-sensitive asset.
- **Inflation factor** — assets that lose when inflation surprises upward carry an inflation premium; nominal bonds and equities both suffer, while T-bills/inflation-linkers and some commodities hedge.
- **Volatility factor** — assets that lose when volatility spikes (VIX, realized vol) carry a volatility risk premium; selling vol/insurance is a long-volatility-factor position that suffers in crises.
- **Other macro factors** — productivity, demographics, and political/regime risk; these shift investment opportunity sets slowly.
- **Dynamic factors (tradeable styles)** — Fama-French and Carhart: market (MKT), size (SMB), value (HML), momentum (UMD); long-short portfolios that replicate the styles and carry risk premiums.
- **Fama-French (1993) three-factor model** — MKT + SMB + HML; explains much of the cross-section CAPM misses.
- **Size factor (SMB)** — small caps historically beat large caps; premium shrank/disappeared post-1985 (possibly product creation arbitraged it); small-cap effect is younger and more fragile than value.
- **Value factor (HML)** — high book-to-market (value) beats low book-to-market (growth); one of the largest, most persistent equity premiums across countries and asset classes.
- **Rational theories of the value premium** — value stocks are risky in bad times (distress risk, long-run risk, liquidity droughts); the premium rewards bearing that risk.
- **Behavioral theories of the value premium** — overextrapolation of past growth, representativeness, and limited attention cause growth overpricing that is not fully arbitraged (constraints, slow capital).
- **Value in other asset classes** — value-growth sorts work in bonds, currencies, commodities, and across countries, suggesting a common factor (carry-style) driver.
- **Momentum factor (UMD, Jegadeesh-Titman 1993)** — past 12-month winners outperform past losers over the next 1–12 months; large and pervasive, but crashes violently (2009 momentum crash); almost certainly behavioral and arbitrage-limited.

## Key Concepts
- **Value-growth strategy** — long value, short growth; positive long-run average but large drawdowns (1999 tech boom, 2008, 2011).
- **Bad times per factor** — value loses in growth-led bubbles and distress; momentum crashes in volatility regime shifts; size premium attenuates after product introduction; market loses in recessions/disasters.
- **Rational vs behavioral is binary for persistence** — rational premiums recur while the bad-time risk endures; behavioral premiums can be eroded by product creation and arbitrage capital.
- **Style premia across asset classes** — value, momentum, and carry show up consistently across equities, bonds, FX, and commodities; a single common factor may underlie them.
- **Multi-factor portfolios** — value, size, momentum, and market are imperfectly correlated; combining them yields better Sharpe ratios than single-factor bets.
- **Long-only vs long-short** — long-only value/momentum capture ~50–60% of the long-short premium; long-short requires shorting, leverage, and higher turnover.
- **Factor timing is hard** — premiums arrive over decades with multi-year drawdowns; timing value or momentum reliably is statistically fragile.

## Anti-patterns
- **Single-factor worship** — betting solely on value, momentum, or size ignores the bad times specific to that factor (1999 value drawdown, 2009 momentum crash).
- **Confusing a behavioral premium for a rational one** — momentum crashes exist *because* it is behavioral; expect regime-change risk, not steady compensation.
- **Treating size as permanent** — the size premium was largely arbitraged after the 1980s; assuming historical premia recur is dangerous for any factor subject to product creation.
- **Ignoring factor drawdowns in backtests** — long-run positive average is cold comfort through multi-year underperformance that causes most investors to abandon the factor.
- **Long-short without accounting for shorting/leverage costs** — theoretical long-short premia overstate what most investors can actually harvest net of costs and constraints.
- **Statistical factor mining** — discovering "factors" by data-snooping hundreds of sorts guarantees false positives; require economic bad-time stories and out-of-sample persistence.

## Key Takeaways
1. **Identify each factor's bad times** — value (growth bubbles, distress), momentum (volatility regime shifts), market (recessions/disasters), inflation (unexpected inflation), volatility (crises); an asset is attractive iff it hedged *your* bad times.
2. **Distinguish rational from behavioral premia** — rational premia persist while the underlying risk endures; behavioral premia carry regime-change and arbitrage risk that can erode them.
3. **Harvest many factors, not one** — value, size, momentum, and macro factors are imperfectly correlated; a multi-factor portfolio stabilizes premia collection.
4. **Take the long-short with realistic costs** — long-only captures most of the premium at a fraction of the cost and complexity of true long-short.
5. **Expect and budget for factor drawdowns** — multi-year underperformance is normal; build governance and IPS rules to stay invested through it.
6. **Look for the carry commonality** — value, momentum, and carry variants appear across asset classes, suggesting a few deep risks rather than dozens of independent anomalies.