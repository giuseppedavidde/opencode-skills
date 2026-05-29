---
name: options-analysis
description: "Analyze multi-leg options positions with Greeks, payoff scenarios, and recommendations. Triggers: 'analyze options', 'cosa fare con le opzioni', 'options position', 'opzioni', 'position analysis', 'Greeks', 'payoff', 'cosa fare', 'analizza opzioni'."
---

# Skill: options-analysis

Analyze and evaluate multi-leg options positions across any ticker with an options chain. Calculates Greeks, payoff scenarios at expiration, probabilities, and generates structured recommendations.

## When to use

- User asks `analyze options for TICKER` with a position description
- User asks `what should I do with my options position?`
- User provides legs like "long 1 call strike 55 @ 4.20, short 2 puts strike 50 @ 2.10"

## Script

```bash
python ~/.config/opencode/skills/options-analysis/scripts/analyze_position.py TICKER \
  --leg "type strike qty entry" \
  [--leg "type strike qty entry" ...] \
  [--expiry "YYYY-MM-DD"] \
  [--output json]
```

### Input format

- **type**: `call` or `put`
- **strike**: strike price (float)
- **qty**: positive = long, negative = short (e.g. +1, -2)
- **entry**: entry premium paid/received per share

### Output

1. Market snapshot (current price, IV, 52w range, volume)
2. Greeks per leg (Option Δ, Position Δ, Position Γ, Position Θ/day, Position Vega/%IV)
3. Position-level Greeks (delta equivalent shares, net gamma/theta/vega)
4. Payoff scenarios at expiration (15+ price levels)
5. Probabilities (ITM/OTM per strike, overall P&L positive)
6. Structured recommendations: Hold / Adjust / Close

### Greeks conventions

| Leg | Option Δ | Position Δ |
|-----|----------|-----------|
| Long Call | +Δ | +Δ |
| Short Call | -Δ | -Δ |
| Long Put | -Δ | -Δ |
| Short Put | -Δ | +Δ ← inverted sign because short |

Position Greeks = Option Greeks × |qty| × sign(qty)

### Dependencies

```bash
pip install yfinance scipy numpy
```

Always use a Python virtual environment — never pip install on the system Python.

### Usage notes

- All Greek calculations use Black-Scholes with r=4.5% (approximate US 1yr rate).
- Greeks are computed per-leg using the IV from that specific strike in the options chain.
- Position Greeks = Option Greeks × qty (positive = long, negative = short).
- Probabilities use the lognormal model (Black-Scholes d2 / -d2).
- Breakevens are found numerically by scanning 5000 price points.
- IV Rank compares current chain-wide IV to its min/max across strikes.
