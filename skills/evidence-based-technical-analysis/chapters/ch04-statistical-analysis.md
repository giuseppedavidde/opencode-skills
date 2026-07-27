# Chapter 4: Statistical Analysis

## Core Idea

Statistical analysis is the **only practical way** to distinguish TA methods that have genuine predictive power from those that do not. The essence of TA is statistical inference — discovering generalizations from historical data and extrapolating them to the future. Without formal statistical reasoning, practitioners are defenseless against the randomness that permeates financial market data.

## Frameworks Introduced

### The Null Hypothesis Framework for Rule Evaluation
- **H₀ (Null Hypothesis)**: The TA rule has **no predictive power** — its expected return is zero on detrended data. Any observed profit is due to luck (sampling variability).
- **H₁ (Alternative Hypothesis)**: The rule has genuine predictive power — its expected return is greater than zero.
- **Logic**: Evidence cannot prove H₁ true (affirming the consequent fallacy), but evidence can show H₀ is **highly improbable** and therefore should be rejected.
- **Falsification via Statistical Improbability**: If a rule's back-tested return is so high that it would occur with probability ≤ 0.05 under the assumption H₀ is true, we reject H₀ and provisionally accept H₁.

### The Sampling Paradigm
- **Population**: The infinite set of all possible future returns from a rule.
- **Sample**: The finite set of historical back-test returns.
- **Sample Statistic**: A function of the sample data (e.g., average return, Sharpe ratio, profit factor).
- **Sampling Distribution**: The probability distribution of a sample statistic across all possible samples of a given size.
- **Central Insight**: Even a useless rule (true expected return = 0) can generate **substantial profits or losses** in any small sample — purely by chance.

### Probability Density Functions for Rule Performance
The PDF describes the distribution of possible back-test returns for a rule with zero predictive power:
- Centered at zero return
- Shows the probability of any given deviation from zero occurring purely by chance
- The **p-value** is the area under the PDF to the right of the observed performance — the probability of obtaining a result this extreme or more extreme if H₀ were true

### The Data-Mining Adjustment
When **many rules** are back-tested and the best one is selected, the sampling distribution shifts rightward. Performance that looks significant for a single rule may be **completely unremarkable** when 1,000 rules were tested. The threshold for rejecting H₀ must be raised to compensate for the greater likelihood of finding a lucky useless rule.

## Key Concepts

### Statistical Significance vs. Practical Significance
- **Statistical significance**: p-value < α (typically 0.05) — the result is unlikely to be due to chance
- **Practical significance**: the economic value of the return — whether the expected profit justifies trading costs, risk, and capital requirements
- Large samples can make trivially small returns statistically significant while being economically worthless

### The Law of Large Numbers
As sample size increases, the sample average converges to the population average. Key implications:
- Larger samples produce more reliable estimates (standard error decreases with √n)
- But this assumes **stationarity** — financial time series are likely non-stationary, meaning older data may be irrelevant or misleading

### The Central Limit Theorem
Regardless of the shape of the population distribution, the **sampling distribution of the mean** approaches a normal distribution as sample size increases. This is the mathematical foundation that makes statistical inference possible even when the underlying data is not normally distributed.

### Performance Statistics
| Statistic | Definition | Use |
|-----------|------------|-----|
| Average Return (mean) | Σ(returns) / n | Primary test statistic; the "sample mean" |
| Sharpe Ratio | (Mean return - risk-free rate) / σ | Risk-adjusted performance; penalizes variance |
| Profit Factor | Sum of gains / \|Sum of losses\| | Ratio measure; log-transform for symmetry |
| Ulcer Index | Magnitude of equity drawdowns | Better risk measure than σ — considers sequence of wins/losses |

### The Bead-Box Thought Experiment
A concrete illustration of sampling and inference: A box contains an unknown mixture of grey and white beads. We can only draw samples of 20 beads at a time. From 50 samples, we estimate the true fraction of grey beads. Key lesson: **individual samples vary widely**, but the distribution of sample fractions converges to the true population fraction. This is the central concept of all statistical inference applied to TA rule evaluation.

## Anti-patterns

- **Naive p-value interpretation**: Thinking p < 0.05 means "95% probability the rule works." The p-value speaks to the probability of the **evidence**, not the probability of the **hypothesis**. It's P(data | H₀ true), not P(H₀ true | data).

- **Ignoring multiple comparisons**: Testing 20 rules, finding one with p = 0.01, and declaring it significant. With 20 tests, the probability of at least one false positive at α = 0.05 is approximately 1 - (0.95)²⁰ ≈ 0.64 — nearly two-thirds. The p-value must be adjusted (Bonferroni, or better, data-mining-aware methods).

- **Conflating sample mean with true mean**: Assuming the back-tested return IS the rule's expected return. The sample mean is an **estimate** with uncertainty quantified by the standard error. Confidence intervals should always be reported.

- **Nonstationarity neglect**: Treating 40 years of market data as one homogeneous sample. Structural breaks (regime changes, new regulations, market microstructure evolution) make old data potentially misleading.

- **Overfitting the null**: Setting α too low (e.g., 0.001) to avoid false positives at the cost of missing genuinely predictive rules (Type II error). The balance between Type I and Type II errors should be context-dependent.

- **Affirming the consequent**: "If a rule has predictive power, it will be profitable in a back test. The back test was profitable. Therefore, the rule has predictive power." This is a logical fallacy. Profitability is consistent with predictive power, but does not prove it.

## Key Takeaways

1. **Start with the null hypothesis that no rule works.** This is the skeptical, scientific default. The burden of proof is on the rule to demonstrate performance that is highly improbable under the null.

2. **The p-value is a statement about the data, not about the hypothesis.** It quantifies how surprising the observed performance would be if the rule were useless. It does not tell you the probability that the rule is truly predictive.

3. **Data mining changes everything.** When many rules are tested, what looks like extraordinary performance may be ordinary. The sampling distribution must be adjusted to account for the number of rules tested.

4. **Financial markets violate stationarity assumptions.** Standard statistical methods assume a stationary process. Financial markets are likely non-stationary, meaning all statistical conclusions are provisional and must be periodically re-validated.

5. **Statistical significance ≠ profitability.** A rule can pass statistical tests at p < 0.05 and still lose money after transaction costs, slippage, and capacity constraints. Always evaluate practical significance separately.
