# Glossary — Machine Learning for Asset Managers

Alphabetical reference of key terms from the book by Marcos M. López de Prado.
Each entry is a concise 1–2 sentence definition; see the linked chapter file for
full context. Cross-references are marked `→`.

---

**Backtest (as anti-pattern)** — A backtest can only provide evidence of a *false*
positive; it can never prove a true positive. Used as a *research* tool (backtest–tweak–backtest cycle), it guarantees overfitting → Ch.1, Ch.8.

**Bet sizing (expected Sharpe)** — `z = (p − ½)/√(p(1−p))`, `m = 2·Z[z] − 1 ∈ [−1,1]`;
translates a meta-labeler's probability into a uniform bet size via the
expected Sharpe ratio → Ch.5.

**Black–Litterman** — A "priors" remedy for Markowitz instability that blends the
investor's views with an equilibrium prior; addresses *noise* but not *signal*
instability → Ch.7.

**Block-diagonal signal instability** — A 500×500 matrix with two blocks at
intra-cluster corr 0.5 has condition number ~251 — this instability is
*structural*, independent of N/T, and not cured by more observations → Ch.7.

**Bonferroni correction** — Approximation `α ≈ α_K/K` for FWER; Šidàk's exact form
`α = 1 − (1−α_K)^(1/K)` is preferred → Ch.8.

**CLT Hail Mary pass** — Anti-pattern: invoking the Central Limit Theorem to justify
linear regression everywhere. The sample *mean* converges to Gaussian (under IID),
not the sample itself → Ch.1.

**CFI (Clustered Feature Importance)** — Capstone method: cluster features with
ONC (preferably in ṼI space), then compute MDI/MDA at the cluster level,
shuffling all features in a cluster simultaneously for MDA → Ch.6.

**Clarke et al. constraints** — A "extra constraints" remedy for Markowitz
instability via turnover/position caps; addresses *noise* but not *signal* → Ch.7.

**Clustered MDA / Clustered MDI** — Clustered MDI sums each feature's MDI within a
cluster (one value per cluster per tree); clustered MDA shuffles *all* features in
a cluster at once → Ch.6.

**Combinatorial Purged Cross-Validation (CPCV)** — Cross-validation scheme that
purges overlapping observations between train and test folds; defense against
train-set overfitting in financial (autocorrelated) data → App. A, Ch.1.

**Condition number** — `max|λ| / min|λ|` of a correlation matrix; for a 2×2 matrix
it diverges as `ρ → ±1`. Denoising lowers it by raising the smallest eigenvalue;
detoning lowers it further by removing the largest → Ch.2, Ch.7.

**Conditional entropy** — `H[X|Y] = H[X,Y] − H[Y]`; the remaining uncertainty in X
once Y is known → Ch.3.

**Constant Residual Eigenvalue method** — Denoising that replaces every noise
eigenvalue (those below `λ+`) with a constant equal to their average (trace
preserving), then rescales the diagonal to 1. Default denoising choice → Ch.2.

**Correlation-as-metric transform** — `d_ρ = √(0.5(1−ρ))` (true metric after
z-standardization) and `d_|ρ| = 1 − |ρ|` (true metric on the ℤ/2ℤ quotient) —
turning correlation into a proper distance → Ch.3.

**Cross-entropy** — `H_C[p‖q] = H[X] + D_KL[p‖q]`; the entropy of the true
distribution plus the KL penalty for using a wrong one → Ch.3.

**Deflated Sharpe Ratio (DSR)** — `DSR = Z[(ŜR − E[max{ŜR_k}])·√(T−1) /
√(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²)]`; the probability that the observed Sharpe exceeds
the expected max under H0, adjusted for skewness, kurtosis, sample length, and
multiple testing → Ch.8.

**Denoising** — Separating eigenvalues associated with noise from those carrying
signal via the Marcenko–Pastur fit, then repairing the matrix without diluting
signal. Outperforms Ledoit–Wolf shrinkage in Monte Carlo → Ch.2.

**Detoning** — Subtracting the market eigencomponent(s) (first eigenvector[s]) from
the denoised matrix so that subtler structural signals (sector, industry, size)
emerge for clustering. The detoned matrix is singular → optimize in PC space → Ch.2.

