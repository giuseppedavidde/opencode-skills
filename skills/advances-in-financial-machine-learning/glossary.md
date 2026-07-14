# Glossary — Advances in Financial Machine Learning

Alphabetical reference for the 22 chapters. Terms are grouped under their defining chapter in parentheses.

**ADF (Augmented Dickey-Fuller)** — (Ch.5,17) unit-root stationarity test; the FFD minimum d* is the smallest d whose ADF p-value < 5%.

**ADIOS** — (Ch.22) Adaptable I/O System; in-situ processing library with the ICEE transport engine for real-time distributed streaming analysis.

**Amihud's lambda** — (Ch.19) daily price response per dollar of volume |r_t|/(p_t V_t); rank-correlates with intraday effective spread.

**Atoms and Molecules** — (Ch.20) indivisible tasks (atoms) grouped into parallelizable units (molecules) processed by a single-thread callback.

**Average Uniqueness (ū_i)** — (Ch.4) harmonic-mean-style non-overlap score = mean_t(1_{t,i}/c_t) ∈ [0,1].

**Bagging (Bootstrap Aggregation)** — (Ch.6) N bootstrapped estimators averaged; variance reduction σ²/N·(1+ρ(N−1)) helps only if ρ→0.

**Bars** — (Ch.2) sampling units: Time, Tick, Volume, Dollar; information-driven Imbalance (TIB/VIB/DIB) and Runs (TRB/VRB/DRB) bars sample more when informed trading arrives.

**Bet Sizing** — (Ch.10) mapping probability p to position size via concave f[p,I,d]; separates alpha from its monetization.

**Brown-Durbin-Evans CUSUM** — (Ch.17) CUSUM on recursive residuals from expanding-window RLS.

**CADF (Conditional ADF)** — (Ch.17) conditional moment of the high-ADF distribution; ≤ SADF, less outlier-sensitive.

**Combinatorial Purged Cross-Validation (CPCV)** — (Ch.12) choose N groups and test-size k; yields φ[N,k] ≥ 1 backtest paths and a *distribution* of Sharpe ratios.

**Combinatorially Symmetric Cross-Validation (CSCV)** — (Ch.11) framework for Probability of Backtest Overfitting (PBO).

**Corwin-Schultz spread** — (Ch.19) bid-ask spread estimator from intra-bar high/low prices.

**CUSUM filter** — (Ch.2,17) event-based sampling; trigger a bar only when a cumulative run-up/down of length h occurs.

**Deflated Sharpe Ratio (DSR)** — (Ch.14) PSR where SR* is the expected maximum SR under multiple testing; controls for how many strategies were tried.

**Discrete O-U process** — (Ch.13) P_t = (1-φ)target + φ P_{t-1} + σ ε; basis for the OTR calibration; half-life τ = -log2/log(φ).

**Dynamic Thresholds** — (Ch.3) profit-taking/stop-loss limits as a function of EWMA std of returns.

**Embargo** — (Ch.7) drop training observations immediately after every test set; one-sided because pre-test training contains no future info.

**Entropy (Shannon)** — (Ch.18) H[X]=−Σ p log p; efficient market ⇒ high entropy ⇒ unpredictable returns.

**ETF trick** — (Ch.2) represent any basket/spread/rolled-future as the strictly-positive value of $1 invested with embedded carry and costs.

**expandCall** — (Ch.20) unwraps a job dictionary into callback kwargs; the core trick turning a dict into a parallel task.

**Feature Importance** — (Ch.8) MDI (in-sample, tree-only), MDA (permutation, OOS, any classifier), SFI (single-feature, no substitution effects).

**First Law of Backtesting** — (Ch.8) "Backtesting is not a research tool. Feature importance is."

**Fractional Differentiation (FFD)** — (Ch.5) (1-B)^d with binomial weights that decay asymptotically; minimum d* yielding stationarity while preserving memory.

**Garleanu-Pedersen** — (Ch.21) dynamic trading with predictable returns; contrasted because it assumes IID Gaussian whereas the chapter's method does not.

**Global Interpreter Lock (GIL)** — (Ch.20) limits Python multithreading to one write-thread per processor — the reason Python relies on multiprocessing.

**Heisenbug** — (Ch.20) a multiprocessing bug whose behavior changes under scrutiny; debug sequentially with numThreads=1.

**Hierarchical Risk Parity (HRP)** — (Ch.16) tree-clustering + quasi-diagonalization + recursive bisection; weights from 1/σ², no covariance inverse needed.

**HHI (Herfindahl-Hirschman Index)** — (Ch.14,22) concentration measure; used for bet concentration and for market fragmentation.

**HDF5** — (Ch.22) Hierarchical Data Format 5; multi-dimensional array library with efficient compression; 21x data-access speedup on stock data.

**ICEE transport engine** — (Ch.22) ADIOS engine enabling distributed real-time collaborative analysis (KSTAR fusion).

**Information-driven bars** — (Ch.2) imbalance/runs bars that sample more frequently when informed trading arrives.

**Inverse Variance Allocation** — (Ch.16) cluster weight ∝ 1/σ²; used in HRP's recursive bisection.

**Kyle's lambda** — (Ch.19) price-impact coefficient from regressing price changes on signed volume; informed profit grows with mispricing and noise-trader variance.

