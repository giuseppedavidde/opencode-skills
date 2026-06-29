---
name: options-analysis
description: >
  Analyzes multi-leg options positions via trading MCP. Use when user asks
  "analyze my options", "check position", "option Greeks", "payoff".
allowed-tools:
  - read
  - bash
  - task
argument-hint: [ticker with leg details]
---

# Options Position Analyzer

## Execution

### Via MCP (server already running)
```
Call: analyze_options(
    ticker="<TICKER>",
    legs=[{"type":"call"|"put", "strike":float, "qty":int, "entry_premium":float}, ...],
    expiry="<YYYY-MM-DD>"
)
```

Example:
```json
analyze_options("DRAM", [
  {"type": "put", "strike": 45, "qty": -2, "entry_premium": 7.90},
  {"type": "call", "strike": 59, "qty": 1, "entry_premium": 14.90}
], "2026-12-18")
```

Returns: strategy classification, per-leg Greeks + P&L, total Greeks,
payoff at 100 price levels, breakevens, ITM/OTM probabilities, recommendations.

### Or: CLI (standalone, terminal use)
```bash
trading-cli options <TICKER> --leg "put 45 -2 7.90" --leg "call 59 1 14.90" --expiry 2026-12-18
```

## Output (present as structured report)
1. **Strategy name** (Options Playbook classification)
2. **Legs table** — Side | Type | Strike | Entry | Current | P&L | Delta | Theta
3. **Total Greeks** — Delta, Gamma, Theta, Vega
4. **P&L** — Cost basis, current value, total P&L, P&L%
5. **Breakevens** + nearest risk levels
6. **Payoff range** — P&L at -20% / spot / +20%
7. **Recommendations** — Hold / Adjust / Close with rationale

## Auto-chain
For scanner context: call `analyze_stock(ticker=<TICKER>)` first to get VPOC/VAH/VAL.
