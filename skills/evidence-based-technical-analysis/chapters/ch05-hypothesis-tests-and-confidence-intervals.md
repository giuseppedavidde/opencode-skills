# Chapter 5: Hypothesis Tests and Confidence Intervals

## Core Idea
Statistical inference — specifically hypothesis testing and parameter estimation — provides the formal machinery to determine whether a trading rule's historical performance reflects genuine predictive power or merely **sampling luck**. Without these tools, back-tested returns are just numbers without meaning.

## Frameworks Introduced

### 1. Two Branches of Statistical Inference
- **Hypothesis testing**: A yes/no decision procedure — does the evidence warrant rejecting the presumption (null hypothesis) that the rule has no predictive power?
- **Parameter estimation**: Quantifies the magnitude of an effect — produces a **point estimate** (best guess of true return) and an **interval estimate** (confidence interval within which the true return lies with specified probability).

### 2. The Null Hypothesis Framework
The null hypothesis (H₀) asserts that the rule's true expected return ≤ 0 (no predictive power). The alternative hypothesis (H_A) asserts expected return > 0. The hypothesis test asks: is the observed back-tested return sufficiently **surprising** under H₀ to warrant rejecting it?

The decision hinge is the **p-value**: the probability of observing a return at least as extreme as the sample result, assuming H₀ is true. A small p-value (typically < 0.05) indicates the result is unlikely to be due to chance.

### 3. Sampling Distribution Mechanics
The sampling distribution characterizes the range of sample statistics (mean returns) expected from random variation alone. Key elements:
- **Central Limit Theorem**: The sampling distribution of the mean tends toward normality as sample size increases
- **Standard error of the mean**: Quantifies the typical deviation between a sample mean and the population mean
- **Computer-intensive methods**: Bootstrap sampling (resampling with replacement from historical returns) and Monte Carlo permutation (randomly scrambling rule outputs against price changes) generate sampling distributions without parametric assumptions

### 4. Confidence Intervals
An interval estimate at confidence level (1-α) means: if the experiment were repeated many times, (1-α)% of the computed intervals would contain the true population parameter. More informative than a binary hypothesis test because it conveys both the **magnitude** and **precision** of the estimate.

## Key Concepts
- **Type I Error (α)**: Rejecting H₀ when it is actually true — false positive, "finding" predictive power where none exists
- **Type II Error (β)**: Failing to reject H₀ when it is false — false negative, missing a genuinely predictive rule
- **Statistical power (1-β)**: The probability of correctly rejecting H₀ when the rule truly has predictive power; increases with sample size and effect size
- **Confirmatory evidence trap**: Profitable back-tests are necessary consequences of predictive power but insufficient to logically establish it
- **Practical vs. statistical significance**: A rule may be statistically significant (p < 0.05) but practically worthless if its edge is smaller than transaction costs

## Anti-patterns
- **p-hacking**: Testing multiple variations of a rule and reporting only the one that achieved p < 0.05 without adjusting for multiplicity
- **Ignoring data-mining bias**: Using standard significance tests (which assume a single test) when many rules were explored — this dramatically inflates the effective Type I error rate
- **Confusing p-value with effect probability**: p = 0.04 does NOT mean "96% chance the rule works" — it means "4% chance of seeing this result if the rule has zero predictive power"
- **Over-reliance on parametric assumptions**: Assuming normally distributed returns when financial data exhibit fat tails and heteroskedasticity
- **Confidence interval misinterpretation**: A 95% CI does not mean "95% probability the true value is in this interval" for any single computed interval

## Key Takeaways
1. Hypothesis testing formalizes the question "could this back-tested profit be luck?" into a **quantitative probability**.
2. Bootstrap and Monte Carlo permutation methods provide robust alternatives to parametric tests for financial data.
3. A **p-value** is the probability of the evidence given the null hypothesis — NOT the probability that the null hypothesis is true.
4. Confidence intervals are more informative than hypothesis tests alone — they communicate the **range of plausible true returns**.
5. All inference procedures assume a **single test** — when data mining over many rules, standard p-values are misleadingly optimistic.
