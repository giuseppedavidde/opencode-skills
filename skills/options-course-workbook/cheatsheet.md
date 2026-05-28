# Cheat Sheet: Formulas, Greeks, and Strategy Decision Tree

## Option Pricing Formulas

| Measure | Formula |
|---------|---------|
| **Long Call Breakeven** | Strike price + premium paid |
| **Long Put Breakeven** | Strike price − premium paid |
| **Call Intrinsic Value** | max(0, underlying − strike) |
| **Put Intrinsic Value** | max(0, strike − underlying) |
| **Extrinsic Value** | Option price − intrinsic value |
| **Option Multiplier** | 1 point = $100 per contract (stock options) |
| **Delta (approximate)** | Change in premium ÷ change in underlying × 100 |
| **Leverage** | (Shares controlled × underlying price) ÷ premium paid |

## Vertical Spread Formulas

| Spread | Type | Max Risk | Max Reward | Breakeven |
|--------|------|----------|------------|-----------|
| **Bull Call** | Debit | Net debit | Width − debit | Lower strike + debit |
| **Bull Put** | Credit | Width − credit | Net credit | Higher strike − credit |
| **Bear Call** | Credit | Width − credit | Net credit | Lower strike + credit |
| **Bear Put** | Debit | Net debit | Width − debit | Higher strike − debit |

*Width = difference between strike prices*

## Straddle/Strangle Formulas

| Strategy | Max Risk | Upside BE | Downside BE |
|----------|----------|-----------|-------------|
| **Long Straddle** | Net debit (call + put) | Strike + debit | Strike − debit |
| **Short Straddle** | Unlimited | Strike + credit | Strike − credit |
| **Long Strangle** | Net debit (call + put) | Call strike + debit | Put strike − debit |

## Greeks Summary

| Greek | Measures | Long Position | Short Position | ATM Option | ITM Option | OTM Option |
|-------|----------|---------------|----------------|------------|------------|------------|
| **Delta (Δ)** | Price change per $1 underlying move | Positive (calls), Negative (puts) | Negative (calls), Positive (puts) | ~0.50 | >0.50 | <0.50 |
| **Gamma (Γ)** | Delta change per $1 underlying move | Positive | Negative | Highest | Low | Very Low |
| **Theta (Θ)** | Daily time decay | Negative | Positive | Highest decay | Lower decay | Low decay |
| **Vega (ν)** | Price change per 1% IV change | Positive | Negative | Highest | Moderate | Low |

**Key rules**:
- **Delta**: ATM ≈ 50, Deep ITM → 100, Deep OTM → 0. Sum of position deltas = position delta
- **Gamma**: Highest for ATM, short-dated options. High gamma = delta changes fast = increased risk/opportunity
- **Theta**: **Accelerates in last 30 days**. Never hold long options past 30 DTE
- **Vega**: Buy options when IV is low (vega positive). Sell options when IV is high (vega negative)

## Strategy Decision Tree

```
What is your market outlook?
|
├── BULLISH
│   ├── High IV → Bear Put Spread (debit) or short put (if very confident)
│   └── Low IV → Long Call or Bull Call Spread
│
├── BEARISH
│   ├── High IV → Bull Put Spread? NO → Bear Call Spread (credit) or Long Put
│   └── Low IV → Long Put or Bear Put Spread
│
├── NEUTRAL (range-bound)
│   ├── High IV → Iron Butterfly, Short Strangle (hedged)
│   └── Low IV → Long Butterfly, Long Condor, Calendar Spread
│
└── UNCERTAIN DIRECTION (expecting big move)
    ├── High IV → WAIT (options too expensive)
    ├── Low IV + Catalyst → Long Straddle or Long Strangle
    └── Long-term uncertain → Long Synthetic Straddle (adjustable)

FOR STOCK HOLDERS:
├── Neutral/bullish → Covered Call (income)
├── Bearish/defensive → Protective Put or Collar
```

## Key Rules of Thumb

1. **Debit spreads**: Use 90+ DTE. **Credit spreads**: Use <45 DTE
2. Aim for **max reward ≥ 2× max risk** on debit spreads
3. Minimum liquidity: stock volume >300K/day, option open interest >100
4. Never sell naked options (unlimited risk)
5. Always define risk before entering any trade
6. Use limit orders for options (market orders risk poor fills)
7. Check IV percentile — avoid buying when IV is in the top quartile
8. Paper trade new strategies before risking real capital
9. Keep a trading journal tracking both trades and emotions
10. Specialize in 2–3 strategies rather than trying to master all
