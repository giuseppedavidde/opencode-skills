# Chapter 5: Trading with an Edge

## Core Idea
An edge is measurable, not mystical. Through the E-ratio framework—comparing maximum favorable excursion (MFE) to maximum adverse excursion (MAE)—traders can quantify whether an entry signal has predictive power and over what time horizon that power manifests.

## Frameworks Introduced
- **E-Ratio (Edge Ratio)**: E-ratio = avg volatility-adjusted MFE / avg volatility-adjusted MAE over N days. An E-ratio > 1.0 indicates positive edge; random entries yield ~1.0. The time subscript (E5, E10, E70) indicates measurement horizon.
- **MAE/MFE Analysis**: Maximum Adverse Excursion = worst drawdown before profit; Maximum Favorable Excursion = best profit before drawdown. Their ratio reveals whether price movement favors the direction of the signal.
- **Time-Frame Edge Matching**: An entry signal must have edge over the system's intended holding period, not all periods. Short-term countertrend strategies can profit from the *absence* of medium-term edge in breakouts.

## Key Concepts
- **Donchian Channel Breakout Edge Profile**: The 20-day breakout has E5-ratio = 0.99 (no short-term edge) but E70-ratio = 1.20 (20% more favorable than adverse movement over 70 days). This explains why breakouts are psychologically difficult—they initially move against you.
- **Trend Portfolio Filter Amplification**: Adding a 50-day > 300-day moving average filter to random entries produces E70-ratio = 1.27, exceeding the breakout entry's standalone edge. The filter alone provides more edge than the entry signal.
- **Combined Filter + Breakout**: E70-ratio rises to 1.33, and E120-ratio reaches ~1.6 with smoothing. Filtering out counter-trend breakouts eliminates the trades most likely to reverse significantly.
- **Exit Edge Asymmetry**: Measuring exit edge is harder than entry edge because exits depend on entry conditions. However, exits also require edge since they determine what portion of favorable excursion is captured.

## Anti-patterns
- **Expecting Edge at All Time Frames**: Assuming a medium-term trend system should show positive E-ratios at 5 days. Edge is time-horizon specific; near-term adverse movement is normal and expected.
- **Ignoring the Countertrend Perspective**: The initial adverse movement in breakouts creates a *real* edge for countertrend traders who bet on the breakout failing. Both sides can have edge at different time frames.
- **Over-weighting Entry Edge**: The trend portfolio filter contributes as much or more edge than the entry signal itself. Obsessing over entry precision while neglecting portfolio-level filters is suboptimal.

## Key Takeaways
1. The E-ratio provides a quantitative, cross-market-comparable measure of entry edge.
2. Breakout entries have negative short-term edge but strong medium-term edge (E70 = 1.20+).
3. A simple trend portfolio filter (50 MA > 300 MA) alone provides significant edge.
4. Edge is time-horizon dependent—match your measurement window to your system's holding period.
5. Understanding where your edge comes from (entry vs. filter vs. exit) enables better system design.
