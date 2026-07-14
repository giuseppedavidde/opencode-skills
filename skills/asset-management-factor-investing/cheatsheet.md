# Cheatsheet — Asset Management: Factor Investing (Andrew Ang)

Quick-reference decision tables and rules for factor-investing practitioners.

---

## 1. Factor Selection Checklist (Ang's 4 Criteria)

| Criterion | Question | Accept if |
|---|---|---|
| Academic basis | Has theoretical foundation in peer-reviewed lit? | Yes (CAPM/ICAPM/APT/consumption-based) |
| Persistence | Robust over >50y out-of-sample and across markets? | Yes |
| Bad-times payoff | Loses precisely in low-consumption/recession states? | Yes (defines "bad" factor) |
| Implementable | Liquid vehicles, capacity >$100B, fees <50bp? | Yes |

Reject any candidate failing 2+ criteria — likely data-mined anomaly.

---

## 2. Bad Factor vs Good Factor

| Type | Pays Off When | Example | Earns Premium? |
|---|---|---|---|
| **Bad** | High consumption / good times | Equity, value, carry, profitability | Yes (positive) |
| **Good** | Low consumption / bad times | Vol, safe-haven (gold, JPY) | Low or negative |
| **Neither** | Random/uncorrelated | Statistical fits, calendar anomalies | Reject |

Rule: hold bad factors for premium, hold good factors for hedging bad ones.

---

## 3. Asset Location Matrix (Taxable vs Deferred vs Roth)

| Asset Class | Taxable | Tax-Deferred (IRA/401k) | Tax-Exempt (Roth) |
|---|---|---|---|
| Taxable bonds / REITs | Avoid | **Best** | Good |
| High-turnover equity | Avoid | Good | Acceptable |
| Broad index ETFs | **Best** | Good | Good |
| Low-yield growth equity | **Best** | OK | Good |
| Municipal bonds | **Best** | Never (waste) | Never (waste) |

Rule: highest-income-yield asset → tax-deferred first.

---

## 4. Fund Selection Decision Tree

```
1. Need active management? NO → buy passive ETF (expense ≤0.10%)
2. YES → Active share >80%? NO → buy passive (closet indexer)
3. YES → Expense ratio <0.5%? NO → reject unless ≥1.5% verified alpha
4. YES → True alpha (regression on FF+Momentum+BAB) t-stat >2 over 5y? NO → reject
5. YES → Capacity not breached (AUM < strategy cap)? NO → reject
6. YES → AUM growth <50% / year? NO → trim (return chasing)
7. ALL YES → allocate ≤2% portfolio per name; cap total active sleeve
```

---

## 5. Rebalancing Heuristics

| Trigger | Rule | Trade-off |
|---|---|---|
| Calendar | Rebalance quarterly to fixed weights | Low turnover, may miss extremes |
| Threshold | Rebalance any asset ±5% from target | Better timing, more turnover |
| Volatility | Scale weight by 1/σ, cap weight between 0.5× and 1.5× target | Higher Sharpe, needs leverage/cash |
| Hybrid | Calendar rebalance + ±10% equity weight modulation when Shiller-PE >97th or <3rd pct | Robust, simple |

Rebalancing premium ≈ 0.5 × σ_asset² × (1−ρ) × w_assets × frequency.
Order matters: rebalance the most volatile assets most often.

---

## 6. Long-Horizon Sizing (Merton: w* = (μ−rf) / γσ²)

| Investor | γ | Equity weight | Notes |
|---|---|---|---|
| Kelly (log utility) | 1 | 100% if μ>rf | Extreme drawdowns |
| Retail | 3-5 | 20-33% × Merton | Half Kelly haircut |
| Pension | 2-3 | 50-70% | Add hedging demands |
| Loss-averse | 2.25 (losses) | Half Kelly | Cross-ref Ch 2 |

Long horizon ≠ safer; only rebalancing + vol-scaling add risk-adjusted edge.

---

## 7. PE Selection Rules

| Red flag | Action |
|---|---|
| Self-reported "top quartile" | Demand PME vs public market equivalent |
| IRR > 20% with low TVPI | Inspect cash-flow timing; IRR inflated by early distributions |
| Single-vintage concentration | Cap ≤15% of PE budget per vintage |
| Committing at market peak | Slow pacing; stagger commitments over next 3-5 vintages |
| Reporting net-of-fee = PME-benchmark match | Reject — needs PME >1.2 net of fees |
| Std GP fee >$18/$100 commitment | Require gross alpha ≥6-7% to break even |

---

## 8. Factor Investing Implementation Ladder

```
Tier 0: Cap-weighted global equity + bond benchmark (reference portfolio)
Tier 1: + Value tilt (small value, HML)
Tier 2: + Momentum tilt (12-1 month signal, vol-scaled)
Tier 3: + Low-vol / BAB (long low-beta / short high-beta)
Tier 4: + Quality / profitability (Fama-French 5-factor QMJ)
Tier 5: Macro factors (growth, inflation, real-rate regimes via commodities/real estate/infrastructure)
Tier 6: + True alpha (delegated mandates with >2 t-stat post-factor regression)
```

Each tier must clear Ang's 4-criteria filter and capacity check before adding.

---

## 9. Anti-Patterns Quick Lookup

| Pitfall | Source chapter | Fix |
|---|---|---|
| Time diversification fallacy | Ch 4 | Use rebalancing premium, not horizon |
| Equities = inflation hedge | Ch 8 | Add TIPS / short rates / EM equity |
| Alpha = skill | Ch 10 | Run full factor regression |
| High yield in taxable account | Ch 12 | Asset location → bonds to deferred |
| Fund active share <60% | Ch 16 | Replace with passive ETF |
| IRR > 20% with low multiples | Ch 18 | Compute PME; require ≥1.2 |
| Top-quartile self-report | Ch 18 | External benchmark comparison |
| Star-manager chase | Ch 16 | 5y true-alpha persistence ≥ t-stat 2 |
| Catching-up-with-crowd factor chase | Ch 2 | Monitor factor crowding, second-tier tilt |

---

## 10. Key Formula Reference

| Formula | Use |
|---|---|
| **Merton fraction**: w* = (μ − r_f) / (γ σ²) | Equity weight under CRRA |
| **Gordon**: r = D/P + g | Long-run equity return |
| **Rebalancing premium**: ≈ 0.5 Σ wᵢσᵢ²(1−ρᵢⱼ) | Diversification gain |
| **Kelly**: f* = (bp − q)/b | Bet size at log utility |
| **Tax equivalent yield**: r_taxable = r_muni / (1 − τ) | Muni breakeven |
| **BAB**: r_bab = β_low − β_high | Low-beta minus high-beta return |
| **PME**: Σ CF_PE / Π(1+r_mkt) ≥1 | PE public-market equivalent |
| **Active Share**: 1 − Σ min(w_fund_i, w_index_i) | Distinguishes true active |

---

## 11. Alpha Test Selection

| Test | Use case |
|---|---|
| CAPM | Quick large-cap US screen |
| Fama-French 3 | Default — nets size + value |
| Carhart 4 | Equity funds — adds momentum |
| FF 5 | Quality funds — adds RMW/CMA |
| BAB | Low-vol / defensive funds |
| Sharpe style analysis | Style drift over time |

Rule: require |t| > 2 over ≥5y non-overlapping windows before declaring skill.