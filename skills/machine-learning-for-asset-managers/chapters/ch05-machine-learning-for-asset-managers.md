# Chapter 5: Financial Labels

## Core Idea
In supervised learning, the **label defines the task the algorithm learns**. Financial ML almost universally uses the fixed-horizon method, yet that choice injects heteroscedasticity, discards path information, and forecasts an impractical event. Four alternative labeling strategies — fixed-horizon, triple-barrier, trend-scanning, and meta-labeling — address these deficiencies, with meta-labeling specifically separating the *side* decision from the *size* decision.

## Frameworks Introduced
- **Fixed-horizon method**: label `y_i ∈ {−1,0,1}` from return over `h` bars vs. threshold `τ`; the academic default, with three documented structural flaws.
- **Triple-barrier method**: two horizontal barriers (profit-taking, stop-loss) + one vertical barrier (max holding period); label is the *first* barrier touched, encoding path information.
- **Trend-scanning method**: scan multiple look-forward windows `L`, fit a linear time-trend `x_{t+l} = β_0 + β_1 l + ε`, label by `sgn(t̂_{β̂_1})` of the window with maximum `|t̂_{β̂_1}|` — no barriers, no fixed horizon.
- **Meta-labeling**: a secondary classifier trained on the *outcomes* of a primary side-model (loss=0, gain=1); it does not predict the side, it predicts whether the primary model will succeed, and that probability sizes the bet.
- **Bet sizing by expected Sharpe ratio**: `z = (p − ½)/sqrt(p(1−p))`, bet size `m = 2·Z[z] − 1 ∈ [−1,1]`.
- **Ensemble bet sizing**: de Moivre–Laplace / Lindeberg–Lévy convergence of `n` meta-labeling classifiers to a Gaussian; size `m = 2·t_{n−1}[t] − 1` with `t = (p̂ − ½)/sqrt(p̂(1−p̂)/n)`.

## Key Concepts
- **Regression vs. classification supervision**: infinite-population targets vs. finite categorical/ordinal labels; real variables can be discretized either way.
- **Path-dependent vs. point labels**: the sign of tomorrow's return (point) differs fundamentally from "the side of the next 5% move" (path-dependent).
- **Time bars and heteroscedasticity**: intraday seasonality makes fixed-horizon label distributions non-stationary; tick/volume/dollar bars or standardized returns `z = r/σ` mitigate this.
- **Precision/recall/F1 trade-off in meta-labeling**: e.g. precision 60% / recall 90% loses money if bet sizing is wrong; meta-labeling sacrifices recall (90%→70%) to gain precision (60%→70%), lifting F1.
- **t-value as label strength**: the trend-scanning `t̂_{β̂_1}` not only signs the trend but, via its magnitude, serves as a regression target or as sample weights in classification.
- **Primary vs. secondary model decoupling**: side-model and bet-sizing-model need not — and often should not — be the same.

## Anti-patterns
- **Defaulting to fixed-horizon labeling because "everyone does it"**: the method produces non-stationary label distributions, ignores intermediate path information, and forecasts an event (return crosses `τ` at exactly `t_{i,0}+h`) investors rarely care about.
- **Applying a constant threshold `τ` to raw (non-standardized) time-bar returns**: seasonality flows straight into the labels — a 0 label at the open/close is far more informative than at noon.
- **Disconnecting labels from how positions are actually managed**: real positions are governed by profit-taking and stop-loss levels; fixed-horizon labels ignore this and produce unrepresentative training outcomes.
- **Forcing a single model to predict both side and size**: a model good at direction may be bad at sizing; conflating them courts losses when false positives are large and true positives are small.
- **Side-stepping meta-labeling when precision is the binding constraint**: without a secondary model, raising recall necessarily lowers precision; meta-labeling is the disciplined way to trade recall for precision.
- **Treating barrier-touch as a clean binary outcome**: a barrier may be touched by a thin margin — trend-scanning with continuous t-values is the proposed guard against this discretization fragility.
- **Sizing bets only on side-probability**: ignoring the Sharpe-implied `z` (or ensemble `t`-statistic) leaves free precision/recall information on the table.

## Key Takeaways
1. The label defines the task — researchers must consciously choose it; the default fixed-horizon choice is usually wrong for finance.
2. Triple-barrier labeling embeds the realistic mechanics (profit-taking, stop-loss, max holding) of how a position is actually managed.
3. Trend-scanning extracts the most statistically significant linear trend across look-forward windows without arbitrary barriers — labels double as regression targets or sample weights.
4. Meta-labeling decouples side from size, trading recall for precision to lift F1 — the single most impactful lever when a high-recall side-model is losing money on false positives.
5. Bet sizing has principled closed forms — expected-Sharpe `z` for a single classifier and a t-statistic for an ensemble — both yielding a uniform `m ∈ [−1,1]`.