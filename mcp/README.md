# trading-mcp-server

MCP server for stock/crypto market analysis using Wyckoff, Volume Profile, VPA, and options analysis.

Part of the [opencode-skills](https://github.com/biocontext-ai/opencode-skills) ecosystem.

## Overview

Exposes 9 MCP tools for deterministic market analysis:

| Tool | Category | Description |
|------|----------|-------------|
| `fetch_stock_data` | Data | OHLCV + fundamentals via yfinance |
| `fetch_crypto_data` | Data | CoinGecko + yfinance crypto |
| `fetch_options_chain` | Data | Options chain + Greeks + IV metrics |
| `scan_market` | Analysis | Multi-market accumulation scanner (ranked) |
| `analyze_stock` | Analysis | Deep single-stock Wyckoff/VP/VPA analysis |
| `analyze_options` | Analysis | Multi-leg options: Greeks, payoff, probabilities |
| `get_macro_context` | Knowledge | VIX, DXY, Fed, regime, dynamic weights |
| `get_skill_knowledge` | Knowledge | On-demand skill knowledge from SKILL.md |
| `suggest_options_strategy` | Knowledge | Strategy recommendation from verdict |

## Quick Install

```bash
./setup-trading-mcp.sh
```

This creates a venv at `~/.local/share/opencode/trading-mcp-venv/` and installs the package.

Then add to your `opencode.json`:

```json
{
  "mcp": {
    "trading": {
      "type": "local",
      "command": ["/home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/trading-mcp"],
      "args": [],
      "enabled": true
    }
  }
}
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Token Savings

When used with OpenCode, this MCP server reduces context window usage by 80-95% compared to loading full trading skills. Analysis that previously consumed ~20K tokens now uses ~1K.

## Architecture

```
trading_mcp/
├── data/           # yfinance, CoinGecko, options chain fetch
├── analysis/       # Wyckoff, Volume Profile, VPA, sentiment, indicators
├── knowledge/      # Skill bridge (reads SKILL.md)
└── tools/          # MCP tool registration
```
