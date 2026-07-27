---
name: evidence-based-technical-analysis
description: "Knowledge base from 'Evidence-Based Technical Analysis' by David R. Aronson. Scientific method and statistical inference for trading signals, data-mining bias, White's Reality Check, hypothesis testing, and objective TA evaluation."
allowed-tools: [read, grep]
argument-hint: [topic, framework, or chapter number]
---

# Evidence-Based Technical Analysis

## Book Overview

David Aronson's *Evidence-Based Technical Analysis* applies the scientific method and formal statistical inference to the evaluation of technical trading rules. The book's central thesis: traditional subjective TA is untestable folklore contaminated by cognitive biases, and even objective TA suffers from data-mining bias — the systematic overstatement of a rule's future performance caused by selecting the best performer from many candidates. The solution is rigorous statistical methodology that accounts for randomness, the number of rules tested, and the non-stationary nature of financial markets.

The book culminates in a case study testing 6,402 individual TA rules on the S&P 500 (1980-2005) using two data-mining-aware statistical methods: White's Reality Check and Masters' Monte Carlo Permutation.

## Core Frameworks

### 1. The Null Hypothesis Default
All rule evaluation must begin with H₀: the rule has no predictive power (expected return = 0 on detrended data). Only evidence that is highly improbable under this assumption warrants rejecting the null. This is the scientific method applied to trading.

### 2. The Data-Mining Bias Correction
When N rules are tested and the best is selected, the observed performance is an upwardly biased estimator of expected future performance. The correction requires constructing a sampling distribution for the **maximum** performance across N useless rules, not the distribution for a single rule. White's Reality Check (bootstrap-based) and Masters' Monte Carlo Permutation are two valid methods.

### 3. The Detrending Principle
All rule evaluation must be performed on **detrended** market data (zero-mean returns). This eliminates the confounding effect of position bias: a rule that is long 80% of the time will profit in any bull market regardless of predictive power. Detrending is mathematically equivalent to benchmarking against position bias.

### 4. The Illusion of Validity Model
Subjective TA's apparent validity is produced by a network of cognitive biases (overconfidence, confirmation, hindsight, self-attribution, illusory correlation, illusion of control) that are hardwired into human cognition. These biases operate automatically and cannot be "thought away" — only objective, algorithmic methods can circumvent them.

### 5. The Configural Thinking Limit
Human information processing can handle at most 3 variables in a configural (interactive) fashion. Financial market prediction with 5+ indicators vastly exceeds this capacity. Statistical models — consistent, formal, tireless — outperform human experts in 96% of studied domains.

### 6. Statistical vs. Practical Significance
A rule can be statistically significant (p < 0.05) while being economically worthless. Practical significance depends on expected return after costs, drawdown tolerance, capacity constraints, and the trader's required rate of return. Both must be evaluated separately.

### 7. Occam's Razor in Rule Selection
When multiple explanations fit the data, prefer the one with the fewest assumptions. Data-mining bias (luck + selection) explains out-of-sample performance deterioration more parsimoniously than "market dynamics changed" — it requires no assumption about the market.

## Chapter Index

### Chapter 1: Objective Rules and Their Evaluation
Defines objective vs. subjective TA. Introduces detrending, position bias, and the need to evaluate rules on zero-mean market data. Establishes that a rule must be algorithmically defined to be testable. Covers benchmark selection and the distinction between market benchmarks and random-signal benchmarks.

### Chapter 2: The Illusory Validity of Subjective Technical Analysis
Documents how cognitive biases (overconfidence, confirmation, hindsight, self-attribution, illusory correlation, illusion of control, representativeness heuristic) create an illusion of validity for untestable subjective methods. The human mind is a "natural pattern finder" that evolved to prefer false positives over false negatives. Subjective TA is "worse than wrong" — it is meaningless because it cannot be falsified.

### Chapter 3: The Scientific Method and Technical Analysis
Applies Popperian falsification to TA. Distinguishes deductive from inductive reasoning. Covers the logical fallacy of affirming the consequent, the principle of falsifiability, and Occam's Razor. Argues that TA must operate like science: propose falsifiable hypotheses, test with data, abandon what fails.

### Chapter 4: Statistical Analysis
Introduces the sampling paradigm, probability density functions, null hypothesis testing, p-values, the Law of Large Numbers, and the Central Limit Theorem. Covers performance statistics (mean return, Sharpe ratio, profit factor, Ulcer Index). The bead-box thought experiment teaches the core concept: sample statistics estimate population parameters with quantifiable uncertainty.

### Chapter 5: Hypothesis Tests and Confidence Intervals
Formal methods for testing whether observed rule performance is statistically significant. Covers t-tests, confidence intervals, Type I and Type II errors, statistical power. The trade-off between false positives (trading a useless rule) and false negatives (missing a genuinely predictive rule).

### Chapter 6: Data-Mining Bias: The Fool's Gold of Objective TA
The central methodological chapter. Data-mining bias = the systematic overstatement of expected performance caused by selecting the best rule from many candidates. Illustrates with the monkey-keyboards, Bible Codes, Bangladesh butter, and lottery winner examples. Introduces White's Reality Check and bootstrap methods for constructing null distributions that account for the full search.

### Chapter 7: Theories of Nonrandom Price Motion
Explores theoretical reasons why TA might work: behavioral finance (investor biases create predictable patterns), market microstructure (order flow, inventory effects), and the Adaptive Markets Hypothesis (efficiency varies over time). Distinguishes between risk-premium explanations (TA profits are compensation for providing liquidity) and inefficiency explanations.

