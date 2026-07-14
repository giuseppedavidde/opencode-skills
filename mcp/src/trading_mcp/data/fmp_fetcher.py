"""FMP (FinancialModelingPrep) fundamentals enrichment for the MCP server.

Loads FMP API key from:
1. TRADING_FMP_API_KEY environment variable
2. FMP_API_KEY environment variable
3. ~/.config/opencode/fmp_api_key.txt (text file)

Falls back to None (yfinance-only) when no key is available.

Field names below are verified against the live FMP /stable/ API:
  - ``ratios``           → valuation (P/E, P/B, P/S, D/E, margins, revenue/share)
  - ``key-metrics``      → profitability/quality (ROE, ROA, graham, FCF yield, mcap)
  - ``financial-growth`` → revenueGrowth, epsgrowth
  - ``profile``          → sector, industry, employees, description, exchange
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = 10  # seconds — keep it fast for real-time analysis


def _load_api_key() -> str | None:
    """Load FMP API key from standard locations."""
    # 1. Explicit trading env var
    key = os.environ.get("TRADING_FMP_API_KEY")
    if key:
        return key

    # 2. Generic env var
    key = os.environ.get("FMP_API_KEY")
    if key:
        return key

    # 3. Text file
    key_file = Path.home() / ".config" / "opencode" / "fmp_api_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line != "YOUR_FMP_API_KEY_HERE":
                return line

    return None


def _fmp_get(endpoint: str, symbol: str) -> list[dict[str, Any]]:
    """Call FMP API endpoint, return list of dicts or empty list on failure."""
    key = _load_api_key()
    if not key:
        return []
    try:
        r = requests.get(
            f"{FMP_BASE}/{endpoint}",
            params={"symbol": symbol, "apikey": key},
            timeout=FMP_TIMEOUT,
        )
        data = r.json()
        if isinstance(data, dict) and "Error Message" in str(data):
            logger.warning("FMP API error for %s: %s", symbol, data)
            return []
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("FMP request failed for %s: %s", symbol, e)
        return []


def _merge_mapping(source: dict[str, Any], mapping: dict[str, str],
                   result: dict[str, Any]) -> int:
    """Copy mapped fields from a single FMP record into ``result``.

    Only non-None values are copied. Returns the number of fields added.
    """
    added = 0
    for fmp_key, yf_key in mapping.items():
        val = source.get(fmp_key)
        if val is not None:
            result[yf_key] = val
            added += 1
    return added


def fetch_fmp_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch key fundamentals from FMP for a single ticker.

    Returns a dict of key metrics (P/E, P/B, ROE, etc.) that can be
    merged into the yfinance info dict. Returns empty dict if FMP is
    unavailable.
    """
    ratios = _fmp_get("ratios", symbol)
    key_metrics = _fmp_get("key-metrics", symbol)
    growth = _fmp_get("financial-growth", symbol)
    profile = _fmp_get("profile", symbol)

    result: dict[str, Any] = {}

    # Valuation + per-share + margins (from /stable/ratios)
    ratios_map = {
        "priceToEarningsRatio": "trailingPE",
        "priceToBookRatio": "priceToBook",
        "priceToSalesRatio": "priceToSalesTrailing12Months",
        "debtToEquityRatio": "debtToEquity",
        "revenuePerShare": "revenuePerShare",
        "netProfitMargin": "profitMargins",
        "operatingProfitMargin": "operatingMargins",
        "grossProfitMargin": "grossMargins",
        "enterpriseValueMultiple": "enterpriseToEbitda",
        "dividendYield": "dividendYield",
        "payoutRatio": "payoutRatio",
        "currentRatio": "currentRatio",
    }
    if ratios:
        _merge_mapping(ratios[0], ratios_map, result)

    # Profitability + quality (from /stable/key-metrics)
    key_metrics_map = {
        "returnOnEquity": "returnOnEquity",
        "returnOnAssets": "returnOnAssets",
        "currentRatio": "currentRatio",
        "freeCashFlowYield": "freeCashflow",
        "grahamNumber": "grahamNumber",
        "evToEBITDA": "enterpriseToEbitda",
        "earningsYield": "earningsYield",
    }
    if key_metrics:
        _merge_mapping(key_metrics[0], key_metrics_map, result)
        mcap = key_metrics[0].get("marketCap")
        if mcap is not None:
            result["marketCap"] = mcap

    # Growth (from /stable/financial-growth)
    growth_map = {
        "revenueGrowth": "revenueGrowth",
        "epsgrowth": "earningsGrowth",
    }
    if growth:
        _merge_mapping(growth[0], growth_map, result)

    # Profile (from /stable/profile)
    profile_map = {
        "sector": "sector",
        "industry": "industry",
        "fullTimeEmployees": "fullTimeEmployees",
        "description": "longBusinessSummary",
        "exchangeShortName": "exchange",
    }
    if profile:
        _merge_mapping(profile[0], profile_map, result)

    if result:
        result["_fundamentals_source"] = "fmp"
        logger.info("FMP enriched %s with %d fields", symbol, len(result))
    else:
        logger.debug("FMP returned no data for %s", symbol)

    return result
