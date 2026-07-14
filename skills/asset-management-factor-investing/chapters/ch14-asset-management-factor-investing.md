# Chapter 14: Factor Investing
## Core Idea
Factor investing turns asset-class investing into risk-factor investing: investors choose which factor risk premiums to harvest based on how well they can weather each factor's "bad times" relative to the average investor, then implement those exposures with the cheapest, most liquid instruments. The chapter uses Norway's sovereign fund, CPPIB's Reference Portfolio, and GM Asset Management's in-house factor benchmarks as implementation archetypes covering macro (equity/bond) factors, dynamic style factors (value-growth, momentum, short-volatility), and safe-asset factor decomposition.

## Frameworks Introduced
- **Reference Portfolio (CPPIB):** a passive, cheap, two-factor (equity + bond) benchmark that funds all other investments; illiquid assets like private equity and real estate are decomposed into equity/bond equivalents and "funded" by transfers from the Reference Portfolio.
- **Factor Recipe (4 criteria):** a factor must (1) be justified by academic research, (2) have exhibited persistent premiums expected to continue, (3) have return history covering bad times, and (4) be implementable in liquid, traded instruments.
- **Return decomposition:** r = (r − r_bmk) + r_bmk; ~90% of fund return variance comes from the benchmark/asset-allocation decision (Brinson-Hood-Beebower), rising to >99% for tightly-constrained funds like Norway.
- **Dynamic factor benchmarks:** non-market-cap-weighted, rule-based portfolios that tilt toward chosen factors (e.g., +5% value-growth loading) and rebalance dynamically as factor memberships migrate.
- **Factor-based manager evaluation:** regress active returns on market, size, value-growth, and momentum factor returns (industry Fama-French/Carhart); only alpha beyond factor exposure justifies fees — raises the bar for active management.
- **Risk–return factor analysis:** simulate return distributions and downside/left-skew measures as a function of factor exposure sizes to calibrate desired holdings.
- **Horizon-based governance:** short-term alpha (managers), medium-term dynamic factor strategies (2–5 yr verification), long-term strategic weights (asset owner/board).
- **Safe-asset factor investing:** sovereign bonds embed credit, collateral, liquidity/transactions, numeraire, macro-growth, inflation, and reserve-status factor risks; market-cap weights are inappropriate — build weights from the factors that matter to the owner.

## Key Concepts
- CPP Reference Portfolio: 65% equity / 35% bond passive benchmark managed by ~12–15 people.
- Factor vs asset-class benchmark: factors look through labels (e.g., "private equity") to underlying risk exposures.
- Static factors (long-only equity/bond) vs dynamic factors (long-short value-growth, momentum, short-vol, carry).
- Factors can appear and disappear: size premium vanished post-1985 after product creation; low-volatility may follow.
- Factor timing vs buy-and-hold: factor allocation is set top-down by the owner; dynamic factor strategies sit in the medium horizon bucket, not short-term alpha.
- Smart beta / "Norway model": passive but dynamic, index but active — cheap harvesting of dynamic factor premiums.
- Factor crowding: industry products exploiting a premium can erode it (size effect precedent).
- Shorting not required: value/momentum premiums persist without shorts but profitability falls ~50–60%.
- Level factor dominates fixed income (~90% of safe-asset return variation) → duration target beats holding the whole index.

## Anti-patterns
- **Over-timing factors / chasing the factor du jour:** trendy, statistically-mined factors belong in active, not benchmarks; benchmarks should hold only well-established factors.
- **Ignoring transaction costs and turnover:** dynamic factors require trading; minimizing costs is essential (GM Asset Management designs low-turnover monthly rebalancing).
- **Naive factor combination / mean-variance optimization first:** appropriateness depends on the owner's utility and bad-time tolerance, not just statistical optimization.
- **Market-cap weighting safe assets:** market weights ignore credit, liquidity, reserve, and macro factors that drive sovereign returns — GDP weights are "a solution in search of a problem."
- **Paying active fees for factor exposure:** if returns are explained by cheaply-replicable factor benchmarks, the active manager is not adding alpha; failing to factor-adjust over-rewards managers.

## Key Takeaways
1. Start top-down: list the factors that matter for the asset owner and implement them with the cheapest liquid instruments; keep the factor set small and simple.
2. Adopt a Reference Portfolio of cheap passive equity/bond index funds and fund all other investments as factor decompositions against it.
3. Benchmark active managers on factor-adjusted alpha (market + size + value + momentum), not raw excess returns — only pay for true stock-selection skill.
4. Match governance horizon to factor type: short-term alpha for managers, 2–5 year review for dynamic factor strategies, long-term strategic weights for the board/owner.
5. For sovereign/safe assets, replace market-cap or GDP weights with weights chosen from the relevant factors (credit, liquidity, reserve status, macro growth/inflation, duration level).
6. Communicate factor exposures ex ante so losses in bad times (e.g., 2008 short-vol/illiquidity) stay within anticipated limits and do not trigger reactive mandate revocation.