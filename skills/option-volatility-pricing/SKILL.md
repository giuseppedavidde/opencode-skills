---
name: option-volatility-pricing
description: "Knowledge base from 'Option Volatility and Pricing' by Sheldon Natenberg. Advanced trading strategies and techniques, 2nd Edition."
allowed-tools: [read, grep]
argument-hint: [topic, framework, or chapter number]
---

# Option Volatility and Pricing (2nd Edition)
**Author**: Sheldon Natenberg | **Chapters**: 25 | **Generated**: 2026-07-27

## Core Frameworks & Mental Models

This book is the definitive practitioner's guide to option theory and trading. Natenberg's approach weaves together theoretical pricing, volatility analysis, dynamic hedging, and risk management into a coherent framework for professional option trading.

### The Central Organizing Principle
All option trading decisions flow from one question: **Is implied volatility higher or lower than your forecast of future realized volatility?** Every strategy, every spread, every hedge must be evaluated against this comparison.

### 1. Forward Pricing & Arbitrage Foundation (Ch. 2-4)
- Forward price = Cash price + Costs − Benefits. This is the anchor for all option valuation
- Forward price, not spot price, determines expected value at expiration — options are priced off the forward
- Parity graphs and expiration P&L diagrams are the diagnostic tools for understanding any position
- Slope analysis: any position decomposes into linear segments between exercise prices

### 2. Theoretical Pricing Model Architecture (Ch. 5, 18-19)
- **Expected Value = Σ(intrinsic value_i × probability_i)**, discounted to present value
- Black-Scholes decomposes this into two questions: (1) average stock value above strike, (2) probability of paying the strike
- Five inputs: S, X, t, r, σ — only σ is unobservable
- Model variants (Black-Scholes stock, Black futures, Garman-Kohlhagen currency) differ only in forward price calculation and cost-of-carry parameter (b)
- Binomial model: discrete-step alternative, converges to Black-Scholes as steps → ∞
- At-the-forward approximation: EV ≈ 0.004 × F × σ × √t ("40% rule")

### 3. Volatility — The Central Variable (Ch. 6, 20)
- Volatility = annualized standard deviation of percent price changes (σ)
- Three interpretations: historical (realized past), future (realized expected), implied (market price embedded)
- Scaling: σ_period = σ_annual × √t (divide by 16 for daily, 7.2 for weekly)
- Three reliable characteristics: serial correlation, mean reversion, term structure convergence
- Implied volatility systematically overprices in normal markets, dramatically underprices during crises — it is reactive, not predictive
- Forecasting: match historical data period to option life, weight recent data higher for short-term, weight mean reversion for long-term

### 4. Risk Measurement — The Greeks (Ch. 7, 9)
- **Delta (Δ)**: Rate of change vs. underlying. N(d1) in Black-Scholes. Ranges 0 to 100 for calls, −100 to 0 for puts
- **Gamma (Γ)**: Rate of delta change. Always positive for long options. Highest ATM. Creates curvature P&L
- **Theta (Θ)**: Daily time decay. Always negative for long options. Highest ATM. Three components: volatility decay, spot-to-forward drift, PV discounting
- **Vega (ν)**: Sensitivity to 1% IV change. Always positive for long options. Highest ATM. Proportional to √t
- **Rho (ρ)**: Interest rate sensitivity. Least important Greek for most strategies
- Higher-order: Vanna (Δ sensitivity to σ), Charm (Δ sensitivity to t), Speed (Γ sensitivity to S)

### 5. Dynamic Hedging — The Replication Engine (Ch. 8)
- Delta-neutral hedging + periodic rebalancing replicates option payoff through mechanical buy-low-sell-high
- Option value ≈ Σ(adjustment profits) — the sum of all gamma scalps equals the time premium
- Breakeven volatility = implied volatility at trade entry; above = profit, below = loss
- Five P&L components: original hedge, adjustments, option carry, underlying carry/interest, dividend flows
- Holding period determines iV vs. rV dominance: short-term = IV matters, to expiration = only rV matters

### 6. Spreading — The Risk Control Framework (Ch. 10-14)
- Spreading maintains probability edge while reducing short-term variance (casino analogy)
- Volatility spreads (straddles, strangles, butterflies, condors, ratio spreads) trade gamma/theta/vega
- Directional spreads (bull/bear verticals) trade delta — never invert
- **Golden Rule**: IV low → buy ATM option, IV high → sell ATM option, then complete the spread
- Synthetics: +C −P = +Underlying. Companion calls and puts have identical gamma and vega
- Iron butterfly = credit equivalent of debit butterfly. Any strategy can be constructed multiple ways

### 7. Forward Pricing for Different Underlyings (Ch. 2, 22)
- Stocks: F = S(1 + rt) − D (dividends are benefits of ownership)
- Futures: F = futures price (trivially, the forward is the futures price)
- Physical commodities: F = C(1 + rt) + storage + insurance − convenience yield
- Bonds/Notes: F = B(1 + rt) − coupon payments with interest
- Foreign currencies: F = S × (1 + r_domestic × t) / (1 + r_foreign × t)
- Stock indexes: F = S × [1 + (r − d) × t] where d = annualized dividend yield

### 8. Early Exercise & American Options (Ch. 16)
- Stock calls: only exercise day before ex-dividend, when Dividend > Vol value + Interest
- Stock puts: exercise when Interest > Vol value + Dividend; blackout period = Dividend ÷ daily interest
- Futures options (stock-type settlement): exercise when Interest on intrinsic > Vol value; requires daily theta < daily interest
- Futures options (futures-type settlement): never exercise early — American = European
- Lower arbitrage boundaries: American ≥ max[0, intrinsic, European boundary]

