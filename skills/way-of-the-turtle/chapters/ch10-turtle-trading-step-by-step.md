# Chapter 10: Turtle-Style Trading: Step by Step

## Core Idea
Simple time-tested methods executed well beat fancy complicated methods every time. Six trend-following systems are compared head-to-head, revealing surprising truths about stops, complexity, and the power of a good entry.

## Frameworks Introduced

### The Six Systems Compared
| System | Entry | Exit | Filter |
|--------|-------|------|--------|
| **ATR Channel Breakout** | Close > 350-day MA + 7 ATR (long); < MA − 3 ATR (short) | Close crosses MA | None |
| **Bollinger Breakout** | Close > 350-day MA + 2.5σ (long); < MA − 2.5σ (short) | Close crosses MA | None |
| **Donchian Trend** | 20-day high breakout (long); 20-day low breakout (short) | 10-day low/high breakout | 350-day/25-day EMA trend filter + 2-ATR stop |
| **Donchian Time Exit** | Same as Donchian Trend | **Time-based: exit after 80 days** | Trend filter, NO stops |
| **Dual Moving Average** | 100-day MA crosses above 350-day MA (long); below (short) | Reverse crossover | Always in market |
| **Triple Moving Average** | 150-day crosses above 250-day (long); below (short) | Reverse crossover | Only if both MAs are on same side as 350-day MA |

### Performance Results (Jan 1996 – Jun 2006)

| System | CAGR% | MAR | Max DD | Trades | Win% |
|--------|-------|-----|--------|--------|------|
| Dual MA | **57.8%** | 1.82 | 31.8% | 210 | 39.5% |
| Donchian Time | 57.2% | 1.31 | 43.6% | 746 | 58.3% |
| Bollinger CBO | 51.8% | 1.52 | 34.1% | 130 | 54.6% |
| ATR CBO | 49.5% | 1.24 | 39.9% | 206 | 42.2% |
| Triple MA | 48.1% | 1.53 | 31.3% | 181 | 42.5% |
| Donchian Trend | 29.4% | 0.80 | 36.7% | 1,832 | 39.7% |

### The Stop Paradox
Adding stops to the Dual Moving Average system **worsened every single metric** — CAGR%, MAR, Sharpe, drawdown, drawdown length. The zero-stop case was optimal. This contradicts the sacred maxim "always use a stop loss." Why?

**Trend-follower drawdowns come from giving back profits during trend reversals, not from entry risk.** Stops protect against entry risk but can't prevent the large equity give-backs when trends end. Worse, stops can prematurely exit trades that later resume trending.

### The 80-Day Time Exit Surprise
The Donchian Time Exit system (no stops, exit after 80 days) outperformed the stop-based Donchian Trend on every metric. **An entry with an edge can account for the entire profitability of a system.**

### November 2006 Shock Update
Adding 5 more months of data (Jul-Nov 2006): the Dual MA system's MAR dropped from 1.82→1.04 (−42.8%) and max DD spiked from 31.8%→47.2%. The Donchian Time Exit showed **zero change** in performance. Simple time-based exits proved more robust.

## Key Concepts
- **The Myth of the Expert**: Pseudo-experts copy rules without understanding why. True experts don't need rigid rules.
- **Entries matter**: The Donchian Time system proves edge can come purely from entry, contrary to "only exits matter" dogma.
- **Complexity ≠ performance**: Triple MA (3 parameters) underperformed Dual MA (2 parameters) for the same reason.
- **Backtesting is the best available tool**: Not perfect, but better than guessing. Use it, don't worship it.

## Anti-patterns
- **"Always use a stop" as dogma**: For long-term trend following with an edge, stops can hurt more than they help.
- **Complexity bias**: Adding rules/indicators hoping to improve performance — usually makes it worse.
- **Overoptimization**: The most dangerous pitfall in backtesting (covered in Ch. 11).
- **Post-hoc rationalization**: Testing until you find what you wanted to find.
- **Short testing periods**: The Nov 2006 shock shows how 5 months can dramatically change perceived performance.

## Key Takeaways
1. Simple systems (Dual MA, time-based exits) outperform complex ones consistently.
2. Stops can reduce returns without reducing drawdowns for trend followers.
3. Time-based exits (80 days) are surprisingly robust — sometimes superior to technical exits.
4. A good entry strategy alone can make a system profitable; exits can be dead simple.
5. Performance metrics are fragile — what looks best in backtest may not hold up out-of-sample.
