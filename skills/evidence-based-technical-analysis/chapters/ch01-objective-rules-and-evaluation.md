# Chapter 1: Objective Rules and Their Evaluation

## Core Idea
Technical analysis can only produce valid, testable knowledge when its methods are reduced to **objective binary signaling rules** — precisely defined, programmable functions that transform market data into unambiguous trading signals. Subjective TA is inherently untestable and thus incapable of generating legitimate knowledge.

## Frameworks Introduced

### 1. The Programmability Criterion
The acid test for objectivity: a TA method is objective **if and only if** it can be implemented as a computer program producing unambiguous market positions (long, short, neutral). Everything else is subjective by default.

### 2. Binary Rule Architecture
A rule is a function mapping input time series → mathematical/logical operators → output time series of market positions (+1 long, -1 short). A **signal** is generated when the output value changes, calling for a position adjustment. Thresholds define when inputs cross into signal territory. The simplest form is the binary rule (two output values), but complex rules can produce graduated position sizes.

### 3. Expected Return and Position Bias
The expected return of a nonpredictive rule is determined entirely by its position bias and the market trend:
```
ER = [p(Long) × ADC] − [p(Short) × ADC]
```
Two rules with identical (zero) predictive power but different long/short biases will produce dramatically different back-tested returns in a trending market — creating the **illusion of skill**.

### 4. Detrending as Universal Benchmark
Rather than computing a custom benchmark for each rule's position bias, detrend the market data so its mean daily change is zero. Any rule's performance on detrended data then reflects only its genuine predictive power, free from the confounding effects of position bias and historical market trend.

## Key Concepts
- **Objective vs. Subjective TA**: Only objective rules can be back-tested and statistically evaluated; subjective methods are immune to falsification
- **Fixed vs. Multiple Thresholds**: Single thresholds define reversal rules; multiple thresholds create zones where existing positions are held (reducing whipsaws)
- **Traditional vs. Inverse Rules**: Both must be tested since it is not known a priori whether the conventional interpretation is correct
- **Trading Costs**: Must be incorporated into evaluation — a rule with marginal edge can be rendered unprofitable by transaction costs
- **Look-Ahead Bias**: Using information not available at the time of signal generation produces unrealistically optimistic results

## Anti-patterns
- **Cherry-picking thresholds**: Choosing threshold values after seeing the data without adjusting significance tests for data mining
- **Ignoring position bias**: Attributing a rule's profits to predictive power when they simply reflect a long bias in a bull market
- **Neglecting inverse rules**: Assuming the traditional interpretation of an indicator is correct without testing the inverse
- **Single-market myopia**: Testing rules on one market/period and assuming generalizability
- **Cost-free backtesting**: Evaluating rules without realistic transaction costs, slippage, and liquidity constraints

## Key Takeaways
1. Objectivity is a **prerequisite** for scientific evaluation — without it, there's nothing to test.
2. The programmability criterion is the definitive litmus test separating science from art in TA.
3. Position bias interacting with market trend is the single greatest source of **illusory performance** in back-testing.
4. Detrending market data provides a clean, universal solution to the benchmarking problem.
5. A rule's back-tested return is a **sample statistic**, not a population parameter — sampling error always creates uncertainty about future performance.
