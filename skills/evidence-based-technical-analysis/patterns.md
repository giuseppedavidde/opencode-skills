# Patterns: Evidence-Based Technical Analysis

## When to Apply Each Framework

### The Null Hypothesis Default
**When**: Evaluating any new rule, indicator, or trading system.
**How**: Start by assuming the rule has zero predictive power. Use detrended data to compute expected return under the null. Only reject the null if the observed performance would occur with probability ≤ 0.05 under the assumption of no predictive power.
**Trade-offs**: High bar for acceptance (fewer false positives → more false negatives). Conservative but protects against the gravest error: trading a useless rule with real capital.

### The Data-Mining-Aware Evaluation
**When**: You or others have tested multiple rules/variants and selected the best performer.
**How**: Do NOT evaluate the winner using a single-rule significance test. Either:
- Apply White's Reality Check: bootstrap the null distribution of the MAXIMUM across all tested rules
- Apply Masters' Monte Carlo permutation: randomly shuffle position-market pairings to destroy predictive relationships
- Report the effective p-value accounting for N (number of rules tested)
**Trade-offs**: Computationally intensive; requires storing per-rule return series. The benefit is avoiding "fool's gold" — rules that are just lucky winners of a randomness competition.

### The Detrending Transformation
**When**: Evaluating any binary (long/short) rule, especially one with position bias.
**How**: Subtract the market's average daily return over the evaluation period from each day's actual return. This zero-centers the return series, eliminating the benefit of being long during uptrends (or short during downtrends). The rule is now evaluated on its ability to be on the right side of the market RELATIVE to a neutral baseline.
**Trade-offs**: Can obscure rules that work by being long in bull markets / short in bear markets. But this is intentional — such rules are not demonstrating predictive power, just position bias + trend.

### The Configural Thinking Test
**When**: Combining multiple indicators subjectively.
**How**: For N binary indicators, there are 2ᴺ possible configurations. With 5 indicators = 32 configurations. Ask: "Can I specify, in advance, what position each of these 32 configurations maps to?" If not, you are not doing configural thinking — you are improvising, and your process cannot be back-tested or improved.
**Trade-offs**: Formalizing the mapping removes flexibility but enables rigorous testing and optimization. The loss of "art" is the gain of "science."

### The Out-of-Sample Validation Protocol
**When**: Testing a rule developed through data mining.
**How**: Reserve a contiguous out-of-sample period (e.g., last 20% of data). Do ALL rule selection, parameter optimization, and comparison on the in-sample data only. Evaluate the SINGLE selected rule on the out-of-sample — exactly once. If OOS performance is substantially worse, the rule was overfit.
**Trade-offs**: Single-use OOS data is costly — you waste data that could be used for estimation. Repeated OOS peeking (tweaking the rule after seeing OOS results) turns OOS into in-sample. Consider cross-validation or bootstrap methods that use data more efficiently.

### The Bias Awareness Checklist
**When**: Making any trading decision based on chart analysis.
**How**: Before acting, explicitly ask:
1. "Am I seeing only confirming evidence?" (Confirmation bias)
2. "Would I attribute success to skill and failure to bad luck?" (Self-attribution bias)
3. "Did I really 'know' this would happen BEFORE it did?" (Hindsight bias)
4. "Is this pattern actually there, or am I imposing order on noise?" (Pattern-finding bias)
5. "How many other interpretations did I consider and discard?" (Biased assimilation)
**Trade-offs**: Constant self-interrogation is mentally taxing and can lead to analysis paralysis. The cost of deliberation must be weighed against the cost of biased decisions.

### The Statistical vs. Practical Significance Separation
**When**: A rule passes statistical significance tests.
**How**: Separately evaluate: (1) Expected annual return after transaction costs, (2) Maximum drawdown and required capital, (3) Sharpe ratio and risk-adjusted measures, (4) Capacity constraints (how much capital degrades the strategy), (5) Correlation with existing portfolio. Only trade if ALL metrics exceed your thresholds.
**Trade-offs**: A statistically significant but practically insignificant rule wastes capital and attention. But ignoring statistical significance means you're trading noise.

## When NOT to Use Formal Statistical Methods

### When the Signal Is Overwhelming
If a rule has produced 80% winning trades across 500 trades, formal statistics add little — the informal case is already compelling. Statistical methods are most needed in the **grey zone** where results are ambiguous.

### When Sample Size Is Too Small
With fewer than 30 independent trades, the Central Limit Theorem does not apply reliably, and parametric tests are invalid. Use non-parametric methods (permutation tests, bootstrap) or simply acknowledge that conclusions are tentative.

### When the Process Is Clearly Non-Stationary
If you know the market regime has fundamentally changed (e.g., decimalization, algorithmic trading dominance, regulatory shifts), historical data from the prior regime may be irrelevant. Statistical inference from obsolete data can be actively misleading.

### When Intuition Is Actually Superior
For problems with clear, stable feedback loops and limited complexity (e.g., market making in a single instrument), expert intuition trained through thousands of repetitions can outperform formal models. This is the exception, not the rule, and requires the specific conditions of "kind" learning environments (rapid, unambiguous feedback).

## Trade-Offs Summary Table

| Approach | Strengths | Weaknesses | Best For |
|----------|-----------|------------|----------|
| Single-rule significance test | Simple, fast | Ignores data-mining bias | Pre-registered single hypotheses |
| White's Reality Check | Accounts for full search | Patented, complex to implement | Data-mined rule universes |
| Monte Carlo Permutation | Public domain, intuitive | Computationally heavy | Same as White's; alternative when patent is an issue |
| Out-of-sample testing | Intuitive, widely accepted | Wastes data, one-shot | Model validation after all optimization |
| Cross-validation | Efficient data use | Assumes i.i.d. (violated in time series) | Non-time-series problems |
| Walk-forward testing | Respects temporal order | Fewer training observations | Trading system development |
| Subjective chart analysis | Flexible, holistic | Contaminated by all cognitive biases | Generation of hypotheses only; never final evaluation |