### Chapter 8: Case Study of Rule Data Mining for the S&P 500
Describes the design and execution of the 6,402-rule case study. Details the three rule themes (trend, extreme/transition, divergence), time-series operators (channel breakout, moving average, channel normalization), intermarket data sources, and statistical methodology. Documents how data-snooping bias was mitigated by excluding rules from the literature.

### Chapter 9: Case Study Results and the Future of TA
Reports the empirical findings from the 6,402-rule test. Discusses which themes produced the most significant results, the performance of the best rules after data-mining correction, and the implications for the future of TA as an evidence-based discipline. Addresses the limitations of the study and directions for future research.

## Topic Index

- **Backtesting**: Ch 1 (methodology), Ch 8 (case study execution)
- **Bootstrap methods**: Ch 6 (White's Reality Check), Ch 8 (Monte Carlo Permutation)
- **Channel breakout**: Ch 8 (operator definition and application)
- **Cognitive biases (comprehensive)**: Ch 2 (overconfidence, confirmation, hindsight, self-attribution, illusory correlation, illusion of control, representativeness, biased assimilation, belief perseverance)
- **Configural vs. linear thinking**: Ch 2 (human limitations), Ch 3 (implications for model building)
- **Data-mining bias**: Ch 6 (definition, examples, correction methods), Ch 8 (case study application)
- **Data-snooping bias**: Ch 6 (distinction from data-mining bias), Ch 8 (mitigation strategy)
- **Detrending**: Ch 1 (definition and rationale), Appendix (mathematical proof of equivalence to benchmarking)
- **Degrees of freedom**: Ch 6 (consumed by searching), Ch 8 (indicator construction costs)
- **Expected vs. observed performance**: Ch 6 (definitions), Ch 4 (sampling distribution)
- **Falsifiability**: Ch 3 (Popperian framework), Ch 2 (why subjective TA fails this test)
- **Law of Large Numbers**: Ch 4 (theoretical foundation)
- **Monte Carlo methods**: Ch 6 (Masters' permutation method), Ch 8 (case study implementation)
- **Moving averages**: Ch 8 (as smoothing operator)
- **Null hypothesis**: Ch 4 (framework), Ch 5 (formal testing), Ch 6 (under data mining)
- **Occam's Razor**: Ch 3 (principle), Ch 6 (applied to out-of-sample deterioration)
- **Out-of-sample testing**: Ch 6 (limitations), Ch 3 (logic of prediction)
- **Performance statistics**: Ch 4 (mean, Sharpe, profit factor, Ulcer Index), Ch 8 (average return as test statistic)
- **Position bias**: Ch 1 (definition), Ch 8 (eliminated by detrending)
- **Practical vs. statistical significance**: Ch 8 (separate evaluation), Ch 4 (large sample effects)
- **p-value**: Ch 4 (definition and interpretation), Ch 5 (formal testing)
- **Randomness in markets**: Ch 2 (Arditti study), Ch 7 (why nonrandom motion might exist)
- **Rule universe**: Ch 6 (definition), Ch 8 (6,402 rules organized by theme)
- **Sampling distribution**: Ch 4 (core concept), Ch 6 (shifted by data mining)
- **Scientific method**: Ch 3 (applied to TA), Ch 1 (objective rules as hypotheses)
- **Stochastics**: Ch 8 (channel normalization operator)
- **Type I / Type II errors**: Ch 5 (trade-off), Ch 6 (data mining increases Type I risk)
- **White's Reality Check**: Ch 6 (theory), Ch 8 (case study application)

## Support Files

| File | Content |
|------|---------|
| `chapters/ch01-objective-rules-and-evaluation.md` | Objective Rules and Their Evaluation |
| `chapters/ch02-illusory-validity-of-subjective-ta.md` | The Illusory Validity of Subjective Technical Analysis |
| `chapters/ch03-scientific-method-and-technical-analysis.md` | The Scientific Method and Technical Analysis |
| `chapters/ch04-statistical-analysis.md` | Statistical Analysis |
| `chapters/ch05-hypothesis-tests-and-confidence-intervals.md` | Hypothesis Tests and Confidence Intervals |
| `chapters/ch06-data-mining-bias.md` | Data-Mining Bias: The Fool's Gold of Objective TA |
| `chapters/ch07-theories-of-nonrandom-price-motion.md` | Theories of Nonrandom Price Motion |
| `chapters/ch08-case-study-sp500-data-mining.md` | Case Study of Rule Data Mining for the S&P 500 |
| `chapters/09-case-study-results-and-future-of-ta.md` | Case Study Results and the Future of TA |
| `patterns.md` | When/How/Trade-offs for each framework |
| `cheatsheet.md` | Decision tables and quick reference |
| `glossary.md` | Alphabetical glossary of key terms |

## References

- Aronson, D.R. (2007). *Evidence-Based Technical Analysis*. Wiley.
- White, H. (2000). "A Reality Check for Data Snooping." *Econometrica*, 68(5).
- Kahneman, D., Slovic, P., & Tversky, A. (1982). *Judgment under Uncertainty: Heuristics and Biases*.
- Gilovich, T. (1991). *How We Know What Isn't So*.
- Romano, J.P. & Wolf, M. (2005). "Stepwise Multiple Testing as Formalized Data Snooping." *Econometrica*, 73(4).
