"""Fetcher per dati fondamentali storici point-in-time.

Fonti (in ordine di preferenza):
1. FinancialModelingPrep (FMP) - API key opzionale, endpoint /stable/
2. yfinance financials - gratuito, sempre disponibile (fallback)

Calcola P/E, P/B, ROE, etc. dal report finanziario + prezzo di chiusura.
Tutto point-in-time: nessun look-ahead bias.
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from pathlib import Path

from utils.logger import get_logger

logger = get_logger("data.fundamentals_fetcher")

FMP_BASE = "https://financialmodelingprep.com/stable"

ALL_COLS = [
    "val_pe_ratio", "val_pb_ratio", "val_ps_ratio", "val_ev_ebitda",
    "val_earnings_yield", "val_market_cap", "val_roe", "val_debt_equity",
    "val_revenue_growth", "val_profit_margins",
]

API_KEY_PATH = Path(__file__).resolve().parents[2] / "config" / "fmp_api_key.txt"
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_api_key() -> str | None:
    if API_KEY_PATH.exists():
        for line in API_KEY_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line != "YOUR_FMP_API_KEY_HERE":
                return line
    if DOTENV_PATH.exists():
        for line in DOTENV_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("FMP_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("FMP_API_KEY")


# ------------------------------------------------------------------- #
#  FMP (preferred)
# ------------------------------------------------------------------- #
def _fmp_get(endpoint: str, symbol: str) -> list:
    key = _load_api_key()
    if not key:
        return []
    try:
        r = requests.get(
            f"{FMP_BASE}/{endpoint}",
            params={"symbol": symbol, "apikey": key},
            timeout=15,
        )
        data = r.json()
        if isinstance(data, dict) and "Error Message" in str(data):
            return []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _build_pit_from_fmp(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame | None:
    """Tenta di costruire fondamentali point-in-time da FMP."""
    if not _load_api_key():
        return None

    ratios = _fmp_get("ratios", ticker)
    metrics = _fmp_get("key-metrics", ticker)
    if not ratios and not metrics:
        return None

    records: dict[str, dict] = {}
    for entry in ratios + metrics:
        date = entry.get("date")
        if not date:
            continue
        rec = records.setdefault(date, {})
        for k, v in entry.items():
            if k in ("symbol", "date") or v is None:
                continue
            rec[k] = v

    if not records:
        return None

    df_fmp = pd.DataFrame.from_dict(records, orient="index")
    df_fmp.index = pd.to_datetime(list(df_fmp.index)).tz_localize(None)
    df_fmp = df_fmp.sort_index()

    df = pd.DataFrame(np.nan, index=ohlcv.index, columns=ALL_COLS)
    close = ohlcv["close"]
    ohlcv_idx = _naive_idx(ohlcv)

    field_map = {
        "priceEarningsRatio": "val_pe_ratio",
        "priceToBookRatio": "val_pb_ratio",
        "priceToSalesRatio": "val_ps_ratio",
        "enterpriseValueOverEBITDA": "val_ev_ebitda",
        "returnOnEquity": "val_roe",
        "debtEquityRatio": "val_debt_equity",
        "profitMargin": "val_profit_margins",
        "revenueGrowth": "val_revenue_growth",
        "earningsYield": "val_earnings_yield",
    }

    for i in range(len(ohlcv)):
        date = ohlcv_idx[i]
        valid = df_fmp.index[df_fmp.index <= date]
        if len(valid) == 0:
            continue
        latest = valid[-1]
        price = float(close.iloc[i])
        if pd.isna(price) or price <= 0:
            continue
        row = df_fmp.loc[latest]
        for fmp_field, our_field in field_map.items():
            if fmp_field in row and pd.notna(row[fmp_field]):
                df.iloc[i, ALL_COLS.index(our_field)] = float(row[fmp_field])
        shares = row.get("commonStockSharesOutstanding")
        if shares and pd.notna(shares) and float(shares) > 0:
            df.iloc[i, ALL_COLS.index("val_market_cap")] = price * float(shares)

    df = df.ffill()
    logger.info("FMP PIT for %s: %d values", ticker, int(df.notna().sum().sum()))
    return df


# ------------------------------------------------------------------- #
#  yfinance (fallback)
# ------------------------------------------------------------------- #
def _naive_idx(df: pd.DataFrame) -> pd.Index:
    """Rimuove timezone dall'indice per confronti sicuri."""
    idx = df.index
    if hasattr(idx, "tz") and idx.tz is not None:
        return idx.tz_localize(None)
    return idx


