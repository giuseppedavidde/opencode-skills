# Cheatsheet — Advances in Financial Machine Learning

Quick-reference decision tables for the full pipeline.

## Pipeline Decision Map

| Stage | Chapter | Go-to Tool | Reject If |
|---|---|---|---|
| Bars | 2 | Dollar / imbalance bars + CUSUM filter | Time bars only (heteroscedastic, non-normal) |
| Labels | 3 | Triple-barrier + meta-labeling | Fixed-time horizon (ignores path & vol) |
| Weights | 4 | Average-uniqueness + sequential bootstrap | Standard bootstrap (~63.2% unique, low ρ) |
| Features | 5 | FFD minimum d* | Integer d=1 (erases memory) |
| Models | 6 | RF/Bagging w/ max_samples=avgU | RF on redundant samples (ρ→1) |
| CV/fit | 7,9 | Purged K-Fold + embargo; scoring=f1 (meta), neg_log_loss (strategy) | Shuffle + k-fold (leakage) |
| Importance | 8 | MDI(max_features=1) + MDA on PCA-perturbed; SFI to isolate | Accuracy-only scoring on imbalanced labels |
| Bet size | 10 | Concave f[p] + discretization + limit-price schedule | Constant or linear sizing |
| Backtest | 11,12,14 | CPCV → DSR gate; never research under backtest influence | Single WF path (no Sharpe distribution) |
| Allocation | 16 | HRP (tree-cluster + recursive bisection) | Markowitz CLA on ill-conditioned covariance |
| Risk | 15 | Strategy-risk precision-PDF integral | Portfolio variance alone |
| HPC | 20–22 | mpPandasObj + nestedParts + mpBatches; HDF5 + MPI | Single-thread on ≥1M-atom jobs |

## Triple-Barrier Configurations (Ch.3)

| [pt, sl, t1] | Use |
|---|---|
| [1,1,1] | symmetric: take-profit, stop-loss, expiry |
| [0,1,1] | stop + expiry only (marts/trailing) |
| [1,1,0] | take/stop only (no expiry) |
| (others) | avoid — useless or redundant |

## Scoring Selector (Ch.9)

| Task | Scoring |
|---|---|
| Meta-labeling (binary {0,1}) | `f1` |
| Strategy tuning (sized bets) | `neg_log_loss` |
| Generic classifier tuning | `accuracy` (only if balanced & risk-equal) |

## Cross-Validation Method Selector (Ch.12)

| Method | Paths | Sharpe dist? | Leakage |
|---|---|---|---|
| Walk-Forward | 1 | no | none (gaps) |
| K-Fold CV | k | no | must purge+embargo |
| CPCV (N,k) | φ[N,k] | **yes** | purge+embargo |

## Backtest Rejection Checklist

| Red flag | Source |
|---|---|
| Sharpe >> 1 on a single WF path | Ch.11 |
| OOB accuracy >> CV accuracy | Ch.4 |
| Improve as k→T (purge catches it) | Ch.7 |
| DSR < 0.95 after logging N trials | Ch.11/14 |
| HRP ≫ CLA out-of-sample | Ch.16 (signal CLA failed) |
| Strategy risk ∫ f[p] under p* > threshold | Ch.15 |
| No feature survives MDA (negative importance) | Ch.8 |

## Bars Cheat (Ch.2)

| Type | Pros | Cons |
|---|---|---|
| Time | simple | oversamples slow periods |
| Tick / Volume / Dollar | activity-sampled | needs raw trades |
| Imbalance (TIB/VIB/DIB) | samples on informed flow | more code |
| Runs (TRB/VRB/DRB) | captures trends | more code |

## Differentiation Cheat (Ch.5)

| d | Result | Corr to price |
|---|---|---|
| 0 | price (memory, non-stationary) | 1.0 |
| d*=0.35 (E-mini) | ADF p<5%, stationary | 0.995 |
| 1 | integer returns (stationary, memoryless) | 0.03 |

## Partition Selector (Ch.20)

| Atom-cost variance | Partition | mpBatches |
|---|---|---|
| uniform | linParts | 1 ok |
| triangular (j≤i) | nestedParts | >1 helps |
| output huge RAM | use `redux` on the fly | — |

## HPC Stack (Ch.22)

| Tool | Role | Speedup |
|---|---|---|
| MPI | interprocessor comms | linear cores |
| HDF5 + indexing | multi-dim array I/O | 21x I/O |
| ADIOS + ICEE | in-situ streaming | real-time |
| C++ VPIN + MPI | early-warning | 234x–720x |

## Allocation Method (Ch.16)

| Input | Method |
|---|---|
| well-conditioned Σ, low ρ | Markowitz/CLA ok |
| ill-conditioned Σ | **HRP** (no inverse) |
| unknown rank covariance | see Snippet 21.4 |

## Two Laws (memorize)

1. **First Law** (Ch.8): "Backtesting is not a research tool. Feature importance is."
2. **Second Law** (Ch.11): "Backtesting while researching is like drinking and driving."