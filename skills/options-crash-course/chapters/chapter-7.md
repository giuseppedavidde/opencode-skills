# Chapter 7: Options Trading Strategies for Experts

## Core Idea
Choose strategies that match your market outlook and risk tolerance. Each strategy has a specific market condition where it shines. Advanced traders also have repair strategies for when trades go wrong — the secret to long-term success is recovering from losses, not avoiding them entirely.

## Frameworks Introduced
- **Strategy-Market Fit** — Every strategy is designed for a specific market condition (bullish, bearish, neutral, volatile). Using the wrong strategy for the current market is the #1 mistake.
- **Repair Framework** — When a trade has unrealized losses, use repair strategies (rolling down, butterfly conversion) to lower breakeven points rather than accepting full loss. Works best when loss <70% of position.
- **Delta Hedging** — Hedge directional risk by shorting the underlying stock in proportion to the option's delta.
- **Synthetic Short** — Replicate short stock payoff by selling ATM calls and buying ATM puts.

## Key Concepts
- **Covered Call (Buy/Write)**: Own stock + sell call. Generates premium income. Bearish/bullish. Suitable for everyone.
- **Married Put**: Own stock + buy put. Insurance against downside. Bullish. Protects against sudden drops.
- **Bull Call Spread**: Buy low-strike call + sell higher-strike call. Bullish. Limited risk, limited profit.
- **Bear Put Spread**: Buy high-strike put + sell lower-strike put. Bearish. Limits losses, caps gains.
- **Protective Collar**: Own stock + buy OTM put + sell OTM call. Bullish/bearish. Locks in profits with small fee.
- **Long Straddle**: Buy ATM call + ATM put. Expects big move in either direction.
- **Short Straddle**: Sell ATM call + ATM put. Expects low volatility (collects premium).
- **Long Strangle**: Buy OTM call + OTM put. Cheaper than straddle. Expects big move.
- **Butterfly Spread**: 3 strike prices — buy lowest call, sell 2 middle calls, buy highest call. Neutral market, low volatility.
- **Iron Condor**: Two credit spreads (put side + call side). Low volatility. Best with index options.
- **Iron Butterfly**: Short straddle plus protective strangle. Limits loss around strike price.
- **Repair Strategies**: Roll down into bull call spread or butterfly to lower breakeven.

## Anti-patterns
- Using complex strategies (iron condor, butterfly) before mastering simple ones
- Repairing losses >70% (generally impossible to recover)
- Buying/writing options without understanding max loss
- Using short straddles/strangles in high-volatility environments (unlimited loss)
- Ignoring the time decay (theta) effect on long option positions

## Key Takeaways
- Match strategy to market condition, not your ego
- Covered calls and married puts are the safest starting strategies
- Repair strategies can rescue losing trades if caught early enough
- Synthetic short has unlimited upside potential AND unlimited loss risk
- The iron condor requires index options and low volatility to work
- Rolling down a losing call into a bull call spread lowers the breakeven