def _merge_annual_quarterly(annual: pd.DataFrame, quarterly: pd.DataFrame) -> pd.DataFrame:
    if annual.empty and quarterly.empty:
        return pd.DataFrame()
    if annual.empty:
        return quarterly
    if quarterly.empty:
        return annual
    combined = quarterly.copy()
    for col in annual.columns:
        if col not in combined.columns:
            combined[col] = annual[col]
    return combined.sort_index(axis=1)


def _get_shares(bs: pd.DataFrame) -> dict:
    for key in ["Ordinary Shares Number", "Share Issued"]:
        if key in bs.index:
            return bs.loc[key].to_dict()
    return {}


def _get_book_value(bs: pd.DataFrame) -> dict:
    for key in ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"]:
        if key in bs.index:
            return bs.loc[key].to_dict()
    return {}


def _safe_get(df: pd.DataFrame, key: str) -> pd.Series:
    return df.loc[key] if key in df.index else pd.Series(dtype=float)


def _prev_year_report(fin: pd.DataFrame, date) -> pd.Timestamp | None:
    if not isinstance(date, pd.Timestamp):
        date = pd.Timestamp(date)
    target = date - pd.DateOffset(years=1)
    for col in fin.columns:
        if col <= target:
            return col
    return None


def _build_pit_from_yfinance(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame | None:
    """Costruisce fondamentali PIT da yfinance financials."""
    df = pd.DataFrame(np.nan, index=ohlcv.index, columns=ALL_COLS)
    close = ohlcv["close"]
    ohlcv_idx = _naive_idx(ohlcv)

    tk = yf.Ticker(ticker)
    fin_all = _merge_annual_quarterly(tk.financials, tk.quarterly_financials)
    bs_all = _merge_annual_quarterly(tk.balance_sheet, tk.quarterly_balance_sheet)

    if fin_all.empty:
        return None

    # Uniforma timezone degli indici dei report
    fin_all.columns = pd.to_datetime(fin_all.columns).tz_localize(None) if hasattr(fin_all.columns, "tz") and fin_all.columns.tz is not None else pd.to_datetime(fin_all.columns)
    bs_all.columns = pd.to_datetime(bs_all.columns).tz_localize(None) if hasattr(bs_all.columns, "tz") and bs_all.columns.tz is not None else pd.to_datetime(bs_all.columns)

    shares_dict = _get_shares(bs_all)
    bv_dict = _get_book_value(bs_all)
    revenue_s = _safe_get(fin_all, "Total Revenue")
    ni_s = _safe_get(fin_all, "Net Income")
    ebitda_s = _safe_get(fin_all, "EBITDA")
    debt_s = _safe_get(bs_all, "Total Debt")

    for i in range(len(ohlcv)):
        date = ohlcv_idx[i]
        valid = fin_all.columns[fin_all.columns <= date]
        if len(valid) == 0:
            continue
        latest = valid[-1]
        price = float(close.iloc[i])
        if pd.isna(price) or price <= 0:
            continue

        def _set(col: str, val: float) -> None:
            df.iloc[i, ALL_COLS.index(col)] = val

        # Shares
        share_val = None
        for k, v in shares_dict.items():
            if isinstance(k, pd.Timestamp) and k <= date:
                share_val = v
        if share_val is None:
            share_val = list(shares_dict.values())[-1] if shares_dict else None

        if share_val and float(share_val) > 0:
            shares_f = float(share_val)

            # EPS → P/E
            ni_val = ni_s.get(latest)
            if pd.notna(ni_val) and ni_val > 0:
                eps_val = ni_val / shares_f
                _set("val_pe_ratio", price / eps_val)
                _set("val_earnings_yield", eps_val / price)

            # P/S
            rev_val = revenue_s.get(latest)
            if pd.notna(rev_val) and rev_val > 0:
                _set("val_ps_ratio", price / (rev_val / shares_f))

            # Market Cap
            _set("val_market_cap", price * shares_f)

            # EV/EBITDA
            ebitda_val = ebitda_s.get(latest)
            if pd.notna(ebitda_val) and ebitda_val > 0:
                debt_val = debt_s.get(latest, 0) or 0
                _set("val_ev_ebitda", (price * shares_f + debt_val) / ebitda_val)

        # BV → P/B, ROE, Debt/Equity
        bv_val = None
        for k, v in bv_dict.items():
            if isinstance(k, pd.Timestamp) and k <= date:
                bv_val = v
        if bv_val is None:
            bv_val = list(bv_dict.values())[-1] if bv_dict else None

        if bv_val and float(bv_val) > 0 and share_val and float(share_val) > 0:
            bv_f = float(bv_val)
            _set("val_pb_ratio", price / (bv_f / float(share_val)))
            ni_val = ni_s.get(latest)
            if pd.notna(ni_val) and ni_val != 0:
                _set("val_roe", ni_val / bv_f)
            debt_val = debt_s.get(latest, 0) or 0
            if pd.notna(debt_val):
                _set("val_debt_equity", debt_val / bv_f)

        # Revenue growth
        rev_val = revenue_s.get(latest)
        prev = _prev_year_report(fin_all, latest)
        rev_prev = revenue_s.get(prev) if prev else None
        if rev_val is not None and rev_prev is not None and pd.notna(rev_val) and pd.notna(rev_prev) and rev_prev > 0:
            _set("val_revenue_growth", (rev_val - rev_prev) / rev_prev)

        # Profit margins
        ni_val = ni_s.get(latest)
        rev_val = revenue_s.get(latest)
        if ni_val is not None and rev_val is not None and pd.notna(ni_val) and pd.notna(rev_val) and rev_val > 0:
            _set("val_profit_margins", ni_val / rev_val)

    df = df.ffill()
    logger.info("yfinance PIT for %s: %d values", ticker, int(df.notna().sum().sum()))
    return df


# ------------------------------------------------------------------- #
#  Snapshot fallback
# ------------------------------------------------------------------- #
def _yfinance_snapshot_fallback(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Fallback estremo: yfinance info (dato costante)."""
    df = pd.DataFrame(np.nan, index=ohlcv.index, columns=ALL_COLS)
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        pe = info.get("trailingPE") or info.get("forwardPE")
        shares = info.get("sharesOutstanding")
        close = ohlcv["close"]

        if pe and pe > 0:
            df["val_pe_ratio"] = pe
            df["val_earnings_yield"] = 1.0 / pe
        if info.get("priceToBook"):
            df["val_pb_ratio"] = info["priceToBook"]
        if info.get("priceToSalesTrailing12Months"):
            df["val_ps_ratio"] = info["priceToSalesTrailing12Months"]
        if info.get("enterpriseToEbitda"):
            df["val_ev_ebitda"] = info["enterpriseToEbitda"]
        if info.get("returnOnEquity"):
            df["val_roe"] = info["returnOnEquity"]
        if info.get("profitMargins"):
            df["val_profit_margins"] = info["profitMargins"]
        if info.get("revenueGrowth"):
            df["val_revenue_growth"] = info["revenueGrowth"]
        if info.get("debtToEquity"):
            df["val_debt_equity"] = info["debtToEquity"]

        if shares:
            df["val_market_cap"] = close * shares

        df = df.ffill().bfill()
        logger.info("Snapshot fallback for %s: %d cols", ticker, len(df.columns))
    except Exception as e:
        logger.warning("Snapshot fallback failed: %s", e)
    return df


# ------------------------------------------------------------------- #
#  Entry point
# ------------------------------------------------------------------- #
def build_point_in_time_fundamentals(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Costruisce fondamentali point-in-time.

    Ordine: FMP → yfinance financials → yfinance snapshot.
    """
    # Prova FMP
    if _load_api_key():
        fmp_df = _build_pit_from_fmp(ticker, ohlcv)
        if fmp_df is not None and fmp_df.notna().sum().sum() > 0:
            return fmp_df

    # Fallback yfinance financials
    yf_df = _build_pit_from_yfinance(ticker, ohlcv)
    if yf_df is not None and yf_df.notna().sum().sum() > 0:
        return yf_df

    # Fallback estremo
    return _yfinance_snapshot_fallback(ticker, ohlcv)
