"""Configuration constants for trading-mcp-server."""

from __future__ import annotations

import os
from pathlib import Path

SKILLS_DIR: Path = Path(
    os.environ.get(
        "TRADING_SKILLS_DIR",
        os.path.join(os.environ.get("HOME", str(Path.home())), ".config", "opencode", "skills"),
    )
)

TICKERS_DIR: Path = Path(
    os.environ.get(
        "TRADING_TICKERS_DIR",
        SKILLS_DIR / "market-accumulation-scanner" / "data",
    )
)

RISK_FREE_RATE: float = 0.045

from trading_mcp.weights_config import load_weights, get_weights

WEIGHTS_CONFIG = load_weights()

# FMP API key (optional — fundamentals still work via yfinance without it)
FMP_API_KEY: str | None = os.environ.get("TRADING_FMP_API_KEY") or os.environ.get("FMP_API_KEY") or None
