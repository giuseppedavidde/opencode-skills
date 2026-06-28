"""MCP tool registration: Data fetch tools."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from trading_mcp.data.stocks import fetch_stock_full
from trading_mcp.data.crypto import fetch_crypto_full
from trading_mcp.data.options_chain import fetch_options_chain


def register_data_tools(mcp_server: FastMCP) -> None:
    """Register data fetch tools with the MCP server."""

    @mcp_server.tool()
    def fetch_stock_data(ticker: str, period: str = "1y") -> dict[str, Any]:
        """Fetch complete stock data: OHLCV history, fundamentals, and indicators.

        Args:
            ticker: Stock ticker symbol (e.g. 'AAPL', 'ENI.MI').
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max).

        Returns:
            Dictionary with ticker, current_price, ohlcv list, info dict, indicators.
        """
        result = fetch_stock_full(ticker, period)

        hist = result.pop("hist", None)
        ohlcv: list[dict] = []
        if hist is not None and not hist.empty:
            for idx, row in hist.iterrows():
                ohlcv.append({
                    "date": str(idx),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })

        info_safe: dict[str, Any] = {}
        raw_info = result.pop("info", {})
        if raw_info:
            for k, v in raw_info.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    info_safe[k] = v
                elif hasattr(v, "item"):
                    info_safe[k] = v.item() if v is not None else None
                else:
                    info_safe[k] = str(v)

        return {
            "ticker": result["ticker"],
            "current_price": result["current_price"],
            "ohlcv": ohlcv[-252:],
            "info": info_safe,
            "indicators": result.get("indicators", {}),
        }

    @mcp_server.tool()
    def fetch_crypto_data(coin_id: str, period: str = "1y") -> dict[str, Any]:
        """Fetch crypto data from CoinGecko and yfinance.

        Args:
            coin_id: CoinGecko coin id (e.g. 'bitcoin', 'ethereum', 'solana').
            period: Data period for yfinance history.

        Returns:
            Dictionary with coin data including price, market cap, OHLCV.
        """
        result = fetch_crypto_full(coin_id, period)

        hist = result.pop("hist", None)
        ohlcv: list[dict] = []
        if hist is not None and not hist.empty:
            for idx, row in hist.iterrows():
                ohlcv.append({
                    "date": str(idx),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                })

        return {
            "coin_id": result["coin_id"],
            "symbol": result["symbol"],
            "current_price_usd": result["current_price_usd"],
            "market_cap": result.get("market_cap"),
            "total_volume": result.get("total_volume"),
            "ohlcv": ohlcv[-365:],
        }

    @mcp_server.tool()
    def fetch_options_chain(
        ticker: str, expiry: str | None = None
    ) -> dict[str, Any]:
        """Fetch options chain with Greeks and IV metrics.

        Args:
            ticker: Stock ticker symbol.
            expiry: Optional target expiry date (YYYY-MM-DD). Auto-selects nearest >30 DTE.

        Returns:
            Dictionary with calls/puts lists including Greeks, and IV metrics.
        """
        return fetch_options_chain(ticker, expiry)
