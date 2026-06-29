---
name: options-strategy-suggestions
description: >
  Suggests options strategy from stock analysis verdict + IV regime.
  Use when user asks "what options strategy", "strategia opzioni",
  "how to trade [ticker] with options", or after stock analysis.
allowed-tools:
  - read
  - bash
  - task
argument-hint: [ticker with analysis context]
---

# Options Strategy Suggestions

## Execution

### Via MCP (server already running)
```
Call: suggest_options_strategy(
    ticker="<TICKER>",
    composite_score=<SCORE>,
    verdict="<VERDICT>",
    risk_tolerance="medium"
)
```
The MCP tool auto-fetches IV rank and applies the strategy matrix.

### Strategy matrix

| Verdict | Score | IV Regime | Strategy | DTE |
|---------|-------|-----------|----------|-----|
| Long-Term | ≥ 75 | HIGH/NORMAL | Synthetic Long 2:1 | 60-90 |
| Long-Term | ≥ 70 | any | LEAPS Call | 300+ |
| Short-Term Bull | any | any | Bull Call Spread | 45-60 |
| Short-Term Neutral | any | HIGH | Iron Condor | 45 |
| Short-Term Neutral | any | LOW/NORMAL | Cash-Secured Put | 30-45 |
| Avoid | any | any | **NO ENTRY** | — |

### Synthetic Long 2:1 rules (only when score ≥ 75)
- Structure: Sell 2x OTM Put + Buy 1x ATM/OTM Call
- Put strike: ~10% below spot (use ATR)
- Call strike: ATM or slightly OTM
- DTE: 60-90
- Exit: 50% at +30% gain, 50% at +50% gain
- Stop: close if stock breaks below VAL

## Output
1. **Strategy name** + structure description
2. **Rationale** — why this strategy (verdict + IV regime match)
3. **Suggested strikes** — from spot price and ATR
4. **Exit plan** — TP, SL, time stop
5. **Warnings** — earnings, IV crush, assignment risk
