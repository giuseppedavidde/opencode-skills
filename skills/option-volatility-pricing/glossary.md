# Glossary: Option Volatility and Pricing (2nd Edition) — Sheldon Natenberg

> Comprehensive alphabetical glossary of key terms from the entire book, covering all chapters.

---

## A
**Arbitrage**: Simultaneously buying and selling the same or closely related contracts in different markets to profit from a mispricing. In options, the most common form is a conversion or reversal exploiting put-call parity violations.

**Assignment**: The obligation imposed on an option seller when a buyer exercises. The assigned seller must take (call) or make (put) delivery of the underlying at the exercise price.

**At-the-Forward (ATF)**: An option whose exercise price equals the forward price of the underlying. Often the most actively traded benchmark in many markets.

**At-the-Money (ATM)**: An option whose exercise price equals (or is very close to) the current price of the underlying contract.

---

## B
**Backwardation**: A futures market condition where nearby contracts trade at a premium to deferred contracts. Affects forward pricing and options on futures.

**Binomial Model (Cox-Ross-Rubinstein)**: A discrete-time option pricing model that builds a tree of possible underlying prices. Values options by backward induction and naturally handles American-style early exercise.

**Black-Scholes Model**: The foundational continuous-time option pricing model (1973) requiring five inputs: exercise price, time to expiration, underlying price, interest rate, and volatility. Assumes European exercise and lognormal price distribution.

**Butterfly Spread**: A three-legged spread (1×2×1 ratio) using calls or puts at equally spaced strikes. Long butterfly: bounded risk/reward, profits from price remaining near the middle strike.

**Buy/Write**: Simultaneously buying stock and selling a call against it. A covered call strategy executed as a single package trade.

---

## C
**Calendar Spread (Time Spread)**: Options at the same strike but different expirations. Long calendar: sell near-month, buy far-month, profiting from faster time decay of the front month.

**Call Option**: The right, but not the obligation, to buy an underlying asset at a fixed exercise price on or before expiration.

**Cap**: An interest-rate call option purchased by a borrower to limit maximum borrowing cost. Also used as a risk limit on variance swaps.

**Charm (Delta Decay)**: Sensitivity of delta to the passage of time (∂Δ/∂t). Greatest for options with deltas around ±20 or ±80.

**Collar**: A hedged position combining a long protective put and a short covered call, typically structured to be zero-cost, bounding both upside and downside.

**Combo (Combination)**: A long call and short put (synthetic long) or short call and long put (synthetic short), both at the same strike and expiration.

**Condor**: A four-legged spread similar to a butterfly but with non-overlapping middle strikes, creating a wider profit zone.

**Contango**: A futures market condition where deferred contracts trade at a premium to nearby contracts. Normal for many commodity markets.

**Conversion**: An arbitrage position: short call + long put + long underlying. Profits when the synthetic short is overpriced relative to the underlying.

**Covered Call**: A long underlying position combined with a short call. Generates premium income but caps upside. Synthetically equivalent to a short put.

**Covered Put**: A short underlying position combined with a short put. Equivalent to a short call.

**Covered Write (Overwrite)**: Selling an option against an existing underlying position to generate income and provide partial protection.

---

## D
**Delta (Δ)**: The rate of change in option value relative to a change in the underlying price. Ranges: 0 to 100 for calls (whole-number format), -100 to 0 for puts. Also interpreted as hedge ratio, equivalent underlying position, and approximate probability of finishing ITM.

**Delta Neutral**: A position where total portfolio delta equals zero, eliminating directional bias. The starting point for volatility-based strategies.

**Derivative**: A financial contract whose value derives from an underlying asset (stock, futures, commodity, index, currency).

**Dynamic Hedging**: Continuously adjusting a hedge position as market conditions change to maintain delta neutrality and capture theoretical edge.

---

## E
**Early Exercise**: Exercising an American-style option before expiration. Optimal when the option's protective value exceeds its remaining time value.

**Edge (Theoretical Edge)**: The expected profit from a strategy, assuming the trader's assessment of market conditions (especially volatility) is correct.

**European Option**: An option that can only be exercised at expiration (not before). Black-Scholes originally priced European options.