**Discretization (optimal)** — Hacine-Gharbi & Ravier closed-form bin counts `B_X(N,ρ)`
that minimize bias when estimating entropy on binned continuous samples → Ch.3.

**Dominant block propagation** — In a block-diagonal correlation matrix the condition
number is governed by the *highest*-correlation cluster; reducing weaker blocks
does not help → Ch.7.

**Elbow method** — Setting an arbitrary variance-explained threshold to choose K in
clustering; ONC avoids it by using silhouette quality as an objective → Ch.4.

**Ensemble bet sizing** — For `n` meta-labeling classifiers, `m = 2·t_{n−1}[t] − 1`
with `t = (p̂−½)/√(p̂(1−p̂)/n)`, using de Moivre–Laplace / Lindeberg–Lévy
convergence to a t-distribution → Ch.5.

**Euler–Mascheroni constant γ** — Appears in the False Strategy theorem's asymptotic
unbiased estimate of `E[max{ŜR_k}]` → Ch.8.

**False Strategy theorem** — For K trials under H0, `E[max{ŜR_k}] ≈
((1−γ)·Z⁻¹(1−1/K) + γ·Z⁻¹(1−(K·e)⁻¹))·√(V[{ŜR_k}])`; even with true SR=0,
selecting the best of 1000 trials yields an expected max SR ≈ 3.26 → Ch.8.

**Familywise Error Rate (FWER)** — `α_K = 1 − (1−α)^K`; probability of at least one
false positive among K tests. Bonferroni approximates it as `α·K` → Ch.8.

**Feature importance** — ML tool that replaces backtesting as a means of theory
discovery: decouples the *variable* search from the *specification* search → Ch.6.

**Financial labels** — The label defines the supervised task; methods include
fixed-horizon, triple-barrier, trend-scanning, and meta-labeling → Ch.5.

**Fixed-horizon labeling** — `y ∈ {−1,0,1}` from return over `h` bars vs threshold
`τ`; the academic default, with three structural flaws: heteroscedastic label
distributions, ignores path, forecasts an impractical event → Ch.5.

**Five scientific uses of ML** — Existence, Importance, Causation, Reductionist,
Retriever: ML as a theory-*discovery* engine rather than a prediction oracle → Ch.1.

**FWER via Šidàk** — Exact critical value `z_α = Z⁻¹[(1−α_K)^(1/K)]`; reject H0 if
`max_k ẑ[0]_k > z_α`. Šidàk preferred over Bonferroni's approximation → Ch.8.

**Hierarchical Risk Parity (HRP)** — López de Prado 2016 ML allocation that beats
Markowitz out-of-sample despite being suboptimal in-sample; a precursor to NCO → Ch.7.

**Information gain** — `Δg[t,f] = i[t] − (N_t^(0)/N_t)·i[t^(0)] − (N_t^(1)/N_t)·i[t^(1)]`;
the impurity reduction at node `t` due to feature `f`; weighted across nodes for
MDI → Ch.6.

**Intracluster / Intercluster allocation** — NCO splits the problem: optimize
weights within each cluster (intracluster), then optimize across clusters on the
reduced near-diagonal covariance `cov2 = W_intra'·cov1·W_intra` (intercluster);
final `ω = W_intra · ω_inter` → Ch.7.

**Joint entropy** — `H[X,Y] = −Σ p[x,y] log p[x,y]`; total uncertainty of the pair → Ch.3.

**k-means** — Partitional centroid clustering with two weaknesses: K must be
supplied and results depend on random initialization → Ch.4.

**KL divergence** — `D_KL[p‖q] = Σ p log(p/q)`; non-symmetric, non-metric,
non-negative; central to variational inference. Treating it as symmetric misleads → Ch.3.

**LASSO** — L1 regularization; a train-set overfitting remedy alongside resampling,
early stopping, and drop-out → Ch.1.

**Ledoit–Wolf shrinkage** — Shrinking the covariance toward a diagonal without
discriminating noise from signal; dilutes signal. Adds little beyond denoising → Ch.2.

