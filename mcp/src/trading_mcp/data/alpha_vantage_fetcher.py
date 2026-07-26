"""Alpha Vantage fundamentals enrichment for the MCP server.

Free tier: 25 API calls/day, 5 calls/minute.
Fallback a yfinance quando il limite è raggiunto.

Carica API key da:
1. TRADING_AV_API_KEY env var
2. ALPHA_VANTAGE_API_KEY env var
3. ~/.config/opencode/alpha_vantage_key.txt
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

AV_BASE = "https://www.alphavantage.co/query"
AV_TIMEOUT = 10  # secondi


# ─── Rate limiter (5 chiamate/min, 25/giorno) ───────────────────────

@dataclass
class RateLimiter:
    """Semplice rate limiter per Alpha Vantage free tier."""
    max_per_minute: int = 5
    max_per_day: int = 25
    calls_minute: list[float] = field(default_factory=list)
    calls_day: int = 0
    _day_reset: str = ""

    def allow(self) -> bool:
        now = time.time()
        today = date.today().isoformat()

        # Reset giornaliero
        if self._day_reset != today:
            self.calls_day = 0
            self._day_reset = today

        # Check limiti
        if self.calls_day >= self.max_per_day:
            return False

        # Pulisci chiamate più vecchie di 60s
        self.calls_minute = [t for t in self.calls_minute if now - t < 60]
        if len(self.calls_minute) >= self.max_per_minute:
            return False

        return True

    def record_call(self) -> None:
        now = time.time()
        today = date.today().isoformat()
        if self._day_reset != today:
            self.calls_day = 0
            self._day_reset = today
        self.calls_minute.append(now)
        self.calls_day += 1

    def remaining_today(self) -> int:
        today = date.today().isoformat()
        if self._day_reset != today:
            return self.max_per_day
        return max(0, self.max_per_day - self.calls_day)


_av_limiter = RateLimiter()


# ─── API key ───────────────────────────────────────────────────────

ALPHA_VANTAGE_API_KEY: str | None = None


def _load_api_key() -> str | None:
    """Load Alpha Vantage API key from standard locations."""
    # 1. Trading-specific env var
    key = os.environ.get("TRADING_AV_API_KEY")
    if key:
        return key

    # 2. Generic env var
    key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if key:
        return key

    # 3. Text file
    key_file = Path.home() / ".config" / "opencode" / "alpha_vantage_key.txt"
    if key_file.exists():
        for line in key_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line

    return None


# ─── API calls ─────────────────────────────────────────────────────

def _av_get(function: str, symbol: str) -> dict[str, Any] | None:
    """Call Alpha Vantage API, return parsed JSON or None on failure.

    Rispetta il rate limiter free tier (5/min, 25/giorno).
    Restituisce None silenziosamente se il limite è raggiunto.
    """
    key = _load_api_key()
    if not key:
        return None

    if not _av_limiter.allow():
        logger.debug("AV rate limit: %d calls remaining today",
                     _av_limiter.remaining_today())
        return None

    try:
        r = requests.get(
            AV_BASE,
            params={"function": function, "symbol": symbol, "apikey": key},
            timeout=AV_TIMEOUT,
        )
        data = r.json()

        # Rileva errori API
        if isinstance(data, dict):
            if "Error Message" in data:
                logger.warning("AV error for %s: %s", symbol, data["Error Message"])
                return None
            if "Note" in data:
                logger.warning("AV rate limited for %s: %s", symbol, data["Note"])
                return None
            if "Information" in data:
                logger.info("AV info for %s: %s", symbol, data["Information"])
                return None

        _av_limiter.record_call()
        return data

    except Exception as e:
        logger.debug("AV request failed for %s: %s", symbol, e)
        return None


# ─── Enrichment ────────────────────────────────────────────────────

def fetch_av_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch fundamentals from Alpha Vantage.

    1 chiamata API per ticker (OVERVIEW → ~25 campi chiave).
    Consuma 1 delle 25 chiamate giornaliere del free tier.

    Per dati storici (INCOME_STATEMENT, EARNINGS) usa
    fetch_av_historical() separatamente — consuma altre 2 chiamate.

    Restituisce dict vuoto se AV non disponibile o rate-limited.
    """
    result: dict[str, Any] = {}

    overview = _av_get("OVERVIEW", symbol)
    if not overview:
        return result

    overview_map = {
        "PERatio": "trailingPE",
        "PriceToBookRatio": "priceToBook",
        "PriceToSalesRatio": "priceToSalesTrailing12Months",
        "ReturnOnEquityTTM": "returnOnEquity",
        "ReturnOnAssetsTTM": "returnOnAssets",
        "DebtToEquityRatio": "debtToEquity",
        "ProfitMargin": "profitMargins",
        "OperatingMarginTTM": "operatingMargins",
        "QuarterlyEarningsGrowthYOY": "earningsGrowth",
        "RevenueGrowth": "revenueGrowth",
        "CurrentRatio": "currentRatio",
        "MarketCapitalization": "marketCap",
        "Beta": "beta",
        "DividendYield": "dividendYield",
        "EPS": "trailingEps",
        "ForwardPE": "forwardPE",
        "PEGRatio": "pegRatio",
        "EVToEBITDA": "enterpriseToEbitda",
        "EVToRevenue": "enterpriseToRevenue",
        "ShortRatio": "shortRatio",
        "SharesOutstanding": "sharesOutstanding",
        "RevenueTTM": "totalRevenue",
        "OperatingCashFlowTTM": "operatingCashflow",
        "FreeCashFlowTTM": "freeCashflow",
        "AnalystTargetPrice": "targetMeanPrice",
        "52WeekHigh": "fiftyTwoWeekHigh",
        "52WeekLow": "fiftyTwoWeekLow",
        "50DayMovingAverage": "fiftyDayAverage",
        "200DayMovingAverage": "twoHundredDayAverage",
        "ReturnOnEquity": "returnOnEquity",
    }

    for av_key, yf_key in overview_map.items():
        val = overview.get(av_key)
        if val is not None and val != "None" and val != "":
            try:
                result[yf_key] = float(val)
            except (ValueError, TypeError):
                pass

    if result:
        result["_fundamentals_source"] = "alpha_vantage"
        remaining = _av_limiter.remaining_today()
        logger.info("AV enriched %s with %d fields (remaining: %d/%d)",
                    symbol, len(result), remaining, _av_limiter.max_per_day)

    return result


