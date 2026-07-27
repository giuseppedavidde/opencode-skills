# Option Volatility & Pricing — Quick Reference

## The Five Black-Scholes Inputs
| Input | Notation | Observable? | Sensitivity |
|-------|----------|-------------|-------------|
| Underlying Price | S | Yes (bid-ask midpoint) | Delta (Δ) |
| Exercise Price | X | Yes (fixed) | — |
| Time to Expiration | t | Yes (days/365) | Theta (Θ) |
| Interest Rate | r | Yes (LIBOR/risk-free) | Rho (ρ) |
| Volatility | σ | **No — must forecast** | Vega (ν) |

## Greeks at a Glance
| Greek | Measures | Long Call | Long Put | ATM Approx |
|-------|----------|-----------|----------|------------|
| Delta (Δ) | Directional exposure | 0 to +1 | −1 to 0 | ±50 |
| Gamma (Γ) | Delta change / $1 move | + | + | Maximum |
| Theta (Θ) | Daily time decay | − | − | Maximum |
| Vega (ν) | 1% IV change impact | + | + | Maximum |
| Rho (ρ) | 1% rate change impact | + | − | Moderate |

## Volatility Scaling (√t Rule)
| Period | Divisor | 20% Annual Vol |
|--------|---------|----------------|
| Daily | ÷16 (√256) | 1.25% (±$1.25 on $100) |
| Weekly | ÷7.2 (√52) | 2.78% (±$2.78 on $100) |
| Monthly | ÷3.5 (√12) | 5.77% (±$5.77 on $100) |

**Probabilities**: ±1σ ≈ 68% (2/3), ±2σ ≈ 95% (19/20), ±3σ ≈ 99.7%

## Put-Call Parity
| Settlement | Formula |
|------------|---------|
| Futures-type | `C − P = F − X` |
| Stock-type (futures) | `C − P = (F − X)/(1 + r×t)` |
| Stock options | `C − P = S − X/(1 + r×t) − D` |

## ATM Option Value Approximation ("40% Rule")
```
Expected Value ≈ 0.004 × F × σ × √t
Theoretical Value ≈ Expected Value / (1 + r×t)
```
Example: F=100, σ=20%, t=0.25 (3mo): EV ≈ 0.004 × 100 × 20 × 0.5 = 4.00

## Early Exercise Decision Matrix
| Option Type | Exercise When | Optimal Timing |
|-------------|---------------|----------------|
| Stock Call | Dividend > Vol value + Interest | Day before ex-dividend ONLY |
| Stock Put | Interest > Vol value + Dividend | After blackout period |
| Futures Call (stock settled) | Interest on intrinsic > Vol value | When daily theta < daily interest |
| Futures (futures settled) | **Never** | No early exercise value |

### Stock Put Blackout Period
```
Days = Dividend / (Exercise Price × Daily Interest Rate)
Don't exercise within this window before ex-dividend
```

## Vertical Spread Selection Rule
| IV Regime | Action | Rationale |
|-----------|--------|-----------|
| **IV Low** | BUY the ATM option | ATM option cheapest in total points |
| **IV High** | SELL the ATM option | ATM option most expensive in total points |

Then complete the spread with the companion option to create desired direction.

## Volatility Spread Characteristics
| Strategy | Gamma | Theta | Vega | Direction |
|----------|-------|-------|------|-----------|
| Long Straddle | + | − | + | Neutral |
| Short Straddle | − | + | − | Neutral |
| Long Butterfly | − | + | − | Neutral |
| Short Butterfly | + | − | + | Neutral |
| Ratio Spread (sell more) | − | + | − | Variable |
| Calendar Spread (long) | Varies | Varies | + | Neutral |

## Volatility Surface Dimensions
| Dimension | What It Captures | Traded Via |
|-----------|-----------------|------------|
| **Level** (ATM IV) | Overall option expensiveness | Straddles/Strangles |
| **Slope** (Skewness) | Puts vs. Calls pricing | Risk Reversals |
| **Curvature** (Kurtosis) | Tail fatness | Butterfly/Condor spreads |
| **Term Structure** | Near vs. Far month IV | Calendar spreads |

## Key Formulas
```
Forward Price (no div):     F = S × (1 + r×t)
Forward Price (with div):   F = S × (1 + r×t) − D
Forward Price (continuous): F = S × e^(r−d)×t
Delta-Neutral Hedge:        Underlying = −(Option Qty × Δ / 100)
Synthetic Long Underlying:  +Call −Put at same strike
Synthetic Long Call:        +Underlying +Put
Synthetic Long Put:         −Underlying +Call
```

## Risk Management Rules of Thumb
1. **Never let gamma risk exceed your ability to adjust**: Large negative gamma positions require constant monitoring
2. **Vega dominates theta at longer expirations**: A 1% vol move on a 1-year option > 1 month of theta
3. **The ATM option is always the fulcrum**: All skew, term structure, and strategy decisions pivot on ATM
4. **Delta-neutral ≠ risk-neutral**: A delta-neutral straddle in stocks has negative true delta (down moves increase vol)
5. **Volatility mean reverts; price doesn't**: Extreme IV is temporary; extreme price can persist
