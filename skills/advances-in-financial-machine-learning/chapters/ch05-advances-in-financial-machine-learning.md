# Chapter 5: Fractionally Differentiated Features

## Core Idea
For stationarity, finance applies integer differentiation (d=1 -> returns), which wipes out all memory that wasn't needed. But d=1 is arbitrary; d=0 (levels) is as arbitrary. There is a wide region between 0 and 1 where a series can be made stationary while preserving maximum memory — and hence predictive power. López de Prado generalizes the difference operator to a real exponent d, introducing **fractional differentiation** as a finance feature transform that resolves the stationarity-vs-memory dilemma.

## Frameworks Introduced
- **Stationarity vs. Memory Dilemma**: returns are stationary but memory-less; prices have memory but are non-stationary. We want the minimum d that makes the series stationary while preserving as much memory as possible.
- **Fractional Difference Operator**: using the backshift operator (1-B)^d with the binomial series expansion for real d, weights omega_k = prod_{i=0..k-1} [(d-i)/ (k-i)] * (-1)^k. For integer d the weights cancel to zero after a finite window; for fractional 0<d<1 they decay asymptotically to zero, alternating in sign — preserving memory.
- **Expanding-window Fracdiff**: computes the full infinite series truncated at the sample start; suffers a negative drift because early points carry different memory than late points (weight-loss l_l > tau).
- **Fixed-Width Window Fracdiff (FFD)**: drops weights once |omega_k| < tau, applying the *same* weight vector to every estimate — produces a driftless, stationary blend of level + noise.
- **Stationarity with Maximum Memory Preservation**: find the minimum d* such that the ADF p-value on FFD(d*) falls below 5%; d* quantifies the memory that must be removed. d*=0 (already stationary), d*<1 (unit root), d*>1 (explosive), 0<d*<<1 (mildly non-stationary, where full integer differentiation is wasteful).

## Key Concepts
- On E-mini S&P 500 futures, FFD crosses the ADF 5% critical value near d=0.35, where the correlation to the original series is still 0.995 — versus only 0.03 for d=1 integer returns.
- Table 5.1: across 87 liquid futures, standard d=1 implies over-differentiation in every case; stationarity is achieved with d < 0.6, and for orange juice/live cattle no differentiation was needed.
- Alternatives contrasted: Box-Jenkins (returns: stationary, memory-less) vs. Engle-Granger cointegration (log-prices: memory, non-stationary). FFD removes the need to choose between them for ML forecasting.
- Practical recipe: cumulative sum -> FFD(d) for d in [0,1] -> pick minimum d with ADF p<5% -> use FFD(d) as the predictive feature.

## Anti-patterns
- **Integer differentiation by default**: applying d=1 "because econometrics does it" over-differentiates and destroys signal, biasing the literature toward the efficient-markets hypothesis.
- Using **expanding-window** fracdiff without controlling for weight loss — introduces a spurious negative drift.
- Treating fractional differentiation as purely technical — Hosking (1981) introduced ARIMA(p,d,q) with fractional d; the literature is surprisingly scarce.
- Achieving stationarity and assuming predictive power follows — stationarity is necessary but not sufficient.

## Key Takeaways
- Returns are merely one (often suboptimal) price transformation among many; FFD lets you generalize them.
- Use FFD with a fixed-width window (weight-loss tolerance tau) to avoid drift.
- Calibrate the minimum d* per series via the ADF test; almost always d* is well below 1.
- Preserve maximum memory while gaining stationarity — this is the data-side precondition for predictive ML.