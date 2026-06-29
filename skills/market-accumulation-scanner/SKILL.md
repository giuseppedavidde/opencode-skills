---
name: market-accumulation-scanner
description: >
  Scans stock/crypto markets for accumulation patterns via trading MCP.
  Use when the user asks "scan", "scanner", "market scan", "find stocks".
allowed-tools:
  - read
  - bash
  - task
argument-hint: [universe or ticker list]
orchestrator:
  parallel: true
  split_by: ticker
  chunk_size: 15
  merge: rank
  merge_key: final_score
  top_n: 15
---

# Market Scanner

## Execution

### Step 1 — Scan via MCP (server already running, zero cold start)
```
Call: scan_market(universe="<NAME>", min_score=50, top_n=15, fetch_news=True)
```

For custom tickers:
```
Call: scan_market(tickers="AAPL,MSFT,NVDA", min_score=40, top_n=10, fetch_news=True)
```

The MCP server uses ThreadPoolExecutor (20 workers) — ~45s for 500 tickers.
Returns ranked JSON with dimensions, modifiers, indicators, sentiment breakdown.

### Step 2 — Present results
Table: `# | Ticker | Score | Pattern | Sector | Price | Flags`

### Step 3 — Deep dive top 3
```
Call: analyze_stock(ticker="<TOP_TICKER>", verbose=true, fetch_news=true)
```
Repeat for top 3 candidates.

### Step 4 — Options (if requested)
Chain to `options-strategy-suggestions` skill.

## Universes
`us_large` | `us_tech` | `all` | `italy` | `germany` | `france` | `uk` | `spain` | `crypto`