**Lempel-Ziv (LZ) estimator** — (Ch.18) entropy as compression rate; robust on short non-stationary sequences.

**linParts / nestedParts** — (Ch.20) linear vs two-nested-loops partition functions; nestedParts solves bin-packing for triangular atom-cost structures.

**Log-Uniform distribution** — (Ch.9) sample log[x]∼U[log a, log b] for non-negative hyper-parameters (SVC C, RBF γ).

**LTAP** — (Ch.22) white-box baseline model for daily peak electricity usage; piece-wise linear in average daily temperature; self-consistent for year T−1.

**Marcos' Second Law of Backtesting** — (Ch.11) "Backtesting while researching is like drinking and driving."

**Markowitz's Curse** — (Ch.16) higher correlation → more need to diversify → more leverage → more unstable covariance inversion → solutions blow up.

**MDI (Mean Decrease Impurity)** — (Ch.8) fast in-sample tree feature importance; set max_features=1 to prevent masking.

**Meta-Labeling** — (Ch.3) primary model sets side; secondary ML model decides binary {0,1} take/pass; size derived from secondary probability.

**MPI (Message Passing Interface)** — (Ch.22) HPC communication protocol; point-to-point + collective operations; MPICH open-source reference.

**mpPandasObj** — (Ch.20) thin multiprocessing engine (func/pdObj/numThreads/mpBatches/linMols/kargs); front-loads heavy molecules.

**Non-uniform FFT** — (Ch.22) Fourier analysis on irregularly spaced tick data; reveals once-per-minute TWAP algorithmic trading in natural-gas futures.

**Ornstein-Uhlenbeck (discrete)** — see Discrete O-U process.

**OTR (Optimal Trading Rule)** — (Ch.13) unique (profit-taking, stop-loss) pair maximizing Sharpe under an O-U price process.

**PCA weights** — (Ch.2) hedging allocations from a target risk distribution across principal components.

**PIN (Probability of Informed Trading)** — (Ch.19) mixture of three Poissons on buy/sell volumes with parameters {α,δ,μ,ε}.

**Pigeonhole partition** — (Ch.21) number of ways to allocate K units of capital among N assets = non-negative integer solutions to x_1+…+x_N=K; order matters.

**Probabilistic Sharpe Ratio (PSR)** — (Ch.14) P(SR > SR*) given observed SR, sample length, skewness, kurtosis.

**Probability of Backtest Overfitting (PBO)** — (Ch.11) P[logit λ_c < 0] under CSCV; high logit ⇒ consistency between IS and OOS.

**Purging** — (Ch.7) drop training observations whose label overlaps in time with any testing label.

**Purged K-Fold** — (Ch.7) sklearn KFold extension that purges + embargoes to prevent leakage during fitting/backtesting/evaluation.

**QADF (Quantile ADF)** — (Ch.17) high quantile (e.g. 0.95) of the ADF values; more robust than supremum.

**Quantamental way** — (Ch.1,3) discretionary PMs + ML; meta-labeling is the canonical tool.

**Runs statistics** — (Ch.14) HHI of bet-concentration over time and of returns; drawdown (DD) and time-under-water (TuW).

**SADF (Supremum ADF)** — (Ch.17) sup over starting points t_0 of the ADF statistic at endpoint t; runs O(T²); needs HPC.

**Sequential bootstrap** — (Ch.4) redraws with δ updated to prefer unique features; expected uniqueness ≈ 0.7 vs 0.6 standard.

**Seven Sins of Quantitative Investing** — (Ch.11) survivorship, look-ahead, storytelling, data mining/snooping, transaction costs, outliers, shorting, etc.

**Sharpe Ratio (SR)** — (Ch.14) assumes IID Gaussian μ,σ; mis-specified under skew/kurtosis/autocorrelation.

**Single Feature Importance (SFI)** — (Ch.8) OOS performance of each feature in isolation; no substitution effects, loses joint effects.

**Strategy Risk** — (Ch.15) integral of the precision PDF f[p] below the implied precision p*; ≠ portfolio risk.

**Sub-/Super-Martingale Tests (SMT)** — (Ch.17) fit polynomial/exponential/power trends on backwards-expanding windows; sup |t_β|; penalize length via φ∈[0,1].

**Tick rule** — (Ch.2,19) sign every tick from price changes b_t∈{−1,1}; builds imbalance/run statistics.

**Triple-Barrier Method** — (Ch.3) profit-taking + stop-loss horizontal barriers + vertical expiration barrier; label +1/-1/sign of return.

**Triple-Barrier configurations** — (Ch.3) only [1,1,1], [0,1,1], [1,1,0] are useful among the eight [pt,sl,t1] configurations.

**VPIN (Volume-Synchronized Probability of Informed Trading)** — (Ch.22) Easley-López de Prado-O'Hara early-warning toxicity metric; 720x HPC speedup; global params reduce false positives from 20% to 7%.

**Walk-Forward (WF)** — (Ch.12) train [0,t], test [t,t+1], advance; one path, overfit-prone.

**Z'Z spectral decomposition** — (Ch.8,20) covariance eigendecomposition basis for PCA and for the sparse-column multiprocessing example.