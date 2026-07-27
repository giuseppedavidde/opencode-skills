# Glossary — Evidence-Based Technical Analysis

Alphabetical reference of key terms from David R. Aronson's "Evidence-Based Technical Analysis: Applying the Scientific Method and Statistical Inference to Trading Signals."

---

## A

**Affirming the Consequent** — A logical fallacy of the form: "If rule works, then profitable back-test. Profitable back-test observed. Therefore rule works." The conclusion does not follow because the back-test result could be due to chance, data-mining bias, or position bias. Central to understanding why confirmatory evidence is insufficient.

**Alternative Hypothesis (H_A)** — The hypothesis that a rule has genuine predictive power (true expected return > 0). Adopted when the null hypothesis is rejected.

**Anchoring** — A behavioral bias where investors fixate on arbitrary reference points (purchase price, 52-week high, round numbers). Leads to underreaction to new information.

**Arbitrage Pricing Theory (APT)** — A multi-factor model relating stock returns to systematic risk factors. Used to determine whether apparent anomalies are compensation for risk rather than true inefficiencies.

**Artificial Trading Rules (ATRs)** — Computer-generated rules with known (zero) predictive power, used in experiments to demonstrate the magnitude of data-mining bias.

---

## B

**Back Testing** — Simulating a rule's performance on historical data to determine what its returns would have been. The observed return is a sample statistic, not a guaranteed future return.

**Behavioral Finance** — The study of how psychological and social factors cause systematic deviations from rational market behavior. Provides theoretical foundation for nonrandom price motion.

**Binary Rule** — A trading rule whose output can assume only two values (e.g., +1 long, -1 short). The simplest form of objective TA method.

**Bootstrap Sampling** — A computer-intensive method that generates a sampling distribution by resampling with replacement from historical returns. Used for hypothesis testing and confidence interval construction without parametric assumptions.

**BSV Hypothesis** — (Barberis-Shleifer-Vishny) A behavioral model where investors alternate between underreaction (due to conservatism bias) and overreaction (due to representativeness), producing momentum followed by reversals.

---

## C

**Channel Breakout Operator (CBO)** — A rule operator that compares current price to the maximum/minimum over a look-back window. Generates signals when price breaks to new highs or lows.

**Cognitive Content** — The property of a statement that makes it a valid candidate for belief; its truth or falsity must make a discernible difference in observable outcomes. Most traditional TA predictions lack cognitive content.

**Complexity Optimization** — The process of systematically increasing rule complexity until test-set performance peaks. Balances underfitting (too simple) against overfitting (too complex).

**Confidence Interval** — A range of values computed from sample data that, with a specified confidence level (e.g., 95%), contains the true population parameter. More informative than a binary hypothesis test.

**Confirmation Bias** — The tendency to seek, interpret, and remember evidence that confirms preexisting beliefs while ignoring contradictory evidence. The primary cognitive error in traditional TA practice.

**Conservatism Bias** — The tendency to underweight new evidence relative to prior beliefs. In markets, causes underreaction and contributes to momentum.

---

## D

**Data Mining** — The process of searching through many rules, parameters, and indicator combinations to find profitable patterns. Distinguished from single-rule back-testing by the multiplication of test opportunities.

**Data-Mining Bias** — The inflation of apparent performance caused by selecting the best result from many tested alternatives. The expected return of the best rule from N worthless rules increases with N, creating the illusion of predictive power.

**Declarative Statement** — A proposition with truth value (can be characterized as true or false). The fundamental building block of knowledge. TA claims must be declarative to be testable.

**Deductive Logic** — Reasoning from general premises to specific, necessary conclusions. Provides certainty but cannot generate new knowledge about the world.

**Detrending** — Transforming market data so its mean daily change is zero. Eliminates the confounding effect of position bias interacting with market trend during back-testing.

**DHS Hypothesis** — (Daniel-Hirshleifer-Subrahmanyam) A behavioral model where overconfidence about private information causes overreaction, and self-attribution bias sustains mispricing.

**Diffusion Indicator** — A composite indicator representing the percentage of components in a universe signaling an uptrend (e.g., percentage of NYSE stocks above their 200-day moving average).

**Discernible-Difference Test** — The criterion for cognitive content: a statement makes a claim whose truth or falsity produces observably different outcomes. TA predictions that fail this test are empty propositions.

---

## E

**Evidence-Based Technical Analysis (EBTA)** — Aronson's term for TA practiced as a rigorous observational science, grounded in objective rules, statistical inference, and the scientific method.

**Efficient Markets Hypothesis (EMH)** — The theory that asset prices fully reflect all available information, implying price changes are unpredictable. Three forms: weak, semi-strong, strong.

**Expected Return** — For a nonpredictive rule: ER = [p(Long) × ADC] − [p(Short) × ADC]. The return attributable solely to position bias and market trend, not predictive skill.

---

## F

**Falsifiability** — Popper's criterion for scientific theories: a theory must make predictions that can potentially be proven false by observation. Non-falsifiable theories (including most traditional TA) are pseudoscience.

**Fallacy of Affirming the Consequent** — See Affirming the Consequent.

---

## G

**Grossman-Stiglitz Paradox** — If markets were perfectly efficient, no one would have incentive to gather costly information. Therefore, some degree of inefficiency must exist to compensate information gatherers.

---

## H

**Herding** — The tendency of investors to imitate others' actions rather than relying on independent analysis. Can amplify price trends beyond fundamental justification.