**Marcenko–Pastur (MP) theorem** — Asymptotic PDF of eigenvalues of a random
covariance matrix. Eigenvalues in `[λ−, λ+]` are noise; those above `λ+` carry
signal → Ch.2.

**Markowitz's curse** — Mean-variance optimization is numerically stable only when
`ρ ≈ 0`, i.e. exactly when diversification help is unnecessary → Ch.7.

**MDA (Mean Decrease Accuracy)** — Permutation importance: shuffle each feature
column and measure the cross-validated performance drop. Solves all 4 p-value
caveats; on two identical features may render both unimportant → Ch.6.

**MDI (Mean Decrease Impurity)** — Breiman 2001; tree-internal impurity-reduction
weights per feature, bounded [0,1] summing to 1. Solves caveats #1–3 but remains
in-sample → Ch.6.

**Meta-labeling** — A secondary classifier trained on the *outcomes* of a primary
side-model (loss=0, gain=1): predicts *whether* the primary will succeed; the
probability sizes the bet. Trades recall for precision → Ch.5.

**Minimum-variance cluster returns** — When computing `V[{ŜR_k}]` across trial
clusters, weight each cluster's strategy series by minimum-variance to prevent
high-variance trials from dominating → Ch.8.

**Mutual Information** — `I[X,Y] = H[X] − H[X|Y] = D_KL[p(x,y)‖p(x)p(y)]`; shared
information. Not a metric (fails triangle inequality) but has the grouping
property useful for agglomerative clustering → Ch.3.

**NCO (Nested Clustered Optimization)** — Wrapper that clusters the denoised
correlation (ONC), optimizes intracluster, then intercluster on the reduced
covariance. Halves Markowitz RMSE out-of-sample; modular (any inner optimizer) → Ch.7.

**Noise variance σ²** — Fitted parameter of the MP PDF; `σ²≈0.677` ⇒ ~32% signal —
this fraction *is* the financial signal-to-noise ratio → Ch.2.

**Normalized Mutual Information (NMI)** — Behaves like `|ρ|` for Gaussians (`I =
−½ log(1−ρ²)`) but detects nonlinear relationships (e.g. `y=100|x|+ε`: NMI≈0.64
vs corr≈0) → Ch.3.

**Normalized Variation of Information** — `ṼI[X;Y] = 1 − I[X;Y]/H[X;Y]`; a true
metric bounded in [0,1] capturing *nonlinear* codependency with minimal
distribution assumptions. The information-theoretic analogue of correlation → Ch.3.

**N/T ratio** — Observations-to-features ratio controlling random-eigenvalue
boundary `λ+`; regulates noise-induced instability → Ch.2, Ch.7.

**Odds ratio θ** — `θ = s_T/s_F`; the ratio of true to false strategies. In finance
θ is low (e.g. 1/99); precision collapses even at low α → Ch.8.

**ONC (Optimal Number of Clusters)** — k-means wrapped in a double loop over `k=2..N`
with multiple seeds, scored by silhouette t-statistic `q = E[{Sᵢ}]/√(V[{Sᵢ}])`, with
recursive higher-level re-clustering of below-average clusters → Ch.4.

**Orthogonalization (PCA)** — Project features to orthogonal PCs and run MDI/MDA on
them; caveats: nonlinear redundancy survives and PCs lose interpretability → Ch.6.

**Path-dependent labels** — Labels encoding the path (which barrier touched first)
vs. point labels (sign of a single future return) → Ch.5.

**p-value caveats (four)** — (1) built on strong distributional assumptions;
(2) meaningless under multicollinearity (substitution effects); (3) estimates
`P(result|H0)` not `P(H0|result)`; (4) in-sample, enabling p-hacking → Ch.6.

**Precision-Weighted Accuracy (PWA)** — `PWA = Σ yₙ·(pₙ−K⁻¹) / Σ (pₙ−K⁻¹)`; penalizes
high-confidence wrong predictions, bounded [0,1]; bridges accuracy (ignores
probabilities) and log-loss (harsh) → Ch.6.

**Precision / recall (strategy testing)** — `precision = (1−β)·θ / ((1−β)·θ + α)`,
`recall = 1 − β`. At θ=1/99, α=0.05, β=0.2: FDR ≈ 86% → Ch.8.

