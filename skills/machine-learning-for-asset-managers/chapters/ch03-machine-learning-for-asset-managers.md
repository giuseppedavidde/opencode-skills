# Chapter 3: Distance Metrics

## Core Idea
Correlation measures only linear codependency, is distorted by outliers, and is not a true metric. Drawing on information theory, this chapter generalizes the notion of distance between random variables: **normalized variation of information** is a bounded [0,1] metric that captures nonlinear codependency with minimal assumptions about the underlying distribution, making it the information-theoretic analogue of the correlation coefficient.

## Frameworks Introduced
- **Correlation-as-metric transform**: `d_ρ[X,Y] = sqrt(0.5 (1 − ρ[X,Y]))` and `d_|ρ|[X,Y] = 1 − |ρ[X,Y]|` are proven to be true metrics (on the ℤ/2ℤ quotient for the absolute case) by reduction to z-standardized Euclidean distance.
- **Entropy hierarchy**: marginal `H[X]`, joint `H[X,Y]`, conditional `H[X|Y]`, cross-entropy `H_C[p‖q] = H[X] + D_KL[p‖q]`, mutual information `I[X,Y]`, and variation of information `VI[X,Y] = H[X|Y] + H[Y|X]` — all interrelated and visualized in a single Venn-style diagram (Figure 3.1).
- **Optimal discretization for continuous variables**: Hacine-Gharbi & Ravier binning formulas choose `B_X` as a function of `N` and `ρ` to minimize bias when computing entropy on binned samples.
- **Distance between partitions** (Meilă): VI extended to compare two clusterings of the same dataset — a metric bounded by `log ‖D‖` and `2 log √K`.

## Key Concepts
- **Shannon entropy** `H[X] = −Σ p[x] log p[x]`: expected surprise; zero for a deterministic variable, maximal (`log ‖S_X‖`) for the uniform distribution.
- **Kullback–Leibler divergence** `D_KL[p‖q] = Σ p log(p/q)`: non-symmetric, non-metric, but non-negative; central to variational inference.
- **Mutual information** `I[X,Y] = H[X] − H[X|Y] = D_KL[p(x,y) ‖ p(x)p(y)]`: information shared; not a metric (fails triangle inequality), but has the grouping property useful for agglomerative clustering and forward feature selection.
- **Variation of information** `VI[X,Y] = H[X,Y] − I[X,Y]`: a *true metric* satisfying non-negativity, symmetry, and triangle inequality; normalized variants bound it to [0,1].
- **Normalized mutual information (NMI)**: behaves like `|ρ|` for Gaussians (`I = −½ log(1 − ρ²)`) but, unlike correlation, detects nonlinear relationships such as `y = 100|x| + ε` (NMI ≈ 0.64 vs. corr ≈ 0).
- **Discretization bias**: results depend on bin count; optimal `B_X` differs for univariate (entropy) vs. bivariate (joint entropy) cases.

## Anti-patterns
- **Treating correlation as a metric**: it violates non-negativity and triangle inequality; differences (0.9,1.0) and (0.1,0.2) are numerically equal but represent very different codependence changes.
- **Using correlation to measure nonlinear codependence**: a strong symmetric nonlinear relationship (`y = 100|x| + e`) yields correlation ≈ 0 while NMI ≈ 0.64 — correlation is structurally blind to it.
- **Applying correlation outside the bivariate-Normal case**: the coefficient can be computed on any two real variables, but it is typically meaningless unless jointly Gaussian.
- **Computing KL divergence as if symmetric**: `D_KL[p‖q] ≠ D_KL[q‖p]` — using it where a symmetric distance is required misleads clustering and inference.
- **Treating mutual information as a metric**: MI satisfies neither the triangle inequality nor a firm upper bound; using it directly as a clustering distance produces incoherent topologies.
- **Arbitrary binning for entropy estimation**: choosing `B_X` without the Hacine-Gharbi/Ravier formulas injects sample-size- and correlation-dependent bias into downstream distance computations.
- **Ignoring the LDDP caveat for continuous variables**: Shannon's entropy is finite only for discrete variables — applying it naively to continuous data without discretization yields undefined/divergent quantities.

## Key Takeaways
1. Correlation's three caveats (linearity, outlier sensitivity, Normal-only validity) demand information-theoretic alternatives.
2. Normalized variation of information is the recommended distance metric for nonlinear codependency — bounded, true metric, assumption-light.
3. Variation of information generalizes cleanly to *partitions*, enabling principled comparison of clustering algorithms across datasets.
4. Optimal discretization bin counts are closed-form functions of `N` and `ρ`; ignoring them biases every entropy-based estimate.
5. Because ML algorithms do not impose a functional form, pairing them with entropy-based features aligns naturally with non-linear distance metrics.