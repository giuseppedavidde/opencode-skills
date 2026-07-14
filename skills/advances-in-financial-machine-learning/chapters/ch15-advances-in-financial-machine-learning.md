# Chapter 15: Understanding Strategy Risk

## Core Idea
Because most strategies exit at a profit-taking or stop-loss condition (explicit or implicit via margin call/stop-out), outcomes can be modeled as a binomial process. Closed-form Sharpe-ratio equations let you invert for the precision p, the frequency n, or the payouts {pi_-, pi_+} required to hit a target Sharpe. Crucially, **strategy risk is not portfolio risk**: the CRO's portfolio vol tells you nothing about the risk that the strategy will fail to deliver, which is a question for the CIO and is dominated by shocks to the *unknown* precision p.

## Frameworks Introduced
- **Symmetric Payouts**: profit pi with prob p, loss -pi with prob 1-p. Annualized Sharpe theta[p,n] = ((2p-1) sqrt n) / (2 sqrt(p(1-p))). pi cancels — Sharpe is a function of *precision* (not accuracy; passing on opportunities has no payout). Even tiny p>0.5 yields high Sharpe for large n (basis of HFT). E.g. p=0.55 -> SR=2 needs 396 bets/year; weekly bets need p≈0.6336 for SR=2.
- **Asymmetric Payouts**: pi_+ with prob p, pi_- (pi_-<pi_+) with prob 1-p. theta = sqrt(n) * ((pi_+ - pi_-) p + pi_-) / (|pi_+ - pi_-| sqrt(p(1-p))). Example: n=260, pi_-=-0.01, pi_+=0.005, p=0.7 -> theta=1.173; raising p to 0.72 jumps theta to 2 — the strategy is highly precision-sensitive. Closed-form quadratic a p^2 + b p + c = 0 solves for the implied precision given {n, pi_-, pi_+} and target theta*.
- **Implied Betting Frequency**: invert the same equation for n given {p, pi_-, pi_+}.
- **Probability of Strategy Failure**: pi_-, pi_+, n are under the PM's control; p (set by the market) and theta* (set by the investor) are not. Define p* as the precision below which the strategy underperforms theta*. The strategy-risk algorithm: (1) estimate pi_- = E[pi_t|pi_t<=0], pi_+ = E[pi_t|pi_t>0] (or fit a mixture of two Gaussians via EF3M); (2) annual n; (3) bootstrap p over k-year windows; (4) KDE the PDF f[p]; (5) strategy risk = integral over p<=p* of f[p] dp. Reject strategies with strategy risk above a threshold (e.g. cut-off defined by theta*).

## Key Concepts
- **Strategy risk != portfolio risk**: a low-volatility portfolio can still have a high probability of failing to deliver the target Sharpe.
- Small changes in p cause large swings in Sharpe when payouts are asymmetric — the strategy is intrinsically risky even if its holdings are not.
- EF3M (López de Prado & Foreman 2014): fits a mixture of two Gaussians to the bet-outcome distribution to recover {pi_-, pi_+}.
- Complementary to PSR (Probabilistic Sharpe Ratio, Bailey & López de Prado): PSR does not separate parameters under/outside the PM's control; this method does, so the PM can study viability subject to {pi_-, pi_+, n}.

## Anti-patterns
- Equating portfolio volatility (the CRO metric) with the risk of the strategy — they measure different things.
- Reporting only the *expected* p without its distribution; a 3-point drop in p can wipe out all profits.
- Setting symmetric barriers when the underlying payout distribution is asymmetric — guaranteed to under-realize the achievable Sharpe or to hide precision fragility.
- Ignoring the sensitivity of theta to each parameter when choosing which lever to pull (frequency vs. precision vs. payout).

## Key Takeaways
- For a strategy, Sharpe is a function of precision (p), frequency (n), and the asymmetric payout pair {pi_-, pi_+}.
- Strategy risk = P[p <= p*], estimated by bootstrapping realized precisions over k-year windows and KDE on f[p].
- A viable strategy needs small strategy risk — independent of how low its portfolio volatility is.
- The framework tells the PM where the lowest-hanging fruit lies (which parameter, if improved, raises theta fastest).