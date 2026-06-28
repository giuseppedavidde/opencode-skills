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
