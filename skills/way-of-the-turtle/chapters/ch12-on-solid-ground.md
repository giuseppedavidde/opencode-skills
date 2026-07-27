# Chapter 12: On Solid Ground

## Core Idea
Backtesting is at best a rough approximation of future performance. The goal is to maximize predictive power through robust statistical measures, representative sampling, and methods that expose fragility — not to find the "perfect" backtest.

## Frameworks Introduced

### The Problem with Standard Performance Metrics
CAGR%, MAR ratio, and Sharpe ratio are **not robust** — they're extremely sensitive to start/end dates:
- Removing 3 bad months from a 10-year test: CAGR% changed 3.0 percentage points (from 43.2% → 46.2%)
- Same change with RAR%: only 0.11 percentage points — **30× less sensitive**

### RAR% — Regressed Annual Return
- Linear regression through ALL equity curve points (the "best fit" line)
- Eliminates endpoint sensitivity by using the entire curve
- Much more stable and predictive than CAGR%

### R-Cubed (RRRR) — Robust Risk/Reward Ratio
```
R-cubed = RAR% ÷ (Avg Max Drawdown × Avg Drawdown Length / 365)
```
- **Numerator**: RAR% (robust return measure)
- **Denominator**: Average of the **5 largest drawdowns**, length-adjusted
- Accounts for both drawdown **severity** AND **duration**
- A 30% DD lasting 2 months is far less painful than 30% DD lasting 2 years
- Changes ~50% less than MAR ratio under start/end date shifts

### Robust Sharpe Ratio
```
R-Sharpe = RAR% ÷ Annualized StdDev of Monthly Returns
```
Same improvements as RAR% over CAGR%.

### The Four Testing Quality Factors
1. **Number of markets**: More markets = more states of volatility/trendiness represented
2. **Test duration**: Longer = covers more market regimes. "Study history."
3. **Sample size**: >100 trades minimum; >200-300 preferred. Rules affecting <20 trades have no statistical validity.
4. **Representativeness**: Avoid "polling at the Democratic convention" (testing only recent bull markets)

## Key Concepts

### Parameter Scrambling
Change parameters by 20-25% from optimal values. If performance collapses, the system is fragile. Example: Bollinger Breakout optimal (350 MA, −0.8 exit) → scrambled (250 MA, 0.0 exit) dropped R-cubed from 3.67 to 2.18.

### Rolling Optimization Windows
Optimize on 10 years, test forward on 2 years. Repeat sliding forward. This simulates the experience of taking a backtested system live. Results: optimal parameters change each period, and forward performance typically underperforms the backtest by 5-30%.

### Monte Carlo Simulation — Equity Curve Scrambling
Generate "alternative trading universes" by reassembling equity curve in 20-day chunks (preserves autocorrelation of bad days). Key insight: **trade scrambling underestimates drawdowns** because it breaks the correlation between simultaneous adverse moves across markets (e.g., gold, silver, sugar all dropping together in May-June 2006).

### Lucky Systems
A system with exceptional recent performance may just be lucky. Expect suboptimal performance going forward. Regression to the mean is real in trading systems.

## Anti-patterns
- **Single-market optimization**: Too few trades for statistical validity.
- **Overly complex systems**: Many rules affecting few trades = impossible to validate.
- **Short backtests**: Testing only recent data (like polling only Democrats).
- **Ignoring endpoint sensitivity**: Celebrating a strong CAGR% that drops 15% with a 3-month date shift.
- **Trade scrambling Monte Carlo**: Understates real-world drawdowns by destroying cross-market correlation.
- **Trusting non-robust measures**: MAR ratio can change 60% from a single rule affecting 4 trades.

## Key Takeaways
1. Use RAR% instead of CAGR% and R-cubed instead of MAR ratio — they're dramatically more stable.
2. Always parameter-scramble and run rolling optimization windows before going live.
3. Monte Carlo with **equity curve chunk scrambling** (20-day blocks) preserves real-world drawdown characteristics.
4. A backtest is a rough estimate — anyone claiming precision is lying or selling something.
5. Robust measures help avoid overfitting by not rewarding rules that affect only a handful of trades.