**Exercise**: The act of converting an option into the underlying position. A call buyer buys the underlying at the strike; a put buyer sells the underlying at the strike.

**Exercise Price (Strike Price)**: The fixed price at which the underlying is bought or sold upon option exercise.

**Expected Value**: The probability-weighted average of all possible outcomes. The foundation of theoretical option pricing.

**Expiration Date (Expiry)**: The date after which all rights and obligations under an option contract cease. For US stock options, typically the third Friday of the expiration month.

---

## F
**Floor**: An interest-rate put option purchased by a lender to guarantee minimum lending returns.

**Forward Contract**: An agreement to buy or sell an asset at a future date at a price agreed upon today. Traded OTC; terms are customizable.

**Forward Price**: The expected future price of an asset, derived from the current spot price adjusted for cost of carry (interest, storage, dividends).

**Futures Contract**: A standardized forward contract traded on an organized exchange with margin requirements and daily settlement.

**Futures-Type Settlement**: Settlement procedure where no money changes hands when options or futures are traded. Common outside North America. Eliminates interest rate effects on option pricing.

---

## G
**Gamma (Γ)**: The rate of change in delta relative to a change in the underlying price. Always positive for long options, negative for short options. Measures curvature/convexity.

**Gamma Rent**: The profit or loss realized from delta rebalancing as the underlying price moves. A long gamma position earns gamma rent from price oscillations.

**Greeks**: The sensitivity measures of an option's value: delta, gamma, theta, vega, and rho. Used for risk management and position analysis.

**Guts**: A strangle constructed with in-the-money options rather than the conventional out-of-the-money options.

---

## H
**Hedge Ratio**: The number of underlying contracts needed to offset the directional risk of an option position. Calculated as 100/|delta| for each contract.

**Historical Volatility**: Volatility calculated from past price data. A backward-looking estimate of the underlying's variability.

---

## I
**Implied Delta**: Delta calculated using implied volatility rather than a volatility estimate. Changes as the market's volatility assessment changes.

**Implied Volatility (IV)**: The volatility implied by an option's market price when plugged into a pricing model. Represents the market's consensus forecast of future volatility.

**In-the-Money (ITM)**: An option with intrinsic value. A call is ITM when the underlying price exceeds the exercise price; a put is ITM when the exercise price exceeds the underlying price.

**Intrinsic Value**: The amount by which an option is in-the-money. At expiration, an option is worth exactly its intrinsic value. Calculated as max(S-X, 0) for calls, max(X-S, 0) for puts.

**Iron Butterfly/Iron Condor**: Strategies combining both calls and puts (rather than all-calls or all-puts) to create the same risk profile as a butterfly or condor, often with reduced margin requirements.

---

## L
**Lambda (Λ)**: Sometimes used to denote the expected percentage change in option value per 1% change in the underlying. Also called leverage or elasticity.

**Lognormal Distribution**: The probability distribution assumed by Black-Scholes for underlying prices at expiration. Implies that percent (logarithmic) returns are normally distributed.

**Long Position**: A position that profits from a price increase. In options, buying a call or selling a put creates a long market position.

---

## M
**Margin**: Funds deposited with a clearinghouse to guarantee performance on futures and short option positions. Margin requirements can force position liquidation.

**Midcurve Option**: A short-term option on a long-term futures contract. For example, a one-year option on a five-year futures contract.

**Moneyness**: The relationship between the underlying price and the exercise price: ITM, ATM, or OTM.

---

## O
**Open Interest**: The total number of outstanding contracts that have not been closed out. Long and short open interest are always equal.

**Option**: A contract giving the buyer the right, but not the obligation, to buy (call) or sell (put) an underlying asset at a fixed price on or before a specified date.

**Out-of-the-Money (OTM)**: An option with no intrinsic value. A call is OTM when the underlying price is below the exercise price; a put is OTM when the exercise price is below the underlying price.

---

## P
**Parity Graph**: A diagram showing the value of an option or strategy at expiration as a function of the underlying price.

**Premium**: The price paid by the option buyer and received by the seller. The seller keeps the premium regardless of whether the option is exercised.

