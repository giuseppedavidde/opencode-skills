"""Crypto data fetching via CoinGecko and yfinance."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import yfinance as yf


def _coingecko_api_key() -> str | None:
    return os.environ.get("COINGECKO_API_KEY")


def fetch_crypto_yfinance(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Fetch crypto OHLCV via yfinance.

    Args:
        symbol: Crypto symbol (e.g. 'BTC-USD', 'ETH-USD').
        period: Data period.
    """
    t = yf.Ticker(symbol)
    return t.history(period=period)


def fetch_crypto_info_yfinance(symbol: str) -> dict[str, Any]:
    """Fetch crypto info via yfinance."""
    t = yf.Ticker(symbol)
    try:
        return t.info or {}
    except Exception:
        return {}


def fetch_crypto_full(
    coin_id: str, period: str = "1y"
) -> dict[str, Any]:
    """Fetch full crypto data.

    Args:
        coin_id: CoinGecko coin id (e.g. 'bitcoin', 'ethereum').
        period: Data period for yfinance history.

    Returns:
        Dictionary with coin data.
    """
    coingecko_info: dict[str, Any] = {}
    try:
        import json
        import urllib.request

        url = (
            f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            f"?localization=false&tickers=false&community_data=false"
            f"&developer_data=false&sparkline=false"
        )
        req = urllib.request.Request(url)
        api_key = _coingecko_api_key()
        if api_key:
            req.add_header("x-cg-demo-api-key", api_key)
        with urllib.request.urlopen(req, timeout=15) as resp:
            coingecko_info = json.loads(resp.read().decode())
    except Exception:
        pass

    symbol = coingecko_info.get("symbol", coin_id).upper() + "-USD"
    hist = fetch_crypto_yfinance(symbol, period)
    info = fetch_crypto_info_yfinance(symbol)

    price = coingecko_info.get("market_data", {}).get("current_price", {}).get("usd")
    if price is None and not hist.empty:
        price = float(hist["Close"].iloc[-1])
    price = price or 0.0

    market_data = coingecko_info.get("market_data", {})

    return {
        "coin_id": coin_id,
        "symbol": symbol,
        "current_price_usd": price,
        "market_cap": market_data.get("market_cap", {}).get("usd"),
        "total_volume": market_data.get("total_volume", {}).get("usd"),
        "hist": hist,
        "info": info,
        "coingecko": coingecko_info,
    }