### 9. Volatility Skews & the Surface (Ch. 24)
- Three skew types: Investment (puts bid — stocks), Demand (calls bid — commodities), Balanced (symmetrical — currencies)
- Skew model: y = a + bx + cx² where a = ATMI V, b = skewness (tilt), c = kurtosis (curvature)
- Moneyness calibration (sticky-delta): express strikes in σ√t terms for cross-expiration comparison
- Skewed risk measures: delta, gamma, vega all change when skew is included in the model
- Risk reversals trade skewness; strangle+straddle combos trade kurtosis
- The volatility surface (skew × term structure) is the professional's complete map

### 10. Risk Analysis & Position Management (Ch. 13, 21)
- Risk-reward tradeoff: theoretical edge must be weighed against all risk dimensions simultaneously
- Six risk categories: delta, gamma, theta, vega, rho, and skew/kurtosis
- Scenario analysis: stress-test positions across underlying price, time, IV, and skew changes
- Position sizing: margin for error in volatility estimate determines maximum position size
- Professional vs. retail: same expected edge, but professionals adjust more frequently → lower variance

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|---------------|
| 1 | Financial Contracts | Calls, puts, exercise, assignment, underlying, expiration |
| 2 | Forward Pricing | Forward price formula, cash-and-carry, contango/backwardation, implied values |
| 3 | Contract Specifications & Terminology | Type, underlying, expiry, exercise style (European/American), settlement types |
| 4 | Expiration Profit & Loss | Parity graphs, hockey-stick diagrams, slope analysis, breakeven calculations |
| 5 | Theoretical Pricing Models | Expected value, probability distributions, riskless hedge, model inputs overview |
| 6 | Volatility | Random walks, normal/lognormal distributions, σ scaling (√t rule), realized vs. implied |
| 7 | Risk Measurement I | Delta, gamma, theta, vega, rho — definitions, interpretations, and base calculations |
| 8 | Dynamic Hedging | Delta-neutral hedging, rebalancing, replication, breakeven volatility, P&L components |
| 9 | Risk Measurement II | How Greeks change with S/t/σ, vanna, charm, speed, color, gamma/vega decay |
| 10 | Introduction to Spreading | Spread definition, intramarket/intermarket spreads, ratio strategies, option spreads |
| 11 | Volatility Spreads | Straddles, strangles, butterflies, condors, ratio spreads, Christmas trees |
| 12 | Bull and Bear Spreads | Naked positions, ratio spreads with bias, vertical spreads, ATM selection rule |
| 13 | Risk Considerations | Risk-reward tradeoff, comparing strategies, theoretical edge vs. risk limits |
| 14 | Synthetics | Synthetic underlying, synthetic options, iron butterfly/condor, Christmas tree decomposition |
| 15 | Option Arbitrage | Put-call parity, conversions/reversals, box spreads, settlement risk |
| 16 | Early Exercise of American Options | Arbitrage boundaries, stock call/put criteria, futures options, protective value |
| 17 | Hedging with Options | Protective puts, covered calls, collars, static vs. dynamic hedging |
| 18 | The Black-Scholes Model | d1/d2 derivation, N(x) probability functions, delta= N(d1), theta components, vega decay |
| 19 | Binomial Option Pricing | Cox-Ross-Rubinstein model, convergence to BS, American option valuation |
| 20 | Volatility Revisited | Historical vol calculation, vol characteristics, forecasting (EWMA, GARCH), term structure |
| 21 | Position Analysis | Multi-dimensional risk analysis, scenario stress testing, position Greeks |
| 22 | Stock Index Futures & Options | Index construction, dividends, program trading, futures delta, AM/PM settlement |
| 23 | Models and the Real World | Model limitations, non-normal distributions, CEV, stochastic vol, jump-diffusion |
| 24 | Volatility Skews | Skew types, modeling (sticky-strike/floating/sticky-delta), skewness, kurtosis, surface, risk reversals |
| 25 | Volatility Contracts | Variance swaps, VIX futures/options, volatility contract replication and applications |

---

## Topic Index

| Topic | See Chapters |
|-------|-------------|
| Arbitrage / Put-Call Parity | 2, 15, 16 |
| Black-Scholes Model | 5, 6, 18 |
| Delta / Directional Risk | 4, 7, 9, 12 |
| Dividends | 2, 16, 22 |
| Dynamic Hedging | 8, 10 |
| Early Exercise | 16 |
| Forward Pricing | 2, 15, 22 |
| Gamma / Curvature | 7, 9, 11 |
| Hedging (Protective) | 17 |
| Implied Volatility | 6, 20, 24 |
| Index Futures/Options | 22 |
| Kurtosis | 23, 24 |
| Lognormal Distribution | 6, 18 |
| Position Analysis / Risk | 13, 21 |
| Probability / Expected Value | 5, 18 |
| Realized / Historical Vol | 6, 20 |
| Rho / Interest Rate Risk | 7, 13 |
| Settlement (Stock vs. Futures) | 3, 8, 15, 16 |
| Skew (Volatility) | 24 |
| Spreading Strategies | 10, 11, 12 |
| Straddles / Strangles | 11 |
| Synthetics | 14, 15 |
| Term Structure (Vol) | 20, 24 |
| Theta / Time Decay | 7, 9 |
| Vega / Volatility Risk | 7, 9, 13 |
| Vertical Spreads | 12 |
| Volatility Forecasting | 20 |
| Volatility Surface | 24 |

---

## Supporting Files
- [glossary.md](glossary.md) — Alphabetical glossary of all key terms (managed by Agent A)
- [patterns.md](patterns.md) — Strategy patterns with When/How/Trade-offs framework
- [cheatsheet.md](cheatsheet.md) — Quick-reference tables, formulas, and decision rules