**Protective Put**: A long underlying position combined with a long put, acting as insurance against a price decline. Synthetically equivalent to a long call.

**Put Option**: The right, but not the obligation, to sell an underlying asset at a fixed exercise price on or before expiration.

**Put-Call Parity**: The fundamental arbitrage relationship: C - P = PV(F - X). For European options with the same strike and expiration, the call-put price difference must equal the present value of the forward price minus the exercise price.

---

## R
**Ratio Spread**: A spread where the number of long and short option contracts is unequal (e.g., buy 1, sell 2). Used to tailor risk/reward profiles.

**Realized Volatility**: The actual volatility observed in an underlying contract over a historical period. Calculated as the standard deviation of logarithmic returns.

**Reverse Conversion (Reversal)**: An arbitrage position: long call + short put + short underlying. Profits when the synthetic long is underpriced relative to the underlying.

**Rho (ρ)**: Sensitivity of option value to changes in interest rates. Generally the least important Greek for short-term options.

**Risk-Neutral Valuation**: A pricing approach where the expected return of all assets equals the risk-free rate, eliminating the need to estimate actual expected returns.

**Riskless Hedge**: A position where the option and its underlying hedge offset each other for small price changes, creating a portfolio with zero directional exposure.

---

## S
**Serial Option**: An option expiring in a month without a corresponding futures contract month. The underlying is the nearest deferred futures contract.

**Settlement Price**: The official price established by an exchange at the end of trading, used for marking positions to market.

**Short Position**: A position that profits from a price decline. Selling a call or buying a put creates a short market position.

**Skew (Volatility Skew)**: The pattern where OTM puts trade at higher implied volatilities than OTM calls. Violates the Black-Scholes assumption of constant volatility across strikes.

**Spot Transaction (Cash Transaction)**: An immediate exchange of money for goods at the current market price.

**Stock-Type Settlement**: Settlement procedure where the full option price is paid at the time of trade. Used for stock options and US futures options. Interest rates affect present value.

**Straddle**: A call and put at the same strike and expiration, either both bought (long straddle) or both sold (short straddle). Pure volatility play.

**Strangle**: A call and put at different strikes (typically OTM) with the same expiration. Similar to a straddle but with a wider break-even range.

**Strike Price**: See Exercise Price.

**Swap**: An agreement to exchange cash flows, typically fixed-rate for floating-rate payments.

**Synthetic**: A combination of options and/or the underlying that replicates the payoff of another instrument. Examples: synthetic long underlying = long call + short put; synthetic call = long put + long underlying.

---

## T
**Theoretical Value**: The fair value of an option calculated by a pricing model. The price at which expected profit is zero in the long run.

**Theta (Θ)**: The rate of time decay—how much value an option loses per day as expiration approaches. Long options have negative theta.

**Time Premium (Time Value)**: The portion of an option's price exceeding its intrinsic value, reflecting the remaining time and volatility.

**Time Spread**: See Calendar Spread.

---

## V
**Vanna**: Sensitivity of delta to changes in volatility (∂Δ/∂σ). Greatest for options with deltas around ±20 and ±80.

**Variance Swap**: A contract that pays the difference between realized variance (σ²) and a fixed strike variance, multiplied by a notional amount. Primary instrument for trading realized volatility.

**Vega**: Sensitivity of option value to a 1% change in implied volatility. Always positive for long options. Also called kappa or omega.

**VIX (Volatility Index)**: The CBOE's index of 30-day expected volatility for the S&P 500, calculated from a broad range of SPX option prices using a model-free methodology.

**Volatility**: A measure of the variability of returns on an underlying contract. The key unobservable input in option pricing models. Expressed as an annualized standard deviation of logarithmic returns.

**Volatility Contract**: An instrument (variance swap, VIX future, VIX option) that provides direct exposure to volatility without requiring dynamic hedging.

**Volatility Spread**: A multi-leg option position designed to isolate volatility as the primary profit/loss driver, typically constructed to be delta-neutral.

---

## Y
**Yield Curve**: The relationship between interest rates and time to maturity. Affects forward pricing and long-dated option valuation.
