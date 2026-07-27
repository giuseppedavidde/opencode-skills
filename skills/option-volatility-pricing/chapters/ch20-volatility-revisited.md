# Chapter 20: Volatility Revisited

## Core Idea
Volatility forecasting is the critical challenge in option trading: the longer a position is held, the more important realized volatility becomes, and the less important implied volatility becomes. Understanding volatility characteristics (serial correlation, mean reversion, term structure) and forecasting methods (weighted averages, EWMA, GARCH) is essential for selecting the right volatility input.

## Frameworks Introduced
- **Realized vs. Implied Dominance Principle**: Over short holding periods, implied volatility changes dominate P&L. Over long holding periods (to expiration), only realized volatility matters
- **Three Volatility Characteristics**: (1) Serial correlation — tomorrow's volatility tends to resemble today's; (2) Mean reversion — volatility oscillates around a long-term average; (3) Term structure — volatility estimates converge as measurement period lengthens
- **Historical Volatility Calculation Methods**: Close-to-close (standard), Parkinson (high-low extreme value), Garman-Klass (open-high-low-close). Parkinson and Garman-Klass are more accurate for continuously traded markets but require weighting adjustments for markets with closed hours
- **Volatility Forecasting Approaches**: (1) Simple average of historical vols, (2) Recency-weighted (more weight to recent data), (3) Regressive weighting (decaying weights), (4) Serial-correlation matching (match forecast period to historical period), (5) EWMA (exponentially weighted moving average), (6) GARCH (incorporates correlation and mean reversion)
- **Implied Volatility as Predictor**: Under normal conditions, implied vol tends to overstate future realized vol (options are "overpriced insurance"). During volatility explosions, implied vol dramatically understates. Implied vol is at best an imperfect predictor

## Key Concepts
- **Volatility Calculation**: Sample standard deviation (n−1 denominator) preferred for forecasting. Use logarithmic returns: `ln(P_i/P_i−1)`. Zero-mean assumption (μ=0) is standard practice
- **Trading Days vs. Calendar Days**: 250-260 trading days/year vs. 365 calendar days. Using calendar days assigns zero change to weekends — differences are negligible for general forecasting
- **Interval Choice**: Daily, weekly, or monthly returns yield similar volatility profiles. Daily returns preferred for more data points (smoothing effect)
- **Term Structure of Volatility**: Cone-shaped graph — short periods show wide min-max spread (~5% to 100% for S&P over 2 weeks), long periods converge to mean (~14-24% over 300 weeks). Easier to predict long-term volatility than short-term
- **Volatility-Weather Analogy**: Like temperature, volatility is serial correlated (tomorrow like today), mean reverting (extreme = temporary), and has seasonal/cyclical patterns
- **Forecast Weighting Logic**: Match historical data period to option life — for 3-month options, weight 12-week historical vol highest; for 12-month options, weight 52-week highest
- **EWMA Model**: `σ²_t = λσ²_t−1 + (1−λ)r²_t`. λ≈0.94 common. More recent returns get exponentially greater weight
- **GARCH Family**: Three components: base volatility estimate (like EWMA) + return correlation (large→large, small→small) + mean reversion speed
- **Implied Volatility Lag**: S&P data shows realized vol leads implied vol; market reacts to, rather than anticipates, volatility changes
- **Long-term Vega Risk**: Long-term options have more stable vol forecasts but vastly greater vega sensitivity — a 2-3 point vol error on LEAPS can exceed a 5-6 point error on near-term options

## Anti-patterns
- **Ignoring volatility characteristics in forecast**: Using only recent data for long-term options (violates mean reversion) or only long-term data for short-term options (misses serial correlation)
- **Assuming implied vol predicts perfectly**: Implied vol is systematically too high in normal markets and dramatically too low during crises — it is reactive, not predictive
- **Using population standard deviation (divide by n)**: Always use sample standard deviation (n−1) unless you have the entire population of data
- **Neglecting the term structure**: Short-term volatility can be 2-3× long-term volatility; failing to respect term structure causes systematic mispricing of different expirations
- **Overcomplicating calculation method**: Close-to-close, Parkinson, Garman-Klass produce similar results — interpretation matters more than method choice
- **Treating volatility like price**: Price trends can persist indefinitely; volatility mean reverts. Applying identical technical analysis rules to both is misguided

## Key Takeaways
1. `Realized vol dominance` increases with holding period; at expiration, only realized vol matters — implied vol changes are interim noise
2. Volatility has three reliable characteristics: serial correlation, mean reversion, term structure convergence
3. Match forecasting method to option life: weight closest historical period highest, then decay weights for more distant periods
4. The volatility cone (term structure graph) shows that long-term vol predictions are more stable but also more impactful due to higher vega
5. No forecasting method is perfect — implied vol systematically overprices in calm markets and underprices in crises. The best approach combines historical patterns with current implied vol
