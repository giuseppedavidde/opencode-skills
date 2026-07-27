# Way of the Turtle — Cheatsheet

## The 8 Cognitive Biases That Kill Traders

| Bias | Description | Turtle Counter |
|------|-------------|----------------|
| Loss Aversion | Losses hurt 2× more than gains feel good | Accept that 65%+ of trades will lose |
| Sunk Cost | Can't let go of committed money | Exit at predetermined stop, no exceptions |
| Disposition Effect | Sell winners early, hold losers | Let winners run (pyramid); cut losers fast |
| Outcome Bias | Judge decision by result, not process | Evaluate process, not P&L per trade |
| Recency Bias | Recent events weigh too heavily | Look at 10+ year backtests, not last month |
| Anchoring | Fixated on a reference price | Trade what IS happening, not vs. your entry |
| Bandwagon | Follow the crowd | Buy breakouts when others are panicking |
| Law of Small Numbers | Conclusions from too few trades | Require 100+ trades for statistical confidence |

## The Four Market States

| State | Volatility | Trend | Best Strategy |
|-------|-----------|-------|---------------|
| Stable & Quiet | Low | None | Stay out |
| Stable & Volatile | High | None | Countertrend |
| Trending & Quiet | Low | Strong | Trend Following (ideal) |
| Trending & Volatile | High | Strong | Swing Trading |

## Turtle Position Sizing (N Factor)

```
N = ATR(20) in dollar terms
Unit = (1% × Account Equity) ÷ N
Max: 4 units/market, 6/correlated group, 10-12/direction
```

| Account | Gold N=$1,000 | NatGas N=$7,500 | Corn N=$250 |
|---------|---------------|-----------------|-------------|
| $100K | 1 contract | 0 contracts | 4 contracts |
| $500K | 5 contracts | 0 contracts | 20 contracts |
| $1M | 10 contracts | 1 contract | 40 contracts |

## System Selection Decision Matrix

| System | CAGR%* | MaxDD%* | Complexity | Psychological Difficulty |
|--------|--------|---------|------------|--------------------------|
| Dual MA | 49.1% | 47.2% | Very Low | High (large DD) |
| Donchian Time | 57.1% | 43.6% | Low | Medium (no stops!) |
| Bollinger CBO | 49.2% | 34.1% | Medium | Medium |
| ATR CBO | 45.9% | 40.0% | Medium | Medium |
| Triple MA | 41.2% | 42.3% | Medium-High | Medium |
| Donchian Trend | 27.4% | 38.7% | Medium | Low (has stops) |

*Through Nov 2006

## Robust Performance Measures

| Measure | Formula | Why Better |
|---------|---------|------------|
| **RAR%** | Linear regression slope of equity curve | 30× less sensitive to endpoint changes than CAGR% |
| **R-cubed** | RAR% ÷ (Avg 5 largest DD × Avg DD length/365) | Accounts for both DD severity AND duration |
| **R-Sharpe** | RAR% ÷ Annualized StdDev of monthly returns | More stable than Sharpe ratio |

## Backtesting Quality Checklist

- [ ] Test on 20+ uncorrelated markets
- [ ] Minimum 10 years of data (preferably 20+)
- [ ] At least 200-300 trades in sample
- [ ] Use RAR% and R-cubed, not CAGR% and MAR
- [ ] Parameter scramble (±25% from optimal)
- [ ] Rolling optimization windows (10yr test → 2yr forward)
- [ ] Monte Carlo with 20-day equity curve chunk scrambling
- [ ] Stress test against historical price shocks (1987, 2001, 2008, 2020)

## Risk of Ruin Prevention

| Risk Level | % per Trade | Probable Outcome |
|------------|-------------|------------------|
| Conservative | 0.5% | Survive all but nuclear scenarios |
| Moderate | 1.0% | Turtle standard; survived 1987 |
| Aggressive | 2.0% | 50%+ DD in bad years possible |
| Reckless | 3.0%+ | Busted in 1987 simulation |

## The Four Turtle Commandments

1. **Trade with an edge** — Positive expectation over the long run
2. **Manage risk** — Stay in the game to realize the edge
3. **Be consistent** — Execute every signal; the plan means nothing without execution
4. **Keep it simple** — Simple holds up; complex breaks down

## Decision Flow: Should I Take This Trade?

```
1. Does this signal match my predefined entry rules? → NO → Skip
2. Is it in the direction of the dominant trend (if using filter)? → NO → Skip
3. Do I have units available (haven't hit per-market/direction limits)? → NO → Skip
4. Is the position size ≤ 1% of account per unit of risk? → NO → Reduce size
5. Do I know where my stop is (and it's ≤ 2 N away)? → NO → Don't enter
6. Execute. Log the trade. Move on.
```
