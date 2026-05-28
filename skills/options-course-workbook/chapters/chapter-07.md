# Chapter 7: The Other Greeks

## Core Idea
Beyond delta, three other Greeks measure risk: **gamma** (rate of delta change), **theta** (time decay), and **vega** (volatility sensitivity). Together they quantify how options prices respond to price, time, and volatility changes.

## Frameworks Introduced
- **Gamma**: Rate of change of delta per $1 move in underlying. Highest for ATM options. High gamma = delta can change rapidly
- **Theta**: Daily time decay. Negative for long options (losing value each day). Positive for short options (gaining value each day). **Accelerates in the last 30 days**
- **Vega**: Price change per 1% change in implied volatility. Critical for understanding IV expansion/contraction
- **Intrinsic vs Extrinsic Value**: Intrinsic = ITM amount (time-independent). Extrinsic = time value (erodes via theta). ATM/OTM options are 100% extrinsic
- **Volatility Types**: Historical (HV) = past price movement standard deviation. Implied (IV) = market's expected future volatility derived from option prices

## Key Concepts
- Seven option pricing components: underlying price, strike, type, time, interest rate, volatility, dividends
- **Volatility crush**: IV drops sharply after events (earnings, FDA decisions) — can cause losses even when direction is correct
- **Mean reversion of IV**: IV stretches like elastic — buy when low, sell when high
- Options are **wasting assets** due to theta; don't hold long options past 30 DTE

## Key Takeaways
1. Buy options when IV is **low** (vega works in your favor); sell options when IV is **high**
2. Never buy options with <30 DTE — theta decay accelerates dramatically
3. The deeper ITM, the less theta matters; the more OTM, the more theta is a problem
4. Black-Scholes model computes theoretical prices; actual price vs theoretical reveals IV opportunities
