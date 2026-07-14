# Patterns — Asset Management: Factor Investing (Andrew Ang)

Actionable setups derived from chapters 2, 4, 6, 8, 10, 12, 14, 16, 18. Each entry follows **When → How → Trade-offs**.

---

## Ch 2 — Preferences

### 1. Loss-Aversion-Aware Sizing
- **When**: Investor exhibits asymmetric pain from losses (~2x pain vs equivalent gain — prospect theory).
- **How**: Cap single-position risk at ~0.5× Kelly; pre-commit a stop-loss level beyond standard vol-scaling; tilt toward low-beta assets when investor is in a drawdown.
- **Trade-offs**: Lower long-run compound return vs markedly smoother drawdown profile; reduces regret-induced behavioral exits.

### 2. Habit-Utility Risk-Cycle Adjustment
- **When**: Consumption/habit ratio low (recession, lifestyle upgrades recent) — risk aversion spikes endogenously.
- **How**: Hold a counter-cyclical buffer of safe assets (TIPS, short-dated treasuries); tilt equity exposure lower when surplus consumption is thin.
- **Trade-offs**: Cash drag in normal times; protects against forced de-risking at the worst possible price.

### 3. Relative-Utility De-Crowding
- **When**: Catching-up-with-the-Joneses herding drives popular factor crowding (low-vol, momentum in 2017-18).
- **How**: Monitor factor spread vs long-term average; trim exposure when crowd metrics (active share, ETF AUM) exceed 2σ; allocate to second-tier factors (profitability, investment).
- **Trade-offs**: Can lag in trending regimes; protects against factor crashes.

### 4. Epstein-Zin Time Separation
- **When**: Long-horizon investor with EIS > 0 but high short-horizon risk aversion.
- **How**: Separate intertemporal choice (smoothing) from risk attitude; use volatile assets for long horizon, safe assets for short horizon needs.
- **Trade-offs**: Implementation complexity; presumes parameter estimation of EIS.

### 5. Ambiguity-Aversion Stress Buffer
- **When**: Parameter uncertainty (factor loads, expected returns) is high — e.g. new asset class.
- **How**: Apply a haircut (Black-Litterman-style shrinkage) on expected returns; hold extra safe-asset buffer until estimation confidence improves.
- **Trade-offs**: Lower expected return during learning phases.

---

## Ch 4 — Investing for the Long Run

### 6. Constant-Mix Rebalancing Premium
- **When**: Multi-asset portfolio with mean-reverting risk premiums over long horizons.
- **How**: Rebalance to fixed weights (e.g., 60/40, 60/30/10) on a calendar or threshold-trigger basis; buy underweight / sell overweight asset classes.
- **Trade-offs**: Captures ~½σ² rebalancing premium but loses in trending bull markets; short convexity — painful in regime breaks.

