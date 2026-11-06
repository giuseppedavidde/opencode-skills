# trading-mcp-server

MCP server for stock/crypto market analysis using Wyckoff, Volume Profile, VPA, and options analysis.

Part of the [opencode-skills](https://github.com/biocontext-ai/opencode-skills) ecosystem.

## Overview

Exposes 17 MCP tools for deterministic market analysis. Every tool declares a
typed `outputSchema` (see [`src/trading_mcp/responses.py`](src/trading_mcp/responses.py)),
so a client knows the payload shape before the first call.

| Tool | Category | Description |
|------|----------|-------------|
| `fetch_stock_data` | Data | OHLCV + fundamentals via yfinance |
| `fetch_crypto_data` | Data | CoinGecko + yfinance crypto |
| `fetch_options_chain` | Data | Options chain + Greeks + IV metrics |
| `scan_market` | Analysis | Multi-market accumulation scanner (ranked) |
| `analyze_stock` | Analysis | Deep single-stock Wyckoff/VP/VPA analysis |
| `analyze_options` | Analysis | Multi-leg options: Greeks, payoff, probabilities |
| `gex_analysis` | Analysis | Gamma exposure, gamma flip, call/put walls |
| `breakout_context` | Analysis | Momentum bias guard + conditional breakout trigger |
| `get_macro_context` | Knowledge | VIX, DXY, Fed, regime, dynamic weights |
| `clear_macro_cache` | Knowledge | Force a macro refresh |
| `get_skill_knowledge` | Knowledge | On-demand skill knowledge from SKILL.md |
| `suggest_options_strategy` | Knowledge | Strategy recommendation from verdict |
| `bali_signals` | Quant | RVol–IVol and CVol–PVol spreads (Bali 2009) |
| `tsmom_signals` | Quant | Time-series momentum (Moskowitz 2012) |
| `bakshi_signals` | Quant | Variance risk premium (Bakshi 2003) |
| `lgbm_predict` | Quant | LightGBM stacking ensemble score |
| `lgbm_postprocess` | Quant | Skill-driven adjustment of the LGBM score |

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
pytest                      # contract, cache, GEX, backends, benchmark
pylint src/trading_mcp
```

### Typed output contract

Each tool's return annotation is a Pydantic model from
`src/trading_mcp/responses.py`; FastMCP turns it into the tool `outputSchema`.
Models set `extra="allow"`, so typing a tool validates the payload without
dropping vendor fields. `tests/test_responses_contract.py` enforces both
invariants and fails if a tool stops advertising a schema.

The contract is versioned (`CONTRACT_VERSION`) and snapshotted in
[`docs/contract/tools.json`](docs/contract/tools.json). CI runs
`python scripts/export_contract.py --check`: a schema change without a
version bump fails, and so does a version bump without a regenerated
snapshot. `python scripts/export_contract.py` rewrites the snapshot.

### Provenance and error envelope

Every payload carries `data_source`, `data_quality` and `as_of` (null when
the upstream source exposes no data date — never an invented value).
Failures use one envelope: `error`, `error_kind` (`blocking`/`degraded`),
`error_retryable`, built with `responses.error_payload()`. Models that only
set the legacy `error`/`error_is_blocking` fields get `error_kind` derived
automatically, so the semantics are uniform without touching every call
site.

### Calibration provenance

Thresholds come from `research/breakout_calibration/output/thresholds.json`,
locked by `thresholds.lock.json` (SHA-256 of the canonical payload).
`breakout_context` cites `artifact_version`, `artifact_fingerprint`,
`artifact_verified` and `calibration_as_of` in its `evidence` block. Editing
the thresholds without re-locking flips `artifact_verified` to false instead
of silently changing results.
Re-lock after an intentional change:
`python -m trading_mcp.calibration research/breakout_calibration/output/thresholds.json`.

`src/trading_mcp/schemas.py` is the shared analysis *vocabulary* (unified
verdict, macro score, sentiment sub-scores) used across skills — not the wire
contract. One owner per concept: the legacy duplicate `GexResult` was removed
in favour of `trading_mcp.analysis.gex.GexResult`.

## Token Cost

Measured, not asserted — see
[`research/token_benchmark/`](research/token_benchmark/) for the harness and
the full report:

| Scenario | MCP payload | Raw data + skill text | Savings |
|---|---:|---:|---:|
| `analyze_stock` | 967 | 12,935 | 92.5% |
| `scan_market` (12 tickers) | 1,109 | 78,886 | 98.6% |
| `bali_signals` | 224 | 12,826 | 98.3% |

The saving comes from the data never entering the context: the server ranks
500 tickers and returns the ranking, instead of the model reading 500 OHLCV
series. The per-session cost of the tool definitions is reported separately
(3,018 tokens with input schemas, 9,993 with typed output schemas and
provenance), so the net effect is visible for short sessions too. Values are
`len(text)/4` estimates; the baseline excludes fundamentals and news, which
makes the numbers conservative.

The committed [`budget.json`](research/token_benchmark/budget.json) turns the
measurement into a gate: CI fails when a payload exceeds its limit, when the
schema grows past its budget, or when a new tool is added without a reviewed
budget update (`python -m research.token_benchmark.benchmark --check-budget`).

### Repeatability (A/B harness)

[`research/ab_outcome/`](research/ab_outcome/) runs seven representative tasks
cold (result cache cleared) and warm, and compares the decision fields. The
current run is 7/7 stable: the cache changes speed, not semantics. The
model-with-MCP vs model-without-MCP half needs the agent runtime; the task
definitions and comparison protocol are in that directory's README.

## Architecture

```
trading_mcp/
├── data/           # yfinance, CoinGecko, options chain fetch
├── analysis/       # Wyckoff, Volume Profile, VPA, sentiment, indicators
├── knowledge/      # Skill bridge (reads SKILL.md)
└── tools/          # MCP tool registration
```