def fetch_av_historical(symbol: str) -> dict[str, Any]:
    """Fetch historical financial data per backtest point-in-time.

    Consuma 2 chiamate API: INCOME_STATEMENT + EARNINGS.
    Solo per backtest LGBM o analisi fondamentali storiche.

    Restituisce dict con:
    - _av_annual_reports: ultimi 5 anni
    - _av_quarterly_reports: ultimi 8 trimestri
    - _av_earnings_history: ultimi 8 trimestri
    """
    result: dict[str, Any] = {}

    income = _av_get("INCOME_STATEMENT", symbol)
    if income and "annualReports" in income:
        result["_av_annual_reports"] = income["annualReports"][:5]
        result["_av_quarterly_reports"] = income.get("quarterlyReports", [])[:8]

    earnings = _av_get("EARNINGS", symbol)
    if earnings and "annualEarnings" in earnings:
        result["_av_earnings_history"] = earnings.get("quarterlyEarnings", [])[:8]

    if result:
        logger.info("AV historical data for %s (remaining: %d/%d)",
                    symbol, _av_limiter.remaining_today(), _av_limiter.max_per_day)

    return result


def remaining_calls_today() -> int:
    """Quante chiamate AV rimangono oggi (free tier)."""
    return _av_limiter.remaining_today()
