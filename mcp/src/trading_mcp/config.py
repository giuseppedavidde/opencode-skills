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


# ── Options data backends ─────────────────────────────────────────────
# Primary source is ThetaData (US options with native greeks/IV/OI), then
# Polygon, MarketData.app, and finally yfinance as an emergency fallback
# (also used for dividend yields). With no keys/daemon the availability
# probe drops everything except yfinance, so zero-config still works.
def _csv_env(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated env var into a lower-case list (fallback default)."""
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return items or list(default)


DEFAULT_OPTIONS_BACKENDS: list[str] = ["thetadata", "polygon", "marketdata", "yfinance"]

OPTIONS_BACKENDS: list[str] = _csv_env("TRADING_OPTIONS_BACKENDS", DEFAULT_OPTIONS_BACKENDS)

# ThetaData: local Java Theta Terminal daemon + API key (US options, native greeks).
THETADATA_API_KEY: str | None = (
    os.environ.get("TRADING_THETADATA_API_KEY")
    or os.environ.get("THETADATA_API_KEY")
    or None
)
THETADATA_URL: str = (
    os.environ.get("TRADING_THETADATA_URL")
    or os.environ.get("THETADATA_URL")
    or "http://127.0.0.1:25510"
)

# Polygon.io: REST, free tier ~5 req/min (options EOD/snapshot).
POLYGON_API_KEY: str | None = (
    os.environ.get("TRADING_POLYGON_API_KEY")
    or os.environ.get("POLYGON_API_KEY")
    or None
)

# MarketData.app: REST, free tier ~100 req/day (options with greeks/IV).
MARKETDATA_API_KEY: str | None = (
    os.environ.get("TRADING_MARKETDATA_API_KEY")
    or os.environ.get("MARKETDATA_API_KEY")
    or os.environ.get("MARKETDATAAPP_API_KEY")
    or None
)
