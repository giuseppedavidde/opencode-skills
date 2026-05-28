# Chapter 5: Position & Money Management

## Core Idea
Even a great strategy fails without solid risk management. Position management protects individual trades; money management protects the entire account.

## Frameworks Introduced
- **Fixed vs Volume-based PT/SL**: Fixed uses ATR (same for all trades), Volume-based uses VP structures (differs per trade)
- **Alternative SL Approach**: Exit only when candle closes past SL — prevents SL hunts. Use with "Catastrophic SL" at 150%
- **SL Management Styles**: Aggressive (never move SL), Neutral (move SL to reaction at 70-80% PT), Conservative (move to BE at 70-80% PT)
- **RRR (Risk Reward Ratio)**: Preference for 1:1. Higher RRR = lower strike rate.

## Key Concepts
- **Fixed PT/SL**: ATR(200) on daily × 10,000 = pips. Intraday = 10-20% of daily ATR. Simplifies decisions
- **Volume-based PT**: Place PT a few pips before the first heavy volume zone in the way. If too close (<10% daily ATR), skip trade
- **Volume-based SL**: Place behind volume clusters where volumes are lowest. Consider volatility — may need 2nd closest zone if too tight
- **Alternative SL**: Position closes only on candle close past SL. Catastrophic SL at 150% ensures max loss is capped
- **Quitting Early (BE Exit)**: If price rotates near your level with no rejection, exit at BE. The level may flip to resistance/support. Do it fast — BE opportunities last seconds. Use PT order set at BE for automatic execution.
- **Risk per Trade Formula**: Backtest max drawdown → multiply by 1.2 (20% safety) → divide by number of consecutive losses → divide into tolerable account loss % → yields risk % per trade
- **Risk per Trade Example**: $10,000 account, tolerable loss = 25% ($2,500), max backtest drawdown = 6 losses, with safety = 7.2 losses. Risk per trade = $2,500 / 7.2 = $347 ≈ 3.47% per trade
- **Position Sizing Rule**: Same size for same trade type. Never vary by "feeling." Different types can have different sizes (intraday = 2%, reversal = 1%, swing = 3%).
- **High Water Mark Method**: Calculate position size based on account balance at start of month. Only increase when a new month-end high is set. Never decrease during drawdown — this slows recovery.
- **Correlation Risk**: If two heavily correlated instruments have similar levels triggering simultaneously, halve both position sizes. Max 2 USD-denominated positions at once. USD rally can hit all USD pairs simultaneously.
- **Stop-Loss Management Comparison**:
  - Aggressive: Set SL and never move it. Two outcomes: full SL or full PT. Best for Asian session when asleep.
  - Neutral: Move SL to reaction point when price reaches 70-80% of PT. Preferred for EU/US sessions. Balances risk and reward.
  - Conservative: Move SL to BE at 70-80% of PT. Ensures no loss. But many profitable trades exit early — price often returns to entry before continuing.
- **Time Factor in RRR**: Longer position duration = higher chance of unexpected events (news, sentiment shifts). 1:1 RRR minimizes time exposure vs higher RRR targets.

## Key Takeaways
- Neutral SL approach (move to reaction at 70-80%) is the preferred method
- Volume-based SL in low-volume areas prevents being stopped by normal volatility
- Trade all valid levels regardless of current P/L streak
- 1:1 RRR preferred — it balances strike rate and time exposure
