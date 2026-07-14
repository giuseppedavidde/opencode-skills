# Chapter 13: Illiquid Assets

## Core Idea
After correcting for biases induced by infrequent trading and selection, it is unlikely that illiquid asset classes have *higher risk-adjusted* returns, on average, than traditional liquid stock and bond markets. However, there are *significant illiquidity premiums within asset classes*. Portfolio choice models that incorporate illiquidity risk recommend only *modest* holdings of illiquid assets, and investors should demand high risk premiums for holding them. Harvard's 2008 crisis — liquidating and slashing budgets while private-asset marks lagged reality — is the cautionary archetype.

## Frameworks Introduced
- **Endowment model (Swensen)** — long-term investors should hold lots of illiquid alternatives (PE, HF, real estate) for diversification and illiquidity premia; Harvard was an early adopter and was nearly undone by it.
- **Sources of illiquidity** — (1) clientele effects and participation costs, (2) transaction costs, (3) search frictions, (4) asymmetric information, (5) price impact, (6) funding constraints. Each is a distinct franchise, not a single "illiquidity."
- **Characteristics of illiquid markets** — wide bid-ask, low turnover, few participants, long search, large minimum size,_LARGE price impact from any trade.
- **Illiquid asset reported returns are not returns** — three biases: survivalship, infrequent sampling (stale pricing), and selection. Naively reading reported illiquid-asset returns as mark-to-market returns overstates Sharpe and understates risk.
- **Survivorship bias** — failed funds/properties are dropped; databases overstate averages.
- **Infrequent trading bias / stale prices** — appraised or last-traded prices smooth returns, biasing volatility down and autocorrelation up (Getmansky-Lo-Makarov style).
- **Unsmoothing returns** — back out true volatility from the autocorrelation structure of observed (smoothed) returns; affects *risk* estimates, not expected returns; no effect if returns are uncorrelated; an art, not a science.
- **Selection bias** — the properties/funds that transact (or are chosen into an index) are unrepresentative; private-market indices especially overstate averages.
- **Illiquidity risk premiums across asset classes** — comparing illiquid asset-class average returns to liquid equivalents confuses: (1) biases inflate apparent return, (2) ignores the extra risk, (3) no market index exists for illiquid classes, (4) factor risk cannot be separated from manager skill. Conclusion: across-class illiquidity premia are probably small after adjustment.
- **Illiquidity risk premiums within asset classes** — real and measurable: less-liquid bonds, small/illiquid stocks, and private placements earn illiquidity premia *within* a class.
- **Market making & rebalancing** — acting as a market maker at the security level, or rebalancing at the portfolio level, captures liquidity premia from less-sophisticated/forced counterparties.
- **Portfolio choice with transaction costs** — trades should be sized by the trade-off between rebalancing benefit and price impact; turnover scales with liquidity cost.
- **Asset allocation with infrequent trading** — when an asset cannot be traded, its weight drifts; optimal target weights and rebalancing intervals account for the lock-up.

## Key Concepts
- **Liquidity as a factor** — illiquidity risk is systematic: all illiquid assets suffer together when funding constraints bind (2008, 2020).
- **Harvard 2008** — endowment fell 22% in three months, then private marks worsened; Harvard liquidated public assets into the crash exactly because private holdings were un-tradable — the forced liquidation trap.
- **Endowment-spending dependency** — Harvard funded >1/3 of operations (and some units >70%) from endowment income; illiquidity + spending rule jointly force procyclical liquidations.
- **Appraisal smoothing** — private real estate, PE NAVs, and HF marks all understate realized volatility; unsmoothing often doubles measured vol.
- **Liquidity premium is conditional** — it accrues in normal times and evaporates exactly when funding is tight; collecting it requires holding through no-bid periods.
- **Long horizon enables illiquidity, but doesn't make it free** — long horizon allows bearing the lock-up, but the expected return premium must compensate the systematic funding-risk factor.
- **Optimal illiquid allocation is small** — calibrated portfolio models recommend only modest weights even for long-horizon funds.

## Anti-patterns
- **Reading illiquid-asset index returns as mark-to-market** — appraisal/stale pricing inflates their Sharpe and deflates their covariance with public assets; overstates diversification.
- **Pretending illiquidity is one thing** — trading illiquidity, funding illiquidity, and liquidity spirals are distinct; do not average them.
- **Building the endowment model without a liquidity reserve** — committing large weights to IV/PE/RE without enough liquid assets to meet spending through crises forced Harvard to sell in the crash.
- **Ignoring the funding-liquidity factor** — assuming low correlations across PE/RE/HF hold through crises; they rise together when funding binds.
- **Using liquidity as a yield lure** — chasing "illiquidity premium" via lock-ups while the systematic factor risk is unmeasured.
- **Valuing private marks at cost** — zombies held at cost to milk fees; mark-to-market discipline is essential.
- **Forgetting manager skill confounds the premium** — in illiquid classes, factor risk and manager alpha cannot be separated, so reported premia partly reflect selection of better managers.

## Key Takeaways
1. **Adjust reported returns before comparing asset classes** — unsmooth, correct for survivorship and selection; risk-adjusted illiquid-class returns are unlikely to dominate liquid markets.
2. **Hunt illiquidity premia within asset classes**, where they are measurable and separable from manager skill; the across-class premium is small and easy to misattribute.
3. **Hold only modest illiquid weights** — calibrated models and the Harvard experience both recommend small allocations even for long-horizon investors.
4. **Maintain a liquid reserve sized to spending and commitment calls** — enough liquid assets to fund operations and PE capital calls through multi-year no-bid periods.
5. **Decompose reported illiquid returns into factor risk + illiquidity premium + manager alpha**, and pay only for the genuine premium/alpha; do not reward stale-price illusions.
6. **Plan for the worst liquidity scenario** — assume all illiquid assets bid together when funding tightens, and ensure the spending rule and liquid reserve can absorb the gap.