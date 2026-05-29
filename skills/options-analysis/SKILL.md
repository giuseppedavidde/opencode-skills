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

1. **Options Playbook** — Strategy classification (structure name, outlook, risk profile)
2. **Greeks & P&L** — Per-leg and position-level Greeks with current P&L
3. **Volume Profile (1yr)** — VPOC, Value Area (VAH/VAL), HVN/LVN zones, strikes vs profile
4. **Sentiment (Trading Against the Crowd)** — Put/Call OI and volume ratios, IV extremes, contrarian signals
5. **Payoff scenarios** at expiration (13 price levels + breakevens)
6. **Probabilities** — ITM/OTM per strike, overall P&L > 0
7. **Recommendations** — Hold / Adjust / Close with integrated context from all frameworks

### Greeks conventions

| Leg | Option Δ | Position Δ |
|-----|----------|-----------|
| Long Call | +Δ | +Δ |
| Short Call | -Δ | -Δ |
| Long Put | -Δ | -Δ |
| Short Put | -Δ | +Δ |

Position Greeks = Option Greeks × qty (positive = long, negative = short)

### Dependencies

```bash
pip install yfinance scipy numpy
```

Always use a Python virtual environment.

### Usage notes

- Greeks: Black-Scholes with r=4.5% (approximate US 1yr rate). IV per-leg from options chain.
- Probabilities: lognormal model (Black-Scholes d2 / -d2).
- Breakevens: numerical scan of 5000 price points.
- IV Rank: current chain-wide IV vs min/max across strikes.
- Volume Profile: 60 bins over 1 year of daily OHLCV. VPOC = max volume bin; VAH/VAL = 70% volume envelope around VPOC; HVN = 2x avg vol; LVN = 0.3x avg vol.
- Sentiment: PC ratios from options chain OI/volume. IV Rank extremes flagged.
- Strategy classification: detects structure from leg types, quantities, and strikes.
