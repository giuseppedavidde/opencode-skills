# Chapter 11: The Dangers of Backtesting

## Core Idea
"Backtesting while researching is like drinking and driving. Do not research under the influence of a backtest." A backtest is a historical simulation — a hypothesis, not an experiment — and it guarantees nothing. Worse, the *better* you become at backtesting, the more likely you are to publish a false discovery: an expert has run tens of thousands of trials on the same dataset, so any "winning" backtest is probably a statistical fluke. Backtest overfitting is "arguably the most fundamental question in quantitative finance."

## Frameworks Introduced
- **Seven Sins of Quantitative Investing (Luo et al. 2014)**: survivorship bias, look-ahead bias, storytelling, data mining/snooping, transaction costs, outliers, shorting (lender availability/cost unknown). Plus: non-standard performance methods, hidden risks, correlation-causation confusion, unrepresentative periods, ignored stop-outs/margin calls, ignored funding costs.
- **Mission Impossible — the flawless backtest**: even a flawless, fully reproducible, conservatively priced backtest is probably wrong, because only an expert can produce one and an expert has run many trials -> multiple testing -> selection bias.
- **Backtest overfitting**: selection bias on multiple backtests — a strategy developed to monetize random historical patterns that won't recur.
- **Second Law of Backtesting (Snippet 11.1)**: "Backtesting while researching is like drinking and driving. Do not research under the influence of a backtest."
- **Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric Cross-Validation (CSCV, Bailey et al. 2017a)**: collect N trials' PnL into a TxN matrix M, partition rows into an even number S of submatrices, form all C(N, S/2) train/test combinations, pick the IS-optimal trial, rank its OOS performance, compute logit lambda_c; PBO = P[lambda < 0]. High logit = consistency between IS and OOS = low overfitting.

## Key Concepts
- The purpose of a backtest is to **discard bad models, not to improve them** — adjusting a model based on backtest results is dangerous and wasted effort.
- Feature importance (Ch.8) is a *true* research tool because it is derived ex-ante; a backtest explains nothing about why a strategy would have made money.
- Researchers who report hundreds of "alphas" never tell you about the millions of tickets that didn't win.
- Recommendations: develop for asset classes not specific securities; apply bagging; never backtest until research is complete; record every backtest to compute PBO and the deflated Sharpe ratio; simulate scenarios not just history; if it fails, start from scratch.

## Anti-patterns
- **Using backtests as a research/discovery tool** — there is always an ex-post story (Luo's sin #3, storytelling).
- Reporting the Sharpe ratio of the best trial without accounting for the number of trials.
- Overfitting by re-running the single walk-forward path until a false positive appears.
- Confusing portfolio risk (the CRO's concern) with the risk that a strategy will fail to succeed.
- Reusing failed backtest results instead of starting from scratch.

## Key Takeaways
- Never backtest until your model is fully specified; if it fails, start over.
- Backtest overfitting is the central unsolved problem of mathematical finance.
- Record every trial, compute PBO and the deflated Sharpe ratio to correct for selection bias.
- A backtest is a sanity check on sizing, turnover, costs, and scenario behavior — not a proof and not a research tool.