### 7. Long-Run ≠ Time Diversification
- **When**: Investor claims "long horizon makes equities safe" (Samuelson's fallacy).
- **How**: Refute with i.i.d. argument — terminal wealth variance scales with horizon; equities are *not* safer long-run unless returns are mean-reverting. Use the rebalancing premium (not horizon) as the true long-run edge.
- **Trade-offs**: Forces explicit modeling of mean reversion vs random-walk; may justify lower equity weight than naive advisors suggest.

### 8. Volatility Targeting for Long Horizons
- **When**: Long-horizon investor willing to absorb equity premium but drawdown-constrained.
- **How**: Scale equity exposure inversely to realized 1y vol (Merton fraction: w* = (μ−rf) / (γσ²)); reduce equity weight in high-vol regimes, increase in low-vol.
- **Trade-offs**: Higher Sharpe than static mix; turnover costs and whipsaw in vol spikes.

### 9. Gordon Formula Sanity Check
- **When**: Estimating long-run equity return from fundamentals.
- **How**: r ≈ dividend yield + nominal earnings growth (Gordon); use Shiller PE / cyclically-adjusted yield as cross-check.
- **Trade-offs**: Anchored to fundamentals; underestimates when payout mix shifts to buybacks; illegitimate if retention > growth opportunities.

### 10. Kelly-vs-Small-Bet Sizing
- **When**: Log-utility investor vs CRRA investor with γ > 1.
- **How**: Kelly sizing assumes γ=1; for typical γ≈3-5, position ≈ 1/γ × Kelly; full Kelly yields extreme drawdowns.
- **Trade-offs**: Lower geometric return but smoother path; preserves liquidity for rebalancing.

---

## Ch 6 — Factor Theory

### 11. Bad vs Good Factor Filter
- **When**: Identifying whether a candidate factor deserves a risk premium.
- **How**: A *bad* factor pays off in good times and loses in bad times → earns premium (equity, value, carry). A *good* factor hedges bad times → low or negative premium (vol, safe haven). Reject factors with no economic story.
- **Trade-offs**: Cuts data-mined anomalies; misses factors where economic rationale is still emerging.

### 12. ICAPM State-Variable Hedging
- **When**: Building a long-horizon portfolio beyond single-period CAPM.
- **How**: Add hedging demands — bonds/cash hedge equity drawdown state variable, value stocks hedge growth shocks, momentum hedge value crashes.
- **Trade-offs**: More robust than CAPM but requires identifying relevant state variables; fragile if model misspecified.

### 13. APT Multiple-Factor Decomposition
- **When**: Alpha attribution to common factors.
- **How**: Regress returns on candidate factors (Fama-French, momentum, BAB); alpha = intercept. If alpha survives economically plausible factors → potential skill; if it disappears → factor exposure.
- **Trade-offs**: Standardized and reproducible; sensitive to factor selection and window choice.

### 14. Consumption CAPM Asset Selection
- **When**: Long-horizon macro-driven investor.
- **How**: Rank assets by covariance with aggregate consumption growth (Breeden); select those with high consumption beta.
- **Trade-offs**: Empirically poor fit (equity premium puzzle); use as qualitative overlay, not sole driver.

### 15. No-Arbitrage Replicating Portfolio
- **When**: Pricing a derivative or new asset class.
- **How**: Replicate payoff with tradable factors; price = cost of replicating portfolio; reject if price diverges without frictions.
- **Trade-offs**: Robust; assumes liquidity and continuous trading — fails in stressed markets.

---

## Ch 8 — Equities (Aggregate Premium)

### 16. Disaster-Risk Premium Capture
- **When**: Equity premium reflects compensation for rare disasters (Rietz-Barro).
- **How**: Hold equities *because* they lose money in disaster states; ensure your liabilities/consumption needs don't require liquidity in those same states.
- **Trade-offs**: Premium accrues slowly over long samples; capacity to hold through actual disaster is the test.

### 17. Long-Run Risks Tilt
- **When**: Selecting equity segments with persistent cash-flow growth.
- **How**: Tilt to high long-run-risk beta assets (value, carry, leveraged equity) — they command higher premium.
- **Trade-offs**: Higher drawdown in long-run-risk realizations; size-controlled.

### 18. Inflation Hedge Layering
- **When**: Equity betas to inflation are negative (developed: −0.25 to −0.42).
- **How**: Pair equities with TIPS, short treasuries (beta +0.6), emerging-market equities (beta ~+1); never rely on US equities alone for inflation protection.
- **Trade-offs**: Adds complexity; short-duration drag in low-inflation regimes.

### 19. Volatility-Timing Overlay
- **When**: Equity vol is forecastable (GARCH, VIX), expected return predictability is weak.
- **How**: Scale equity weight by 1/σ; trim when VIX jumps >30%, increase when VIX <12%. Large investors should aggregate over months, not days.
- **Trade-offs**: Higher Sharpe (~+0.1-0.2); turnover costs; whipsaw in vol spikes that don't materialize.

### 20. Valuation-Based Constant-Mix Hybrid
- **When**: Predictability signals are weak and noisy.
- **How**: Use rebalancing to constant weights as primary engine; modulate target equity weight ±10% only when Shiller-PE exceeds 95th or below 5th historical percentile.
- **Trade-offs**: Robust to estimation noise; forgoes pure timing alpha.

---

## Ch 10 — Alpha & Low-Risk Anomaly

### 21. Factor-Adjusted Alpha Screen
- **When**: Evaluating a fund manager's "alpha".
- **How**: Regress against Fama-French + momentum + BAB + quality; require intercept (true alpha) to remain statistically significant (t>2) over multiple non-overlapping windows.
- **Trade-offs**: Eliminates skill-by-factor-loading confusion; misses genuine alpha hidden in non-standard factors.

### 22. Betting Against Beta Portfolio
- **When**: Leverage constraints (40-Act funds, pension risk limits) force investors into high-beta names.
- **How**: Long low-beta / short high-beta portfolio, leveraged to match market beta; captures persistent premium from constraint-driven mispricing.
- **Trade-offs**: Premium traceable to leverage constraints — capacity crowded post-Frazzini-Pedersen; requires leverage and shorting.

### 23. Min-Variance Equity Portfolio
- **When**: Low-vol anomaly — low-vol stocks outperform high-vol on Sharpe basis.
- **How**: Construct min-variance equity portfolio (or buy MV ETF); ignores market weights, optimizes pure risk.
- **Trade-offs**: Sector concentration; underperforms in strong bull runs where high-beta works; works over full cycles.

### 24. Style-Analysis Ex-Post Decomposition
- **When**: Diagnosing a fund's style drift.
- **How**: Run Sharpe (1992) constrained regression — return = Σ ( exposures × asset-index returns ), exposures ≥ 0, sum ≤ 1.
- **Trade-offs**: Reveals drift but not timing skill; complementary to factor regression.

### 25. Low-Vol Volatility Scaling
- **When**: Combining low-vol anomaly with vol targeting.
- **How**: Lever low-vol portfolio to target market volatility (or strategic equity vol ~12-15%) — captures anomaly while controlling path risk.
- **Trade-offs**: Requires leverage access; market-impact rises with size.

---

## Ch 12 — Tax-Efficient Investing

### 26. Asset Location Decision
- **When**: Holding both taxable and tax-deferred (IRA, 401k) / tax-exempt (Roth) accounts.
- **How**: Place high-tax (tax-inefficient) assets — taxable bonds, REITs, high-turnover funds — in tax-deferred; place tax-efficient (equities, broad index ETFs, munis) in taxable accounts; munis only in taxable.
- **Trade-offs**: Optimal when accounts comparable in size; rough heuristic: "highest-yield → tax-deferred."

### 27. Tax-Loss Harvesting Machine
- **When**: Portfolio sits underwater in individual positions.
- **How**: Realize losses to offset capital gains + $3,000 ordinary income; replace with non-substantially-identical ETF (avoid wash sale, 30-day window around trade).
- **Trade-offs**: ~0.5-1% annual after-tax return enhancement; tracking error from substitute; permanent-deferral benefit on subsequent gains.

### 28. Long-Term-Holding Discipline
- **When**: Holding positions near 12-month threshold.
- **How**: Defer sales to cross 12 months → convert ordinary-rate gain (up to 37% Fed) to long-term (15-20%); tax-alpha alone is ~15-17% × gain size for one transaction.
- **Trade-offs**: Carries position-specific risk; sometimes loses more in price decline than tax saved.

### 29. Constantiniades Tax-Timing Option
- **When**: Many positions joined by gains and losses throughout the year.
- **How**: Harvest losses yearly, defer gains indefinitely — option value: pay tax never until stepped-up basis at death.
- **Trade-offs**: Effective for taxable portfolios with active rebalancing; requires sufficient turnover and breadth.

### 30. Dividend-Yield Tax Optimization
- **When**: High-income taxable investor in 37% bracket.
- **How**: Prefer qualified dividends (20% LT cap-gains rate) over ordinary income; prefer low-yield growth stocks over high-yield in taxable if ordinary income tax burden high; munis for fixed income.
- **Trade-offs**: Foregoes dividend yield premia; compensated by tax-equivalent yield.

---

## Ch 14 — Factor Investing (Implementation)

### 31. Reference Portfolio Anchor
- **When**: Building a multi-asset, multi-class portfolio (CPP-style).
- **How**: Start with passive two-factor (equity / bond) reference portfolio; benchmark alpha is measured as deviation from reference; fund all active bets against this anchor.
- **Trade-offs**: Forces explicit rationale for every deviation; risk-budgetOK; constrains alpha ambition.

### 32. Factor Recipe Checklist
- **When**: Selecting which factors to pay for.
- **How**: Apply Andrew Ang's four criteria — (1) academic basis, (2) persistent over >50y out-of-sample, (3) bad-times track record, (4) implementable in liquid vehicles with low cost.
- **Trade-offs**: Filters out fashionable factors; misses factors where history is short (e.g., some alternatives).

### 33. Dynamic Factor Benchmark Construction
- **When**: Replacing cap-weighted index with factor-tilted benchmark.
- **How**: Build rule-based, non-cap-weighted index (value-growth tilt, low-vol tilt); rebalance to fixed style weights; passive implementation with active logic.
- **Trade-offs**: Lower fees than active; capacity and turnover costs from non-cap weighting.

### 34. Macro Factor Investing
- **When**: Commodities, real estate, infrastructure, real bonds — exposures to growth/inflation regimes.
- **How**: Decompose asset returns into macro-economic factor exposures (growth, inflation, deflation, real-rate regimes); balance the macro-factor exposures rather than asset-class labels.
- **Trade-offs**: Reallocates risk budget to actual macro exposures; requires econometric regime modeling.

### 35. Manager Alpha via Factor Regression
- **When**: Selecting active managers.
- **How**: Run Fama-French/Carhart + BAB regression on live track record; require positive intercept with t-stat >2 over ≥5y; move residual alpha into budget; reject where alpha is just factor loadings.
- **Trade-offs**: Survives genuine skill; misses new managers with too-short record; benchmark selection subjective.

---

## Ch 16 — Mutual Funds & 40-Act Funds

### 36. Active Share Filter for Mutual Funds
- **When**: Choosing active mutual funds.
- **How**: Require Active Share >80% (truly active) AND expense ratio <0.5%; below 60% Active Share is closet indexing — buy the passive version instead.
- **Trade-offs**: Truly active picks occasionally win big but with non-survivorship / track-record issues; high Active Share alone is not enough.

### 37. ETF Creation-Redemption Arbitrage
- **When**: Choosing between ETF and mutual fund for the same exposure.
- **How**: Prefer ETF for taxable accounts — in-kind creation/redemption minimizes capital gains distributions; intraday liquidity reduces market impact.
- **Trade-offs**: ETF spreads in less-liquid asset classes can negate tax benefit; check bid-ask before committing.

### 38. Star-Manager Anti-Pattern
- **When**: Considering a fund with recent 5-star Morningstar rating.
- **How**: Regress past performance on common factors — most "star" returns shrink or vanish after factor adjustment; mandate future persistence test over ≥5y with t-stat >2 on true alpha.
- **Trade-offs**: Forgoes small subset of genuine star managers; protects from return-chasing.

### 39. Expense-Ratio Threshold
- **When**: Comparing similar-capability funds.
- **How**: Each 1% extra fee drags long-run return by ~1%/year compounded; cap equity funds at 0.3-0.5%, fixed income at 0.2-0.4%, alternatives higher; passive index ≤0.10%.
- **Trade-offs**: Some active strategies may justify higher fees — demand ≥1.5% edge above next best passive.

### 40. Fund-Flow Sentiment Counter-Signal
- **When**: A fund receives unusually large inflows (top decile).
- **How**: Trim / avoid — Berk-Green returns accrue to firm not investors; flows chase past performance, future returns systematically lower; recent large AUM growth taxes capacity-constrained strategies.
- **Trade-offs**: Misses continued momentum in capacity-unconstrained passive funds.

---

## Ch 18 — Private Equity

### 41. PME Comparison vs IRR
- **When**: Evaluating a PE fund's reported IRR.
- **How**: Compute Public Market Equivalent (Kaplan-Schoar): discount PE cash flows using the public market return at the same vintage; PME >1.0 means PE outperformed public equivalent.
- **Trade-offs**: Removes leverage/time-value sleight-of-hand; requires benchmark selection discipline.

### 42. Leveraged Small-Value Factor Decomposition
- **When**: Assessing PE buyout returns.
- **How**: Regress PE returns on small + value + 3x leverage — alpha ≈ 0; treat buyout as a leveraged small-value beta exposure, not as a separate asset class.
- **Trade-offs**: Demystifies "PE premium"; means similar exposure is replicable in public markets at lower fees.

### 43. Vintage Diversification Constraint
- **When**: Committing to PE over multiple years.
- **How**: Spread commitments across at least 5-7 vintages; allocate paced 10-15% of total PE budget per year; avoid clustering commitments in market peaks (which contain "money chasing deals").
- **Trade-offs**: Smooths J-curve; requires committing through downturns when capital is scarce; capacity-constrained LP must maintain pacing discipline.

### 44. Top-Quartile Deception Check
- **When**: Reviewing a GP's track record boasting top-quartile placement.
- **How**: Use external benchmark (PME-rank, Burgiss/Cambridge peers); 77% of GPs self-report top quartile via benchmark cherry-picking; require LP-funded cash-on-cash multiples.
- **Trade-offs**: Discards marketers; forgoes valid alpha persistence finding — true top quartile does repeat (Kaplan-Schoar).

### 45. Fee-Economics Negation Filter
- **When**: PE fees charged at ~2/20 with committed (not deployed) capital.
- **How**: Compute fee drag: ~$18-23 per $100 collected over fund life, two-thirds being fixed management fees regardless of performance; recurrent ~6-7% required gross alpha needed just to break even vs passive PME.
- **Trade-offs**: Filters uneconomic structures; some top-quartile buyout GPs persistently justify fees — but the median does not.