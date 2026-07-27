# Cheatsheet: Evidence-Based Technical Analysis

## Decision Tables

### Rule Evaluation: Is This Rule Worth Trading?

| Criterion | Check | Pass Threshold |
|-----------|-------|----------------|
| Data detrended? | Was the evaluation done on detrended/zero-mean data? | Yes — mandatory |
| Single rule or from a search? | Was this the only rule tested, or the best of N? | If N > 1, adjust significance |
| Universe size (N) | How many rules were compared? | Must know N to correct p-value |
| Sample size (n) | How many independent trades/days? | ≥ 30 trades for CLT; ≥ 100 preferred |
| Statistical significance | p-value after data-mining correction | p < 0.05 |
| Practical significance | Expected annual return after costs | ≥ risk-free rate + risk premium |
| Out-of-sample confirmed? | Tested on truly unseen data | OOS return within 50% of IS return |
| Method documented? | Can the study be replicated? | Full rule specification, data source, evaluation methodology |

### Cognitive Bias Diagnostic

| Symptom | Likely Bias | Corrective Action |
|---------|-------------|-------------------|
| "I knew that would happen" after seeing the outcome | Hindsight bias | Write predictions before outcomes; keep a prediction journal |
| Explaining wins as skill, losses as "the market was manipulated" | Self-attribution bias | Compare actual win rate to expected; calculate statistical significance of your edge |
| Finding the pattern "obvious" once someone points it out | Confirmation bias + Hindsight | Look for the pattern in random data; ask "what would disprove this?" |
| Confidence increases with more information (even irrelevant) | Overconfidence + Information bias | Limit indicators to those with proven incremental predictive value |
| "This indicator works 70% of the time" (based on memory) | Illusory correlation + Availability heuristic | Back-test objectively; count ALL instances, not just memorable ones |
| Changing chart settings until the pattern appears | Texas sharpshooter | Pre-specify exact pattern criteria; lock parameters before looking |

### Statistical Test Selection

| Scenario | Recommended Method | Key Assumption |
|----------|-------------------|----------------|
| Testing 1 pre-specified rule | Standard t-test of mean return | Independence of returns (may be violated) |
| Testing best of N rules (N known) | White's Reality Check or Monte Carlo Permutation | All rules' return series available |
| Testing complex rule with many parameters | Walk-forward analysis | Stationarity within walk-forward windows |
| Evaluating whether rule beats buy-and-hold | Detrended return + sign test | Position bias removed via detrending |
| Comparing two rules against each other | Paired difference test or bootstrap | Rules tested on same data period |
| Non-normal return distributions | Bootstrap confidence intervals | Resampling with replacement is valid |

### The Aronson Framework: From Hypothesis to Trade

| Phase | Activity | Key Tool/Method | Watch Out For |
|-------|----------|-----------------|---------------|
| 1. Hypothesis | Propose a causal rationale for the rule | Chapter 7 (theories of nonrandom price motion) | Post-hoc rationalization; "just-so" stories |
| 2. Operationalization | Define rule precisely as algorithm | Mathematical/logical/time-series operators | Vagueness ("strong breakout," "clear trend") |
| 3. Detrend | Zero-center the market return series | Subtract average daily return | Non-stationarity over long periods |
| 4. Back-test | Compute average return, distribution, risk metrics | Performance statistics (mean, Sharpe, profit factor) | Look-ahead bias, survivorship bias |
| 5. Account for data mining | Adjust p-value for universe size N | White's Reality Check / Monte Carlo Permutation | Ignoring N entirely |
| 6. Out-of-sample test | Apply rule to withheld data — ONCE | Reserved contiguous period | Multiple OOS peeks = OOS becomes IS |
| 7. Practical evaluation | Assess economic viability | Expected return - costs, drawdown, capacity | Statistical significance without economic significance |
| 8. Deploy & monitor | Trade rule; track live vs. expected performance | Performance dashboards, alert thresholds | Assuming stationary dynamics continue |

### Degrees of Freedom Burned by Common TA Practices

| Practice | DF Cost | Mitigation |
|----------|---------|------------|
| Testing N indicator lookback values | N DFs | Pre-specify lookback based on economic rationale, not optimization |
| Choosing best of M entry rules | M DFs | Report M; apply data-mining correction |
| Optimizing 3 parameters jointly | P₁ × P₂ × P₃ DFs | Use walk-forward optimization; shrinkage methods |
| "Eyeballing" charts to find patterns | Effectively infinite | Don't do this for evaluation — only for hypothesis generation |
| Trying multiple exit strategies for same entry | N_exit DFs | Fix exit logic before entry optimization |
| Selecting indicators based on back-test | N_indicators_tested DFs | Pre-specify indicator set; report total tested |

### Quick Reference: Key Formulas

| Concept | Formula/Definition |
|---------|-------------------|
| **p-value** | P(observed return ≥ x \| H₀ true) = area under null PDF ≥ x |
| **Data-mining adjusted α** | α_adjusted = 1 - (1 - α)^(1/N) ≈ α/N for small α (Bonferroni) |
| **t-statistic** | (X̄ - μ₀) / (s / √n) |
| **Detrended return** | r_detrended = r_raw - r̄_period |
| **Standard error of mean** | SE = s / √n |
| **95% CI for mean** | X̄ ± 1.96 × SE |
| **Profit factor (log)** | ln(Σ gains / \|Σ losses\|) — symmetric around zero |
\end{verbatim}
