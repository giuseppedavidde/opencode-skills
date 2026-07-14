# Chapter 2: Preferences

## Core Idea
Asset management begins with "know thyself": quantitatively characterizing how an investor feels during bad times. Utility functions are the tool to measure this, and optimal allocation trades off the risk of bad times against expected returns. Mean-variance is the industry workhorse but is dangerously restrictive — it is blind to skewness, kurtosis, reference points, habit, and peer effects that define real-world "bad times."

## Frameworks Introduced
- **Expected Utility (von Neumann–Morgenstern / Savage)** — `U = E[U(W)]` = Σ ps U(Ws); combines probabilities of outcomes with utility over outcomes. Nests behavioral models. Objective or subjective probabilities.
- **CRRA (Constant Relative Risk Aversion)** — `U(W) = W^(1-γ)/(1-γ)`; γ ∈ [1,10] typical. Risk aversion constant across wealth levels. Empirical estimates cluster around γ ≈ 2–4 (Paravisini et al.), up to 8 (Kimball et al.).
- **Mean-Variance Utility (Markowitz)** — `U = E(rp) − (γ/2)·var(rp)`. Bad times = low mean, high variance. Ignores skew/kurtosis. Approximates CRRA under log-normality (Levy–Markowitz 1979).
- **Indifference Curves** — Locus of equal-utility mean/σ combinations. Steeper slope ⇒ higher risk aversion. Tangency with frontier/CAL yields optimal portfolio.
- **Certainty Equivalent** — Risk-free return making investor indifferent to a risky position = utility level itself (cardinal, not ordinal). Useful for costing non-diversification, illiquidity, lock-ups.
- **Revealed Preference** — Back out γ from observed holdings. 60/40 pension fund ⇒ γ ≈ 2.8. Aggregate US market (stocks vs T-bills) ⇒ γ ≈ 3.0.
- **Safety First (Roy 1952)** — Binary utility: disaster if return < threshold. Minimize disaster probability. Hold safe assets to threshold, then maximize risk.
- **Quantile Utility (Manski 1988, Rostek 2010)** — Maximize worst outcome at a chosen quantile (VaR-like). Quantile choice = downside-risk-aversion parameter.
- **Prospect Theory / Loss Aversion (Kahneman–Tversky 1979)** — Utility kinked at reference point: concave over gains (risk-averse), convex over losses (risk-seeking), steeper for losses. λ ≈ 2.25 (losses weighted ~2× gains). Plus probability weighting `w(p)` (decision weights, need not sum to 1).
- **Disappointment Aversion (Gul 1991)** — Rational cousin of loss aversion. Endogenous reference point = certainty equivalent. Downside ("disappointing") outcomes weighted 1/A more than "elating" ones; A<1 ⇒ downside-averse. Always admits solution; extends to dynamic settings.
- **Habit Utility (Sundaresan, Constantinides, Campbell–Cochrane)** — Bad times = wealth approaching habit (subsistence lifestyle) level. Risk aversion is endogenous, state-dependent: high near habit, low when wealth >> habit. Habit can be external (macro) or internal (own past consumption).
- **Catching Up with the Joneses (Abel 1990, Galí 1994)** — Utility defined relative to peers' wealth/consumption. "Relative utility." Produces endogenous herding (DeMarzo–Kaniel–Kremer). Relevant for benchmarked managers / endowments.
- **Uncertainty / Ambiguity Aversion (Knight 1921, Gilboa–Schmeidler 1989)** — Multiple probability distributions (not a single pdf). Max-min utility: take worst-case distribution then maximize. Equivalent to inflated risk aversion; can drive equity allocation to zero. ~1/3 of US households are ambiguity-seeking (Dimmock et al.).

## Key Concepts
- **Bad times** — Not only low wealth; can be low consumption vs habit, underperformance vs peers, or violation of ethical norms. Marginal utility highest in bad times.
- **Leptokurtic distributions** — Thin body, fat tails vs normal. Volatility strategy: skewness −8, kurtosis >100. Mean-variance misses this entirely.
- **Risk aversion (γ)** — Curvature of utility. γ≈1 risk-neutral-ish (Jeopardy players), γ≈3 typical market, γ≈8 high (survey estimates).
- **Capital Allocation Line (CAL)** — E(rp) = rf + [(E(r)−rf)/σ]·σp. Slope = Sharpe ratio. Empirical US equity Sharpe ≈ 0.40–0.53.
- **Sharpe ratio** — (E(r)−rf)/σ. Zero-cost long-risky / short-risk-free reward-to-risk ratio.
- **Normative vs positive economics** — Normative = what you should do (prescriptive); positive = what people actually do. Ang focuses normative but stresses best frameworks account for behavioral failures.
- **Optimal risky-asset weight** — `w* = (1/γ)·(E(r)−rf)/σ²`. More risk-averse ⇒ less equity; more attractive asset ⇒ more.
- **Probability weighting** — Decision weights `w(p)` over-weight small-probability extreme events (disasters, jackpots). Need not satisfy probability axioms.
- **Endogenous risk aversion** — In habit utility γ varies with state; near habit ⇒ very high γ. Contrasts with constant γ in CRRA.
- **Non-monetary considerations** — Ethics/social preference enter utility (Norway SWF exclusions: tobacco, cluster munitions, human rights violators). Bad times include moral indignation.

## Anti-patterns
- **Using mean-variance to evaluate skewed strategies** — Vol strategy and S&P 500 have same mean (~10%) and stdev (~15%) but vastly different tail risk. M-V equivalence is misleading; certainty equivalents falsely equal.
- **Conflating mean-variance with normality assumption** — M-V does NOT require normal returns (Levy–Markowitz), but approximation degrades badly with high skew/kurtosis. Many practitioners wrongly equate the two.
- **Picking up nickels in front of a steamroller** — Short-vol earns steady premiums for years, then loses 70%+ in a single crisis (2008). Losses cluster at worst possible time. Loss-averse / habit / disappointment-averse investors should avoid entirely.
- **Treating wealth or happiness as the objective** — Path matters, not just terminal wealth. Utility ≠ happiness; it jointly captures risk AND return. Pure wealth-max or bliss-max framing is wrong.
- **Assuming everyone is ambiguity-averse** — >1/3 of US households are ambiguity-seeking; heterogeneity matters. But more risk-averse ⇒ generally more ambiguity-averse.

## Key Takeaways
1. **Define your bad times first.** Factor investing is about comparing your bad times to the average investor's; you cannot harvest premiums without knowing what you cannot tolerate.
2. **Mean-variance is a starting point, not an endpoint.** Always stress-test allocations with richer utilities (loss aversion, disappointment aversion, habit) especially for skewed/fat-tailed strategies.
3. **Calibrate γ from observed behavior (revealed preference).** A 60/40 portfolio implies γ≈2.8; the aggregate market implies γ≈3. Use these as reality checks on optimizer outputs.
4. **Downside risk aversion drastically reduces allocations to short-vol / negative-skew strategies.** At λ≈2.2 (loss aversion) or A≈0.45 (disappointment aversion), investors optimally abandon the volatility strategy entirely for T-bills.
5. **Reference points, habits, and peers are real bad-time triggers.** Endogenous risk aversion (habit) and herding (Joneses) explain observed behavior that mean-variance cannot — incorporate them when designing factor tilts for liability-driven or benchmarked mandates.
6. **Build normative advice that survives behavioral failure.** Frame rebalancing, diversification, and dis-saving rules to mitigate the known tendency of investors to abandon optimal policy at the worst moment.