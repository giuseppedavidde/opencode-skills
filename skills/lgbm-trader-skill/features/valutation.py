"""Fundamental valuation — P/E, P/B, market cap, earnings yield."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from utils.logger import get_logger

logger = get_logger("features.valutation")

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "val_pe_ratio": "Price to Earnings ratio",
    "val_pb_ratio": "Price to Book ratio",
    "val_ps_ratio": "Price to Sales ratio",
    "val_ev_ebitda": "Enterprise Value / EBITDA",
    "val_earnings_yield": "Earnings yield (1/PE)",
    "val_market_cap": "Market capitalization (billions)",
    "val_div_yield": "Dividend yield",
    "val_roe": "Return on Equity",
    "val_profit_margins": "Profit margins",
    "val_revenue_growth": "Revenue growth (YoY)",
    "val_peg_ratio": "P/E to Growth ratio",
}


def fetch_valutation(ticker: str) -> dict:
    """Fetcha metriche di valutazione da yfinance info."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        pe = info.get("trailingPE") or info.get("forwardPE")
        return {
            "val_pe_ratio": pe,
            "val_pb_ratio": info.get("priceToBook"),
            "val_ps_ratio": info.get("priceToSalesTrailing12Months"),
            "val_ev_ebitda": info.get("enterpriseToEbitda"),
            "val_earnings_yield": 1.0 / pe if pe and pe > 0 else None,
            "val_market_cap": info.get("marketCap"),
            "val_div_yield": info.get("dividendYield"),
            "val_roe": info.get("returnOnEquity"),
            "val_profit_margins": info.get("profitMargins"),
            "val_revenue_growth": info.get("revenueGrowth"),
            "val_peg_ratio": info.get("pegRatio"),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed valutation for %s: %s", ticker, e)
        return {}


def build_historical_valutation(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Costruisce feature di valutazione. Snapshot propagato all'indietro."""
    df = pd.DataFrame(index=ohlcv.index)
    val = fetch_valutation(ticker)
    if val:
        for col, v in val.items():
            df[col] = v if v is not None else np.nan
    df = df.ffill().bfill()
    # Drop entirely-NaN columns (yfinance may return None for many keys)
    df = df.loc[:, df.notna().any()]
    return df


def get_valutation_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return valutation feature columns present in ``df``."""
    return [c for c in df.columns if c.startswith("val_")]
