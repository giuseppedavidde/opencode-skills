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

Then add to your `opencode.json`. Use **absolute paths** (no `$HOME` in the
shell string) plus an explicit `environment` block so the server never depends
on the ambient `HOME` and behaves identically from any OpenCode conversation,
even with multiple conversations in parallel:

```json
{
  "mcp": {
    "trading": {
      "type": "local",
      "command": [
        "/home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/trading-mcp",
        "--skills-dir", "/home/giuseppe/.config/opencode/skills",
        "--tickers-dir", "/home/giuseppe/.config/opencode/skills/market-accumulation-scanner/data"
      ],
      "environment": {
        "TRADING_SKILLS_DIR": "/home/giuseppe/.config/opencode/skills",
        "TRADING_TICKERS_DIR": "/home/giuseppe/.config/opencode/skills/market-accumulation-scanner/data",
        "TRADING_CACHE_DIR": "/tmp/opencode/options_cache",
        "TRADING_DATA_CACHE_DIR": "/home/giuseppe/.cache/trading_mcp/data"
      },
      "enabled": true
    }
  }
}
```

### Robustness notes

- **Launcher**: the command uses the venv's absolute executable with explicit
  `--skills-dir` / `--tickers-dir` arguments, and an `environment` map that
  pins every cache directory. There is no `bash -c` and no `$HOME` expansion,
  so a missing/changed `HOME` cannot break startup.
- **Interpreter pin**: the venv's `bin/python3` points to the real
  `/usr/bin/python3.14` binary (not a symlink chain through `python3`) and
  `pyvenv.cfg` is kept in sync with the runtime version.
- **Cache safety**: `options_chain`, `provider` and `result_cache` write
  atomically (temp file in the same directory + `os.replace`) and treat
  corrupted/partial files as cache misses. Multiple MCP processes can share
  the same cache directories concurrently without reading half-written files.
- **HOME independence**: `config.py`, `weights_config.py`, `provider.py` and
  `result_cache.py` resolve their directories via explicit env vars with a
  `Path.home()`-based fallback, so startup works even with `HOME` unset.

Quick sanity check (starts clean with no `HOME`):

```bash
env -i HOME= /home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/trading-mcp \
  --skills-dir /home/giuseppe/.config/opencode/skills \
  --tickers-dir /home/giuseppe/.config/opencode/skills/market-accumulation-scanner/data
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
