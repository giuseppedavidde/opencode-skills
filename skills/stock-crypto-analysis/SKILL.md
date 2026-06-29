---
name: stock-crypto-analysis
version: "2.0"
description: >
  Deep single-stock/crypto analysis via trading MCP. Use when user asks
  "analyze [ticker]", "deep dive", "cosa farne", "what to do with [ticker]".
allowed-tools:
  - read
  - bash
  - task
  - websearch
argument-hint: [ticker or crypto name]
---

# Stock & Crypto Analysis

## Execution

### Step 1 — Macro always first
```
Call: get_macro_context()
```
Gives VIX, DXY, regime, dynamic weights. Adapt analysis to the regime.

### Step 2 — Core analysis via MCP (server already running)
```
Call: analyze_stock(ticker="<TICKER>", verbose=true, fetch_news=true, include_options_context=true)
```
Returns: composite_score, verdict, confidence, signal_alignment,
5 dimensions (Wyckoff, VP, PA, Sentiment, Fundamentals) with detail strings,
5 modifiers (MTF, SOT, Squeeze, Earnings, 6-Clue),
11 indicators, sentiment breakdown, flags, pattern, options_context.

### Step 3 — Synthesize verdict
- Score ≥ 70 → **Long-Term Investment**
- 50-69 → **Short-Term Speculation (Bullish)**
- < 50 → **Avoid / Wait**
- Check `confidence` (HIGH/MEDIUM/LOW) and `signal_alignment.pct`

### Step 4 — Options strategy (if applicable)
```
Call: suggest_options_strategy(ticker="<TICKER>", composite_score=<SCORE>, verdict="<VERDICT>")
```

### Step 5 — Risk sizing (optional, if user wants entry plan)
```bash
python scripts/dynamic_weights.py --vix <from macro> --dxy-trend <from macro> --json
```

## Output format
1. Macro context — regime, VIX, dynamic weights
2. **Score + Verdict + Confidence** (% signal alignment)
3. **5 Dimensions** — name, score, key detail excerpt
4. **5 Modifiers** — name, score, interpretation
5. **Key risks** — value_trap, vertical_rally, earnings proximity
6. **Entry/Exit** — from options_context VPOC/VAH/VAL
7. **Options strategy** — if applicable

## Crypto
Same flow. Engine auto-detects and adjusts weights (Wyckoff 25%, VP 25%, PA 20%, Crypto APC 30%).
