# Options Playbook Cheatsheet

## Strategy → Outlook Quick Table

| Strategy | Bullish | Bearish | Neutral | Volatile | Risk |
|---|---|---|---|---|---|
| Long Call | ✓ | | | | Limited |
| Long Put | | ✓ | | | Limited |
| Short Call | | ✓ | ✓ | | Unlimited |
| Short Put | ✓ | | ✓ | | Substantial |
| Cash-Secured Put | ✓ | | | | Substantial |
| Covered Call | ✓ | | ✓ | | Stock loss |
| Protective Put | ✓ | | | | Stock + debit |
| Collar | ✓ | | | | Limited range |
| Fig Leaf | ✓ | | | | Limited debit |
| Bull Call Spread | ✓ | | | | Limited debit |
| Bear Put Spread | | ✓ | | | Limited debit |
| Bear Call Spread | | ✓ | ✓ | | Limited (width-credit) |
| Bull Put Spread | ✓ | | ✓ | | Limited (width-credit) |
| Long Straddle | | | | ✓ | Limited |
| Short Straddle | | | ✓ | | Unlimited |
| Long Strangle | | | | ✓ | Limited |
| Short Strangle | | | ✓ | | Unlimited |
| Long Combination | ✓ | | | | Substantial |
| Short Combination | | ✓ | | | Unlimited |
| Front Spread w/ Calls | ✓ | | | | Unlimited upside |
| Front Spread w/ Puts | | ✓ | | | Substantial↓ |
| Back Spread w/ Calls | | | | ✓ | Limited |
| Back Spread w/ Puts | | | | ✓ | Limited |
| Calendar Spread | ✓ | ✓ | ✓ | | Limited debit |
| Diagonal Spread | ✓ | ✓ | | | Limited debit |
| Long Butterfly | | | ✓ | ✓ | Limited debit |
| Iron Butterfly | | | ✓ | | Limited (width-credit) |
| Skip Strike Butterfly | | | ✓ | | Limited debit |
| Christmas Tree | ✓ | ✓ | | | Limited debit |
| Long Condor | | | ✓ | | Limited debit |
| Iron Condor | | | ✓ | | Limited (width-credit) |
| Double Diagonal | | | ✓ | | Limited |

## Greeks Quick Ref

| Greek | What It Measures | Long Option | Short Option | Key Fact |
|---|---|---|---|---|
| Δ Delta | $ change per $1 stock move | +0 to +1 (call)<br>-1 to 0 (put) | Opposite sign | ATM = ~0.50. Also prob of ITM. |
| Γ Gamma | Δ change per $1 stock move | Positive | Negative | Highest for ATM near-term. |
| Θ Theta | Daily time decay | Negative | Positive | Accelerates last 30 days. |
| ν Vega | $ change per 1pt IV change | Positive | Negative | Higher for longer-term. |
| ρ Rho | $ change per 1% rate change | Slightly positive | Slightly negative | LEAPS only. |

## Exit Rules — When to Close

| Strategy | Take Profit | Stop Loss |
|---|---|---|
| Long Call/Put | 25-50% gain or target hit | 25-50% loss or IV crush |
| Short Call/Put | 50-75% of premium decayed | 2-3x premium collected |
| Credit Spread | 50% max profit | Width = stop (don't wait) |
| Debit Spread | 75-100% of spread width | 100% loss (debit paid) |
| Long Straddle | 50%+ after vol expansion | 50% loss or IV crush |
| Iron Condor | 50% of credit received | 1x-2x credit collected |
| Butterfly | 50-80% of max profit | 100% loss (debit paid) |
| Covered Call | Call expires or stock called away | Stock stop-loss |
| Protective Put | Let expire if stock rises | Exercise/close if stock hits strike |
| Calendar/Diagonal | Front month decays to near zero | Stock moves away from strike |

## Time Frame Guidelines
- **Premium Sellers** (Covered Call, Credit Spreads, Iron Condor): 30-45 DTE — balance of theta decay and gamma risk.
- **Premium Buyers** (Long Call, Long Put, Long Straddle): 60-90 DTE — gives stock time to move. Don't buy short-term OTM.
- **LEAPS Strategies**: 12+ months. For stock replacement and long-term directional views.

## Position Sizing (1 contract = 100 shares)
- If you normally trade 100 shares = trade 1 contract.
- If you normally trade 200 shares = trade 2 contracts.
- Do not let leverage fool you — buying 10 cheap OTM calls is MORE risk than buying 100 shares.
