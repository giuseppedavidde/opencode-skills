"""FMP (FinancialModelingPrep) fundamentals for the MCP server.

Loads the FMP API key from:
1. TRADING_FMP_API_KEY environment variable
2. FMP_API_KEY environment variable
3. ~/.config/opencode/fmp_api_key.txt (text file)

Without a key every function returns an empty result (yfinance only).

The key travels in the query string (``apikey=``), so no URL or raw
exception text is ever logged or returned: messages go through
:func:`trading_mcp.data.redact.redact` and only the exception type is
logged (DATA-14).

Endpoints (``/stable``): ``ratios`` (fiscal-year valuation, leverage and
margins), ``key-metrics`` (ROE, ROA, FCF yield, market cap),
``financial-growth`` and ``profile``. :func:`fetch_fmp_normalized` returns
the typed :class:`~trading_mcp.data.fundamentals_schema.Fundamentals`;
:func:`fetch_fmp_fundamentals` renders it in yfinance keys and units.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

from trading_mcp.data.fundamentals_schema import Fundamentals, from_fmp
from trading_mcp.data.redact import install_log_redaction, redact

logger = logging.getLogger(__name__)
install_log_redaction()

FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = 10  # seconds


def _load_api_key() -> str | None:
    """Load the FMP API key from the standard locations."""
    for name in ("TRADING_FMP_API_KEY", "FMP_API_KEY"):
        key = os.environ.get(name)
        if key:
            return key
    key_file = Path.home() / ".config" / "opencode" / "fmp_api_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line != "YOUR_FMP_API_KEY_HERE":
                return line
    return None


def _fmp_get(endpoint: str, symbol: str) -> list[dict[str, Any]]:
    """Call one FMP endpoint; an empty list on any failure (never raises)."""
    key = _load_api_key()
    if not key:
        return []
    try:
        response = requests.get(
            f"{FMP_BASE}/{endpoint}",
            params={"symbol": symbol, "apikey": key},
            timeout=FMP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("FMP %s request failed for %s: %s", endpoint, symbol, type(exc).__name__)
        return []
    status = response.status_code
    if status == 429:
        logger.warning("FMP rate limit (HTTP 429) for %s %s", endpoint, symbol)
        return []
    if status >= 400:
        logger.warning("FMP %s HTTP %s for %s", endpoint, status, symbol)
        return []
    try:
        data = response.json()
    except ValueError:
        logger.warning("FMP %s returned invalid JSON for %s", endpoint, symbol)
        return []
    if isinstance(data, dict):
        message = redact(str(data.get("Error Message") or data.get("message") or data))[:160]
        logger.warning("FMP %s error for %s: %s", endpoint, symbol, message)
        return []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def fetch_fmp_normalized(symbol: str) -> Fundamentals | None:
    """Typed FMP fundamentals (fiscal-year periods), or ``None`` without data."""
    ratios = _fmp_get("ratios", symbol)
    key_metrics = _fmp_get("key-metrics", symbol)
    growth = _fmp_get("financial-growth", symbol)
    profile = _fmp_get("profile", symbol)
    if not (ratios or key_metrics or growth or profile):
        return None
    result = from_fmp(symbol, ratios, key_metrics, growth, profile)
    if not result.fields and not result.profile:
        return None
    logger.info("FMP fundamentals for %s: %d fields", symbol, len(result.fields))
    return result


def fetch_fmp_fundamentals(symbol: str) -> dict[str, Any]:
    """FMP fundamentals in yfinance keys AND yfinance units (``{}`` without data).

    ``debtToEquity`` is a percent, ``dividendYield`` a percent and
    ``trailingAnnualDividendYield`` a fraction, as in yfinance 1.5.1. The
    fiscal-year P/E is ``_peFiscalYear`` and the FCF yield ``_fcfYield``.
    """
    normalized = fetch_fmp_normalized(symbol)
    if normalized is None:
        return {}
    legacy = normalized.to_legacy_info()
    legacy["_fundamentals_source"] = "fmp"
    return legacy
