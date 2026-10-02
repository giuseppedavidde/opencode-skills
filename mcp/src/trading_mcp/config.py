"""Configuration constants for trading-mcp-server."""

from __future__ import annotations

import os
from pathlib import Path


def _default_skills_dir() -> Path:
    """Resolve the default skills directory without depending on ``$HOME``.

    Resolution order (first existing/usable wins):
      1. ``TRADING_SKILLS_DIR`` environment variable (explicit override).
      2. ``$HOME/.config/opencode/skills`` (classic layout).
      3. ``Path.home()/.config/opencode/skills`` (HOME-independent fallback;
         ``Path.home()`` is robust even when ``$HOME`` is unset).
      4. A well-known absolute path if it exists on this machine.

    The function never raises: a missing HOME degrades to the default
    ``.../.config/opencode/skills`` path so that import-time resolution is
    always deterministic.
    """
    env_dir = os.environ.get("TRADING_SKILLS_DIR")
    if env_dir:
        return Path(env_dir)

    candidates: list[Path] = []
    home_env = os.environ.get("HOME")
    if home_env:
        candidates.append(Path(home_env) / ".config" / "opencode" / "skills")
    try:
        candidates.append(Path.home() / ".config" / "opencode" / "skills")
    except (RuntimeError, OSError):
        pass
    candidates.append(Path("/home/giuseppe/.config/opencode/skills"))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else Path(".config/opencode/skills")


SKILLS_DIR: Path = _default_skills_dir()

TICKERS_DIR: Path = Path(
    os.environ.get(
        "TRADING_TICKERS_DIR",
        SKILLS_DIR / "market-accumulation-scanner" / "data",
    )
)

# P1 Aug 2026: RISK_FREE_RATE kept as FALLBACK only.
# Use trading_mcp.data.risk_free.get_risk_free_rate() for live rates.
FALLBACK_RISK_FREE_RATE: float = 0.045

# Backward-compatible alias for code not yet migrated to provider:
RISK_FREE_RATE: float = FALLBACK_RISK_FREE_RATE

from trading_mcp.weights_config import load_weights, get_weights

WEIGHTS_CONFIG = load_weights()

# FMP API key (optional — fundamentals still work via yfinance without it)
FMP_API_KEY: str | None = os.environ.get("TRADING_FMP_API_KEY") or os.environ.get("FMP_API_KEY") or None

# Alpha Vantage API key (optional — free tier: 25 calls/day, sufficient for enrichment)
ALPHA_VANTAGE_API_KEY: str | None = (
    os.environ.get("TRADING_AV_API_KEY")
    or os.environ.get("ALPHA_VANTAGE_API_KEY")
    or None
)