**HS Hypothesis** — (Hong-Stein) A behavioral model where "news watchers" (fundamental analysts) and "momentum traders" (trend followers) interact, producing momentum followed by reversal.

**Hypothesis Test** — A formal inference procedure that evaluates whether sample evidence is sufficiently inconsistent with the null hypothesis to warrant its rejection.

**Hypothetico-Deductive Method** — The scientific workflow: observation → hypothesis → deduction of testable predictions → empirical testing → falsification or corroboration.

---

## I

**Inductive Logic** — Reasoning from specific observations to general conclusions. Always uncertain; conclusions go beyond the premises. The basis of all empirical science and statistical inference.

**Information Cascade** — A social phenomenon where individuals ignore their private information and follow the actions of earlier decision-makers, leading to herd behavior.

**Inverse Rule** — A rule that takes the opposite position of the traditional interpretation (buy when traditional rule sells). Included in testing because it is not known a priori which direction is correct.

**Interval Estimate** — See Confidence Interval.

---

## L

**Limits of Arbitrage** — Constraints (fundamental risk, noise trader risk, implementation costs) that prevent rational arbitrageurs from fully correcting mispricings.

**Look-Ahead Bias** — Using information in back-testing that would not have been available at the time of signal generation. Produces unrealistically optimistic results.

---

## M

**Monte Carlo Permutation (MCP)** — A computer-intensive method that generates a sampling distribution by randomly scrambling rule outputs against price changes. Used to test the significance of data-mined rules.

**Moving-Average Operator** — A rule operator that smooths a time series by computing its average value over a specified look-back window. Foundation of crossover and divergence rules.

---

## N

**Noise Trader** — An investor who trades on non-fundamental information or sentiment. Creates mispricings that informed traders may not be able to fully correct.

**Nonrandom Price Motion** — Systematic departures from a random walk (trends, mean-reversion, cycles). Necessary for TA to have any justification.

**Null Hypothesis (H₀)** — The presumption that a rule has no predictive power (expected return ≤ 0). The hypothesis that the evidence must contradict to establish significance.

---

## O

**Objective Technical Analysis** — TA methods that are precisely defined and programmable, producing unambiguous signals independent of individual interpretation. Required for scientific evaluation.

**Overconfidence Bias** — The tendency to overestimate one's knowledge, skill, or predictive accuracy. Manifests as control illusion, hindsight bias, and optimism bias in traders.

**Overfitting** — Creating a rule so complex that it captures noise as well as signal. Performs well in training data but poorly out-of-sample.

---

## P

**p-value** — The probability of observing a test statistic at least as extreme as the one obtained, assuming the null hypothesis is true. NOT the probability that the null hypothesis is true.

**Parameter Estimation** — Using sample data to approximate the value of a population parameter. Produces point estimates (single value) and interval estimates (range).

**Point Estimate** — A single value that serves as the best guess of a population parameter (e.g., "the rule's true expected return is 10%").

**Population Parameter** — The true (unknown) value characterizing a population (e.g., the rule's true expected return over all possible future realizations).

**Position Bias** — A rule's tendency to spend more time in long or short positions. In trending markets, position bias alone can generate apparent performance unrelated to predictive power.

**Programmability Criterion** — The test for objectivity: a TA method is objective if and only if it can be implemented as a computer program producing unambiguous market positions.

---

## R

**Representativeness Heuristic** — The cognitive shortcut of judging probability by similarity to a stereotype. Causes investors to see patterns in random data and extrapolate short trends.

**Risk Transfer Premium** — The return earned by speculators in futures markets as compensation for accepting price risk from commercial hedgers. A rational, non-behavioral explanation for trend-following profits.

---

## S

**Sample Statistic** — A value computed from sample data (e.g., back-tested mean return). An estimate of the unknown population parameter, subject to sampling error.

**Sampling Distribution** — The probability distribution of a sample statistic over many independent samples from the same population. Characterizes the range of values expected from random variation alone.

**Sampling Error** — The deviation between a sample statistic and the population parameter it estimates. Inherent in any finite sample.

**Self-Attribution Bias** — The tendency to attribute successes to skill and failures to external factors. Prevents traders from learning from losses and contributes to overconfidence.

**Standard Error of the Mean** — The standard deviation of the sampling distribution of the mean. Quantifies the typical sampling error for a given sample size.

**Subjective Technical Analysis** — TA methods relying on personal interpretation (chart patterns, Elliott Wave, etc.). Inherently untestable and immune to falsification.

---

## T

**Threshold** — A boundary value that determines when an indicator's value triggers a signal (e.g., overbought/oversold levels for RSI).

**Type I Error** — False positive: rejecting the null hypothesis when it is actually true. Finding "predictive power" where none exists.

**Type II Error** — False negative: failing to reject the null hypothesis when it is actually false. Missing a genuinely predictive rule.

---

## U

**Underdetermination of Theories** — The philosophical problem that any finite set of observations is consistent with infinitely many alternative explanations. Data alone cannot prove a theory true.

**Underfitting** — Creating a rule too simple to capture systematic patterns in the data. Leaves predictive power unexploited.

---

## V

**Validation Set** — A third data partition (after training and test sets) kept untouched during all optimization. Provides the only unbiased estimate of a rule's expected future performance.

---

## W

**White's Reality Check (WRC)** — A statistical method that accounts for data-mining bias by comparing a rule's performance against the sampling distribution of the best rule from repeated bootstrap replications. Developed by Halbert White.
