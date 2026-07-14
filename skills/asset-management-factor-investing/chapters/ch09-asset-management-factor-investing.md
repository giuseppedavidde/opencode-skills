# Chapter 9: Bonds

## Core Idea
The **level factor** — the parallel shift in all bond yields — is the dominant driver of fixed-income returns. The level factor is shaped by risks associated with economic growth, inflation, and monetary policy. Corporate bonds do not just reflect credit risk; as theory predicts, **volatility risk** is an important factor and corporate bond returns correlate highly with equity returns. **Illiquidity risk** is also an important factor in bond returns. The chapter reframes fixed income from asset labels (government, IG, HY) into the level, term-spread, credit-spread, volatility, and liquidity factors underlying them.

## Frameworks Introduced
- **Level factor (Litterman-Shea / PCA)** — the first principal component of yield changes, shifting all yields together, accounts for ~90% of safe-bond return variation. Duration targets the level factor; market-cap sovereign weights are inappropriate because level dominates.
- **Monetary policy and the level factor** — the short rate, the policy rate (Fed funds), and QE/QT drive the level; the Taylor (1993) rule describes the policy rate as a function of inflation and output gaps.
- **Taylor rule** — `i_t = r* + π_t + 0.5(π_t − π*) + 0.5(y_t − y*)`; deviations (Taylor gaps) predict future rate moves and the level factor.
- **Changing policy stances** — pre-crisis Greenspan/Bernanke easing, ZLB, QE (large-scale asset purchases), forward guidance, Operation Twist; each alters the level and slope transmission.
- **Term spread / long-term bonds** — the second factor (slope); long bonds earn a term premium (compensation for duration and inflation/level risk) but also expose investors to the level factor.
- **Macro-factor term-structure models** — embed (1) underlying risk factors, (2) the short-rate rule, and (3) how the short rate and factor risk premiums transmit to long yields; reconcile bond premia with macro fundamentals.
- **Macro risk premiums in long-term bonds** — long bonds earn premiums for bearing growth, inflation, and level risk over multi-year horizons; the term premium is time-varying, not constant.
- **Credit spread / corporate bonds** — the third factor; the credit spread compensates for default risk but is much larger than realized defaults predict — the **credit spread puzzle**.
- **Default models (Merton/structural)** — equity is a call on firm assets; bond spreads depend on leverage, asset volatility, and distance-to-default.
- **Credit spread puzzle** — only a small fraction of the investment-grade spread is explained by actual default losses; taxes, systematic jump risk, and illiquidity fill the gap, with Baa-equity correlations reaching 65–84% post-2005.
- **Volatility risk in corporate bonds** — firm value volatility drives default risk and spreads; high-vol regimes widen spreads, and corporate bonds load on equity volatility factor risk.
- **Liquidity risk in corporate bonds** — corporate bonds trade infrequently, with bid-ask and price-impact premia; liquidity is a priced factor in bond returns.

## Key Concepts
- **U.S. downgrade (Aug 5, 2011)** — S&P cut U.S. AA+;Treasury yields *fell* (flight-to-quality): the move reflected growth/deflation fear, not perceived credit risk.
- **Level > slope > curvature** — PCA of yield changes ranks components; level alone dominates returns of high-grade bonds.
- **Short-rate rule deviation** — when the Fed funds rate sits below the Taylor rule, the level factor is low and term premiums richen (forward rate risk compensation).
- **Long bond Sharpe vs equity** — long Treasuries hedge equity risk in deflationary recessions (2008, 2020); the bond–equity correlation is regime-dependent.
- **Realized credit premium** — modest, much smaller than quoted IG spread; defaults cluster in recessions, exactly when investors need the cash least.
- **Equity correlation of credit** — high-yield and Baa corporate bonds correlate 0.5–0.8 with equities in bad times; they are not "bond-like," they are leveraged equity risk wrapped in a bond label.
- **Illiquidity premium within fixed income** — on-the-run vs off-the-run Treasuries, small-issue corporate discounts, and private placements all trade at illiquidity premia.

## Anti-patterns
- **Treat credit as a pure bond allocation** — IG/HY corporate debt is leveraged equity + volatility + liquidity risk; "Bonds = safe" label misleads.
- **Market-cap weighting sovereign benchmarks** — market-cap weights over-allocate to the most indebted (sometimes distressed) issuers; the level factor and credit/liquidity risks argue for factor-based weights.
- **Assume the term spread reflects default-free pure premium** — much of the slope reflects inflation uncertainty and monetary policy regime, not a static, safe reward.
- **Quote the credit spread as if it were all expected compensation** — defaults and recoveries explain only a piece; the rest is volatility, liquidity, and taxes investors may not be able to harvest.
- **Ignore the level factor in duration decisions** — arguing about credits or curve segments without first nailing duration exposure misses ~90% of the risk.
- **Buying HY for yield in quiet vol regimes** — HY's equity-like correlation emerges precisely when volatility spikes; the carry looks safe until the bad time.

## Key Takeaways
1. **Manage the level factor first** — duration (level exposure) drives ~90% of safe-bond returns; set the duration target before debating curve or credit subtleties.
2. **Decode corporate bonds into factors** — credit = default risk + volatility risk + equity correlation + liquidity risk; the bond label understates the equity-like losses in bad times.
3. **Own the credit spread puzzle** — only part of the spread compensates default; require the volatility, liquidity, and tax premia to be acceptable before harvesting them.
4. **Use macro-factor term-structure models**, not static term premiums, to position along the curve; the short-rate rule (Taylor gap) forecasts the level factor.
5. **Treat sovereign benchmarks as factor portfolios**, not market mandates — credit, reserve, liquidity, and macro-growth factors should drive sovereign bond weights, not market cap.
6. **Plan for liquidity risk** — corporate and small-issue bond illiquidity premia are real but only collectable by long-horizon investors able to hold through no-bid periods.