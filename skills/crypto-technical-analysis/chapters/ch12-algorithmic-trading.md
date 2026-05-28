# Chapter 12: Algorithmic Trading

## Core Idea
Algorithmic trading uses computer programs to execute trades based on predefined rules. The goal is a 24/7 money-making machine, but practical challenges (errors, slippage, adaptability, self-destruction) prevent it from being easy money.

## Frameworks Introduced
- **Rules → Code → Execute**: Convert trading strategy into algorithmic rules, code them, let the bot run
- **51% Rule**: An algorithm correct 51% of the time at 5%/5% win/loss can theoretically compound massively
- **Backtesting → Forward Testing → Live**: Test against historical data, then paper trade, then deploy small

## Key Concepts
- **Backtesting**: Run algorithm against historical data to validate profitability
- **Split-Testing**: Compare different parameter sets to optimize
- **Risk Control**: Stop-losses and trailing stops are essential in automated trading
- **Simplicity**: Most successful algorithms use 1-2 indicators, not complex multi-layered systems
- **Challenges**: Errors in code, unpredictable events (black swans), lack of adaptability, slippage/volatility, self-destruction of profitable strategies

## Crypto-Specific Considerations
- Crypto is 24/7—algorithms can trade while you sleep, a major advantage
- Higher volatility means more slippage risk for bots (especially on altcoins)
- HFT is moving into crypto but hasn't reached stock-market saturation yet—early opportunity
- Many crypto-exchanges offer API access specifically for bot trading
- Backtesting in crypto has limited data (shorter history than stocks); results may not generalize
- Algorithmic trading resources specific to crypto: Trality, 3Commas, Cryptohopper, Bitsgap, Hummingbot

## Key Takeaways
- Simple algorithms (1-2 indicators) outperform complex ones
- Backtest thoroughly but expect real-world results to differ
- 51% accuracy with proper risk management is enough for profitability
- Crypto's 24/7 nature makes bots more valuable than in traditional markets
- Self-destruction problem: profitable strategies stop working once widely adopted
