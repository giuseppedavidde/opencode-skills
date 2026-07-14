# Chapter 14: Backtest Statistics

## Core Idea
Most backtests report a single Sharpe ratio and ignore everything else. López de Prado makes the case that a backtest must be characterized across **nine families** — general characteristics, performance, runs, implementation shortfall, efficiency, classification scores, attribution — and introduces two robustness correctors: the **Probabilistic Sharpe Ratio (PSR)** and **Deflated Sharpe Ratio (DSR)** that adjust for skewness, length, and the multiple-testing inflation from having tried many strategies.

## Frameworks Introduced
- **Types of backtest statistics**: general characteristics, performance, runs, implementation shortfall, efficiency, classification scores, attribution.
- **Time-weighted vs dollar-weighted average return**: distinction matters when exposure varies over time.
- **Hits and average return from hits**: bets that generated a vs those that did not.
- **Runs statistics (HHI-inspired)**: Herfindahl-Hirschman Index (HHI) of bet-concentration over time; the HHI of returns.
- **Drawdown (DD)**: max loss between consecutive high-watermarks (HWMs); **Time-under-water (TuW)**: duration between HWMs (Figure 14.1).
- **Sharpe Ratio (SR)**: assumes IID Gaussian μ,σ; mis-specified under non-zero skew/kurtosis, autocorrelated returns.
- **Probabilistic Sharpe Ratio (PSR)**: P(SR > SR*) given observed SR, sample length, skewness, kurtosis — penalizes left-skew and short samples.
- **Deflated Sharpe Ratio (DSR)**: PSR where SR* is *estimated* as the expected maximum SR under multiple testing ([0,1] inference threshold that controls for how many strategies were tried).
- **Efficiency statistics**: returns per unit of risk / capital / drawdown.
- **Classification scores**: precision, recall, F1 (critical for meta-labeling where label imbalance dominates).

## Key Concepts
- Returns with negative skewness inflate naive SR — PSR corrects this.
- DSR accounts for the number of trials: the more strategies tried, the higher the SR needed to reject H0: SR=0.
- Runs and HHI reveal whether bets are concentrated (a few huge winners) or diversified.
- Drawdown + time-under-water are path statistics no Sharpe ratio sees.
- For meta-labeling, accuracy is the wrong metric; F1 aligns with the goal of(true positives vs false positives).

## Anti-patterns
- Reporting a single SR with no PSR/DSR and no dispersion (no CPCV from Ch.12).
- Comparing strategies on Sharpe alone when skewness/kurtosis differ.
- Ignoring multiple-testing inflation (run 100 strategies, pick the best → guaranteed false positive).
- Using accuracy (not F1) on imbalanced meta-labeled data.
- Skipping drawdown/TuW — strategies can share SR yet have ruinous tail profiles.

## Key Takeaways
1. Always characterize backtests across the nine families, not just performance.
2. Replace naive SR with PSR, and PSR with DSR once you've tried multiple strategies.
3. Drawdown and time-under-water are essential path statistics.
4. For meta-labeling classifiers, optimize F1, not accuracy.
5. DSR is the quantitative answer to Ch.11's "even a flawless backtest is probably wrong."