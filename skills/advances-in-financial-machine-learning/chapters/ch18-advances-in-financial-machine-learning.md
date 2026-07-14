# Chapter 18: Entropy Features

## Core Idea
Shannon entropy measures the information content of a random process — high entropy = unpredictable, low = regular. The chapter makes entropy a **financial feature**: encode price bars as a message, estimate the entropy of returns (market efficiency, regime identification) via several estimators, and harness **mutual information** as a non-linear, distribution-free alternative to Pearson correlation. Entropy features quantify how much "structure" exists in a series and how much information one variable carries about another.

## Frameworks Introduced
- **Shannon's entropy** (1948): H[X] = −Σ p_x log p_x = E[−log f_X(x)]. R[X] ∈ [0,1] normalized entropy rate.
- **Kolmogorov complexity** (1965): formal link between entropy and the length of the shortest program describing a sequence.
- **Mutual information (MI)**: I[X,Y]=H[X]+H[Y]−H[X,Y]; non-negative, symmetric; for Gaussian reduces to −½log(1−ρ²) — a natural non-linear association measure.
- **Plug-in / maximum-likelihood estimator**: bin the series into states of width w whose count n ≫ w, estimate p via frequency, compute Ĥ — Snippet 18.1.
- **Lempel-Ziv (LZ) estimator**: decomposes the message into non-redundant substrings (dictionary size) — entropy as compression rate; robust even on short, non-stationary financial sequences.
- **Encoding schemes**: binary (up/down), quantile, sigma-based — choice of discretization bounds the entropy features one can extract.
- **Entropy of a Gaussian process**: closed-form scaled, expanding to potentially infinite features.
- **Entropy and the generalized mean**: derive entropy-like features (extends finite-feature family to the generalized mean).
- **Financial applications of entropy**: measuring market efficiency, the entropy of attribution across returns, and the entropy of feature importance (MDI convergence).

## Key Concepts
- Efficient market ⇒ returns are unpredictable ⇒ high entropy; low entropy signals exploitable structure.
- MI captures non-linear associations invisible to Pearson ρ — useful in finding redundant features (complements orthogonal features in Ch.8).
- Plug-in estimator needs many bins; choice of w drives bias/variance.
- LZ estimator sidesteps distributional assumptions — it counts "novelty" in the sequence directly.
- Entropy can be computed on MDI itself: how concentrated is the importance across features? (HHI analogue from Ch.14).

## Anti-patterns
- Using Pearson correlation to filter features when the relationship is non-linear.
- Choosing arbitrary bin width for the plug-in estimator without verifying n ≫ w.
- Interpreting normalized entropy R=1 as "noise" without checking for regime structure.
- Applying Gaussian-process entropy to heavy-tailed returns expecting correct results.
- Encoding financial bars naïvely (e.g., fixed thresholds) — quantile/sigma encodings better preserve information.

## Key Takeaways
1. Entropy quantifies predictability — low entropy ⇒ exploitable structure; high ⇒ efficient.
2. Mutual information is the non-linear generalization of correlation; prefer it for feature selection.
3. The LZ estimator is the most robust entropy feature for short, non-stationary financial series.
4. Encoding choice (binary/quantile/sigma) sets the upper bound on what you can learn.
5. Entropy of feature-importance distributions complements MDI/MDA (Ch.8) and HHI concentration (Ch.14).