**Proximity matrix** — N×N matrix encoding similarity (correlation, MI) or
dissimilarity (distance); standardize features first and project via PCA when
`F >> N` (curse of dimensionality) → Ch.4.

**Quadratic-programming formulation** — `min_ω ½ω'Vω` s.t. `ω'a = 1`, closed form
`ω* = V⁻¹a/(a'V⁻¹a)`; naïve, inverse-variance, min-variance and max-Sharpe are
special cases via the characteristic vector `a` → Ch.7.

**Random Block Correlation** — Monte Carlo ground-truth matrix generator (shuffled
K-block matrices, intra-block corr σ) for validating clustering algorithms → Ch.4.

**Recursive NCO** — Applying NCO recursively within subclusters to mirror a
hierarchical tree structure of clusters-within-clusters → Ch.7.

**Reductionist / Retriever uses of ML** — Two of the five scientific uses:
Reductionist compresses a problem into its driving variables; Retriever finds
analogue historical episodes → Ch.1.

**Separation theorem** — Any unconstrained efficient-frontier portfolio is a convex
combination of the minimum-variance and maximum-Sharpe portfolios → testing these
two is sufficient → Ch.7.

**Shannon entropy** — `H[X] = −Σ p[x] log p[x]`; expected surprise; zero for a
deterministic variable, maximal (`log ‖S_X‖`) for uniform distribution → Ch.3.

**SBuMT (Selection Bias under Multiple Testing)** — Two-stage compounding: each
researcher runs millions of trials; the firm selects the best of already-overfit
backtests ("backtest hyper-fitting") → Ch.8.

**Silhouette coefficient** — `Sᵢ = (bᵢ − aᵢ) / max{aᵢ, bᵢ}` with `aᵢ` intra-cluster
distance and `bᵢ` nearest-cluster distance; `S=+1` well clustered, `S=−1` misfit.
ONC uses its t-statistic as the objective → Ch.4.

**Substitution effects** — In multicollinear datasets two identical features halve
each other's MDI and may render each other unimportant in MDA; the motivation for
CFI → Ch.6.

**Targeted shrinkage** — Denoising variant: split the matrix into signal (L) and
noise (R) blocks and shrink only the noise block by `α ≥ 0`, preserving the
signal block intact (`α→0` fully shrinks the noise) → Ch.2.

**Threshold method** — Denoising anti-pattern: keep components that explain a fixed
variance share — ignores the true noise-driven variance → Ch.2.

**Time / Volume / Dollar bars** — Time bars exhibit intraday seasonality producing
non-stationary labels; volume or dollar bars (or standardized returns `z = r/σ`)
mitigate the heteroscedasticity of fixed-horizon labels → Ch.5.

**Trend-scanning** — For each look-forward `L` fit `x_{t+l} = β0 + β1·l + ε`, choose
the L with max `|t̂(β̂1)|`, label by sign of `t̂(β̂1)`. No barriers, no fixed
horizon; doubles as regression target or sample weights → Ch.5.

**Triple-barrier labeling** — Two horizontal barriers (profit-taking, stop-loss) +
one vertical (max holding); label is the *first* barrier touched, embedding path
information and realistic trading mechanics → Ch.5.

**Two overfitting types** — Train-set (model fits noise; fought via resampling,
regularization, ensembles) vs. test-set (researcher fits the *test set* by running
many trials; invisible to backtests; fought via DSR/FWER/CPCV) → Ch.1, Ch.8.

**Variation of Information (VI)** — `VI[X,Y] = H[X|Y] + H[Y|X] = H[X,Y] − I[X,Y]`; a
*true* metric (non-negative, symmetric, triangle inequality). Generalizes to
distance between partitions (Meilă) → Ch.3.

**VPIN theory** — A market-microstructure theory trained on order-flow imbalance
that anticipated a flash-crash anecdote; demonstrates that *theories*, not
historical data, predict the never-seen-before → Ch.1.

**Šidàk correction** — Exact FWER single-trial level `α = 1 − (1−α_K)^(1/K)`;
preferred over Bonferroni's `α ≈ α_K/K` → Ch.8.