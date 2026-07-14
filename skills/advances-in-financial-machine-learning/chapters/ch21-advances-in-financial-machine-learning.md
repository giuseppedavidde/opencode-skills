# Chapter 21: Brute Force and Quantum Computers

## Core Idea
Many financial ML problems reduce to discrete/combinatorial optimization (hierarchical clustering, grid search, threshold decisions, integer optimization) that classical computers solve sequentially and so become intractable as the feasible set grows. Unlike Garleanu-Pedersen (which assume IID Gaussian returns), López de Prado reformulates a **dynamic portfolio optimization with generic, non-continuous transaction costs** as an integer optimization problem. The result is a *global* optimum that convex solvers cannot reach — at the price of being NP-hard. Quantum computers, whose qubits hold a linear superposition of 0 and 1, can evaluate all feasible solutions at once and are ideally suited to such brute-force search. The chapter is a recipe: discretize an intractable ML problem, then hand it to a quantum annealer.

## Frameworks Introduced
- **Combinatorial optimization**: a finite number of feasible solutions combined from discrete variable values. As combinations grow, exhaustive search on a classical machine becomes impractical (traveling-salesman is NP-hard — Woeginger 2003).
- **Qubits & linear superposition**: classical bits take one of {0,1}; qubits hold a superposition of both, so a quantum machine can store/evaluate multiple feasible solutions simultaneously — the property that makes it suited to NP-hard brute force (Williams 2010).
- **Objective function**: returns r from a trading trajectory ω (NxH matrix) given forecasted mean μ_h, variance V_h and a generic transaction-cost function τ_h[ω] = Σ √|Δω| · C_h. The Sharpe ratio SR[r] is the objective to maximize.
- **Why it is NOT convex/quadratic**: (1) returns are time-independent but **not** identically distributed (μ_h, V_h change with h); (2) transaction costs τ_h[ω] are non-continuous and change with h; (3) SR[r] is not convex. Standard convex optimization fails.
- **Integer optimization approach**: discretize the problem so it becomes amenable to integer optimization, and hence to quantum computation.
- **Pigeonhole partitions**: number of ways to allocate K units of capital among N assets = number of non-negative integer solutions to x_1+…+x_N = K, with combinatorial closed form. Order matters — partitions (1,2,3) and (3,2,1) are distinct; use Stirling's approximation for an estimate at large K, N (Hardy-Ramanujan-Rademacher; Johansson 2012).
- **Feasible static solutions (Ω)**: for each partition generate a vector of absolute weights Σ|ω_i|=1 (full investment), then 2^N signed weights via the Cartesian product of {−1,1}^N (no-leverage constraint allows signs).
- **Evaluating trajectories (Φ)**: the set of all trajectories is the Cartesian product of Ω with H repetitions. Evaluate transaction costs and SR for every trajectory; pick the global optimum — **no reliance on any analytic property of the objective** (works even with ill-conditioned covariance, non-continuous costs).
- **Numerical example**: `Snippet 21.4` produces a random matrix of a *given rank* (useful for Monte Carlo / scenario analysis); `Snippet 21.5` generates H vectors of {C, μ, V}; `Snippet 21.6` computes the **static** (local) optimum; `Snippet 21.7` computes the **globally dynamic** optimum. A quantum annealer evaluates all trajectories at once; a digital machine does it sequentially.

## Key Concepts
- **Global vs local optimum**: the dynamic solution dominates the sequence of static Markowitz optima (Ch.16) whenever transaction costs are non-continuous — explaining why naïve solutions often beat Markowitz out-of-sample.
- **Cost of generality**: evaluating all trajectories is travelling-salesman-like — extremely computationally intensive. Digital machines are inadequate for NP-complete/NP-hard; quantum machines are not.
- **Foundation for Rosenberg et al. (2016)**: this discretization set the stage for solving the optimal trading trajectory on a quantum annealer (IEEE J. Select. Topics Signal Processing).
- **Generalization recipe**: any intractable ML problem with path dependency can be discretized → translated into a brute force search → handed to a quantum computer.
- The rank-controlled random matrix (`Snippet 21.4`) connects directly to Markowitz's Curse (Ch.16): low-rank covariance matrices produce unstable inversions.

## Anti-patterns
- Assuming IID Gaussian returns to force the problem into convex quadratics — you lose generality and the global optimum.
- Treating partitions as order-invariant — (1,2,3) and (3,2,1) must be distinct solutions.
- Searching only static (local) optima when transaction costs are non-continuous — the global dynamic trajectory can be very different.
- Applying integer optimization without bounding K and N — combinatorial explosion is exponential; check feasibility via Stirling before brute force.
- Using a classical machine for genuinely NP-hard search and declaring "no solution" — the right conclusion is "use a quantum computer."

## Key Takeaways
- Discretize the intractable, then brute-force it: integer optimization makes dynamic portfolio choice solvable without convexity assumptions.
- Quantum computers' superposition property is purpose-built for NP-hard combinatorial search.
- The global dynamic optimum can diverge sharply from the sequence of local Markowitz optima — explaining naïve-beats-Markowitz results.
- `Snippet 21.4` (rank-controlled random matrices) is a reusable Monte Carlo tool tied to Markowitz's Curse.
- The discretization recipe generalizes: path-dependent ML problems → integer optimization → quantum annealer (Rosenberg et al. 2016).