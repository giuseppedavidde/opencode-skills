# Chapter 4: Optimal Clustering

## Core Idea
Clustering is an unsupervised-learning problem that appears at every step of the investment process (peer groups, risk concentration, flows, historical analogues). The hard sub-problem is not assigning objects to clusters — it is determining the **optimal number** and composition of clusters when the researcher does not know it a priori. This chapter introduces the **ONC (Optimal Number of Clusters)** algorithm, a three-stage modification of k-means that uses the silhouette quality statistic to recover the correct number of clusters from a shuffled block-diagonal correlation matrix.

## Frameworks Introduced
- **Proximity matrix**: an N×N matrix encoding similarity (correlation, mutual information) or dissimilarity (distance). Standardize features to prevent scale dominance. When `F >> N` (curse of dimensionality), project X (or the proximity matrix) onto a low-dim space whose dimension is given by the number of eigenvalues above `λ+` (Section 2).
- **Five types of clustering**: connectivity (hierarchical), centroids (k-means), distribution (mixtures), density (DBSCAN/OPTICS), subspace (biclustering). Different algorithms expect different inputs — biclustering on a distance matrix clusters the most *distant* elements (the opposite of k-means), so bicluster on the reciprocal of distance.
- **ONC base clustering**: k-means wrapped in a double loop — outer loop tries `k=2..N` with multiple random initializations, inner loop re-tries initializations — and picks the partition maximizing the t-statistic of silhouette scores `q = E[{Sᵢ}] / sqrt(V[{Sᵢ}])`.
- **Silhouette coefficient**: `Sᵢ = (bᵢ − aᵢ) / max{aᵢ, bᵢ}`, where `aᵢ` is intracluster distance and `bᵢ` is distance to the nearest cluster NOT containing `i`. `S=+1` well clustered, `S=−1` poorly clustered.
- **ONC higher-level clustering**: evaluate per-cluster average quality; collect clusters with below-average quality `K₁`; if `K₁ ≥ 2`, rerun the base algorithm only on those items. Keep the new clustering only if average cluster quality improves. This is recursive refinement of weak clusters.
- **Observations matrix for correlation clustering**: option (c) `Xᵢⱼ = sqrt(0.5·(1−ρᵢⱼ))` — the "distance of distances" approach — recognizes that `ρ: 0.9→1.0` is a bigger change than `ρ: 0.1→0.2`, and makes the distance a function of multiple correlations rather than a single one (more robust to outliers).
- **Monte Carlo validation** via random block correlation matrices (Code Snippet 4.3): shuffled K-block matrices with intra-block correlation `σ`, K-blocks of size ≥ M.

## Key Concepts
- Partitional vs hierarchical clustering: hierarchical produces a nested tree; partitional produces one flat partition. You can derive a partition from a hierarchy by restricting the tree, but not the reverse.
- The "elbow method" sets an arbitrary variance-explained threshold; ONC avoids this by using silhouette quality as an objective function.
- Détone the correlation matrix before clustering (Section 2) when a strong common component exists — otherwise the algorithm cannot find dissimilarities across clusters.
- PCA on the observations matrix before clustering raises the signal-to-noise ratio when N is large.
- Experimental results: ONC recovers the correct number of clusters with small errors across `N ∈ {20,40,80,160}`, `K/N` up to 0.5, with `E[K]/K ≈ 1`.

## Anti-patterns
- Hard-coding the number of clusters `K` without an objective function — k-means will return *something*, but it may be far from optimal.
- Single initialization of k-means — the result is random; always use multiple seeds and pick the best quality.
- Using the elbow method with an arbitrary variance-explained threshold.
- Biclustering directly on a distance matrix (will cluster the *most distant* items together) — use the reciprocal of distance or pass a similarity matrix.
- Forgetting to standardize features when building the proximity matrix.
- Clustering a non-detoned correlation matrix with a strong market component.

## Key Takeaways
1. k-means has two known weaknesses — `K` must be supplied and results depend on initialization; ONC fixes both with a silhouette-based objective function and multi-seed restarts.
2. Higher-level re-clustering of weak clusters adds recursive refinement: ONC keeps re-clustering below-average-quality clusters as long as it improves overall quality.
3. ONC is agnostic to the observations matrix — use correlation-based, variation-of-information, or any other metric.
4. Validate any clustering algorithm on shuffled block-diagonal matrices where the ground truth is known.
5. ONC is a building block reused later for clustered feature importance (Ch.6) and for estimating effective number of trials in testing-set overfitting (Ch.8).