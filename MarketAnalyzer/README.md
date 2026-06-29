# MarketAnalyzer

Streamlit dashboard for market analysis powered by the `trading_mcp` engine.

## Quick Start

```bash
cd MarketAnalyzer
pip install -r requirements.txt
streamlit run app.py
```

## Tabs

- **Macro Dashboard** — VIX, DXY, regime, dynamic weights (5-min TTL cache)
- **Market Scanner** — Multi-universe accumulation scan with sortable results table
- **Stock Analyzer** — Deep ticker analysis (5 dimensions + modifiers + indicators)
- **Options Analyzer** — Multi-leg position Greeks, P&L, payoff chart

## Architecture

Imports `trading_mcp` modules directly — zero MCP protocol overhead, zero CLI subprocess.
All expensive operations cached via `@st.cache_data`.
