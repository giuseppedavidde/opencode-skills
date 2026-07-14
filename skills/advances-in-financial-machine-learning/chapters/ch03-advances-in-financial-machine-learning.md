# Chapter 3: Labeling

## Core Idea
Supervised ML needs labels for the rows of the feature matrix X. The standard fixed-time-horizon labeling used in virtually all ML finance papers is path-independent, ignores volatility, ignores stop-loss limits, and produces a majority of trivial 0 labels. López de Prado replaces it with the **triple-barrier method** — a path-dependent label that mirrors how real strategies exit (profit-taking, stop-loss, time limit) — and introduces **meta-labeling**, a secondary classifier that learns only the *size* of a bet given the side is set by a primary model.

## Frameworks Introduced
- **Fixed-Time Horizon Method (and why it fails)**: y_i = sign(r_{t_i,0+h}) vs threshold tau. Fails because (1) time bars have poor statistical properties, (2) a constant tau ignores volatility regime, (3) it ignores the price path — labeling positions that would have been stopped-out.
- **Dynamic Thresholds**: profit-taking/stop-loss limits set as a function of exponentially weighted moving std of returns (Snippet 3.1).
- **Triple-Barrier Method**: two horizontal barriers (profit-taking, stop-loss, dynamic multiples of volatility) + one vertical barrier (expiration). Label = +1 if upper touched first, -1 if lower, sign of return (or 0) if vertical. Eight barrier configurations [pt,sl,t1]; only three are useful ([1,1,1], [0,1,1], [1,1,0]).
- **Learning Side and Size**: when there is no primary model, horizontal barriers must be symmetric; the classifier learns both direction and size.
- **Meta-Labeling**: primary (exogenous) model sets the side; secondary ML model learns a binary {0,1} (take the bet or pass); the size is derived from the secondary model's probability. Decouples side from size.
- **Quantamental way**: meta-labeling is exactly the tool discretionary + quant funds need — it layers an ML sizing filter on top of human/fundamental calls.

## Key Concepts
- Path-dependence: t_i,1 <= t_i,0+h; the label depends on the entire path, not just endpoints.
- Confusion matrix: precision = TP/(TP+FP), recall = TP/(TP+FN), accuracy = (TP+TN)/all, F1 = harmonic mean of precision and recall. Meta-labeling raises F1 by filtering false positives from a high-recall primary.
- Meta-labeling limits overfitting damage (ML only decides size, not side), enables separate long/short secondary models, and properly sizes good opportunities — "high accuracy on small bets and low accuracy on large bets will ruin you."

## Anti-patterns
- **Fixed threshold on time bars**: the dominant labeling error in the finance ML literature; most labels become 0 even when returns were predictable.
- Labeling positions that would have been stopped-out by the exchange/risk desk — purely unrealistic.
- Applying the same tau regardless of the prevailing volatility.
- Believing feature analysts develop strategies; they only catalogue findings for other stations.
- Letting sklearn's rare-label bug (issue #8566) silently corrupt classifiers — drop rare labels (Snippet 3.8) instead.

## Key Takeaways
- Replace fixed-time-horizon labels with the path-dependent triple-barrier method.
- Use dynamic (volatility-scaled) barriers, not constant thresholds.
- When you already know the side, use meta-labeling to learn only the size and to filter false positives.
- Meta-labeling converts any white-box/fundamental/human model into an ML system — the quantamental bridge.