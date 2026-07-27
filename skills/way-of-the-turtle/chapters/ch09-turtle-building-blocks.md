# Chapter 9: Turtle-Style Building Blocks

## Core Idea
All trend-following systems can be built from five elemental building blocks. The specific block chosen matters less than how it's tuned—any block can be adjusted to react faster or slower. Simple, time-tested methods well executed beat complex, novel indicators every time.

## Frameworks Introduced
- **The Five Building Blocks Taxonomy**: (1) Breakouts, (2) Moving Averages, (3) Volatility Channels, (4) Time-Based Exits, (5) Simple Lookbacks. These primitives can be combined to create all major trend-following system architectures.
- **Reactivity Spectrum**: Every building block can be tuned from fast (fewer days, tighter channels) to slow (more days, wider channels). Faster systems capture shorter trends with more whipsaws; slower systems capture longer trends with deeper drawdowns.

## Key Concepts
- **Breakouts**: A new N-day high (long) or low (short) signals potential trend initiation. Fewer days target shorter trends; more days target longer trends. Breakouts work best combined with a trend filter (e.g., Donchian Trend system: 20-day breakout + 50/300 MA filter).
- **Moving Averages**: The crossover of a faster MA above a slower MA generates entry signals. Simple moving averages average N prior closes; exponential moving averages blend prior average with current price for faster response. The 20/70 EMA crossover exemplifies this approach.
- **Volatility Channels**: Plot a moving average ± a volatility multiple (standard deviation or ATR). Price breaking above the upper channel signals an uptrend; below the lower channel signals a downtrend. The channel width adapts to market conditions automatically.
- **Time-Based Exits**: Exit after a fixed number of days regardless of price action. These are the simplest possible exits and can smooth drawdowns because they often trigger before a moving average or breakout exit would reveal the reversal.
- **Simple Lookbacks**: Compare current price to price N days ago. Buy if current price > price[N days ago] + K × ATR. This is trend following reduced to its purest form—no indicators, no crossovers, just direction relative to history.
- **The Building Block Equivalence Principle**: If a market trends, it will eventually trigger a long signal using *any* trend-following building block. Therefore, block choice is less important than consistent application and proper risk management.

## Anti-patterns
- **The Nuclear-Powered Indicator Hunt**: Searching for the "perfect newfangled" indicator that worked flawlessly in backtests. Complex indicators increase curve-fitting risk without improving out-of-sample performance.
- **Ignoring Time-Based Exits**: Dismissing the simplest exit type because it seems "unsophisticated." Time-based exits often reduce drawdowns better than complex trailing stops by exiting before reversals fully manifest.
- **Over-Optimizing Block Parameters**: Tuning breakout days or MA lengths to historical data with precision. The E-ratio framework shows that many parameter ranges produce similar edge; precise optimization reduces robustness.

## Key Takeaways
1. All trend-following systems reduce to five building blocks—master these before inventing new ones.
2. Any block can be tuned fast or slow; the tuning matters more than the block choice.
3. Combine breakouts with trend filters for maximum edge (E70-ratio improvement from 1.20 to 1.33).
4. Time-based exits are deceptively powerful and reduce drawdowns by exiting before trend-following indicators signal.
5. Simple systems well executed outperform complex systems poorly executed.
