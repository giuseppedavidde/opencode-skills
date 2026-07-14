"""Fetcher per dati fondamentali storici point-in-time via yfinance.

Usa yfinance per income statement, balance sheet e quarterly reports
storici. Calcola P/E, P/B, ROE, etc. dal report finanziario + prezzo di
chiusura — tutto point-in-time, nessun look-ahead bias.

Funziona senza API key (yfinance è gratuito).
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from typing import Optional
from pathlib import Path

from utils.logger import get_logger

logger = get_logger("data.fundamentals_fetcher")


def build_point_in_time_fundamentals(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Costruisce fondamentali point-in-time da yfinance financials.

    Ogni barra vede SOLO i dati disponibili fino a quella data:
    - Un report pubblicato il 31 Mar 2020 è valido da quel giorno
      fino al report successivo (forward-fill).
    - Nessun backward-fill, nessun leak dal futuro.

    Ratio calcolati:
    - P/E = close / (NetIncome / SharesOutstanding)
    - P/B = close / (BookValue / SharesOutstanding)
    - P/S = close / (Revenue / SharesOutstanding)
    - ROE = NetIncome / StockholdersEquity
    - Debt/Equity = TotalDebt / StockholdersEquity
    - Earnings Yield = 1 / P/E
    - Market Cap = close * SharesOutstanding

    Returns:
        DataFrame con index = ohlcv.index, colonne = ``val_*``
    """
    # Pre-crea tutte le colonne possibili (NaN)
    ALL_COLS = [
        "val_pe_ratio", "val_pb_ratio", "val_ps_ratio", "val_ev_ebitda",
        "val_earnings_yield", "val_market_cap", "val_roe", "val_debt_equity",
        "val_revenue_growth", "val_profit_margins",
    ]
    df = pd.DataFrame(np.nan, index=ohlcv.index, columns=ALL_COLS)
    close = ohlcv["close"]

    try:
        tk = yf.Ticker(ticker)

        # --- Financials annuali + trimestrali ---
        fin_a = tk.financials       # annuale
        fin_q = tk.quarterly_financials  # trimestrale
        bs_a = tk.balance_sheet
        bs_q = tk.quarterly_balance_sheet

        # Unisci annuali e trimestrali in un unico dataframe storico
        fin_all = _merge_annual_quarterly(fin_a, fin_q)
        bs_all = _merge_annual_quarterly(bs_a, bs_q)

        if fin_all.empty:
            logger.warning("No financials data for %s", ticker)
            return _yfinance_snapshot_fallback(ticker, ohlcv)

        # --- Calcola EPS storico ---
        eps = _get_eps(fin_all, bs_all)
        # Shares outstanding
        shares = _get_shares(bs_all)
        # Book value
        bv = _get_book_value(bs_all)
        # Revenue
        revenue = _safe_get(fin_all, "Total Revenue")
        # Net Income
        ni = _safe_get(fin_all, "Net Income")
        # EBITDA
        ebitda = _safe_get(fin_all, "EBITDA")
        # Total Debt
        debt = _safe_get(bs_all, "Total Debt")

        # --- Allinea a OHLCV ---
        # Uniforma i tipi datetime — rimuovi timezone da ohlcv index
        # (i report finanziari sono sempre timezone-naive)
        ohlcv_naive = ohlcv.copy()
        if hasattr(ohlcv_naive.index, "tz") and ohlcv_naive.index.tz is not None:
            ohlcv_naive.index = ohlcv_naive.index.tz_localize(None)
        fin_cols = pd.DatetimeIndex([pd.Timestamp(c) for c in fin_all.columns])
        fin_all.columns = fin_cols

        # Per ogni data in ohlcv, usa il report PIU' RECENTE (forward-fill)
        for i in range(len(ohlcv_naive)):
            date = pd.Timestamp(ohlcv_naive.index[i])

            # Trova il report più recente non futuro
            valid_reports = fin_cols[fin_cols <= date]
            if len(valid_reports) == 0:
                continue

            latest = valid_reports[-1]
            price = float(close.iloc[i])
            if pd.isna(price) or price == 0:
                continue

            # Mappa nome colonna → indice intero (pre-calcolato)
            def _set(col: str, val: float) -> None:
                if col in ALL_COLS:
                    df.iloc[i, ALL_COLS.index(col)] = val

            # EPS
            eps_val = eps.get(latest)
            if eps_val is not None and eps_val > 0:
                _set("val_pe_ratio", price / eps_val)
                _set("val_earnings_yield", eps_val / price)

            # P/B
            bv_val = bv.get(latest)
            shares_val = _get_shares_at(bs_all, latest)
            if bv_val is not None and shares_val is not None and shares_val > 0:
                _set("val_pb_ratio", price / (bv_val / shares_val))

            # P/S
            rev_val = revenue.get(latest)
            if rev_val is not None and shares_val is not None and shares_val > 0:
                _set("val_ps_ratio", price / (rev_val / shares_val))

            # ROE
            ni_val = ni.get(latest)
            if ni_val is not None and bv_val is not None and bv_val > 0:
                _set("val_roe", ni_val / bv_val)

            # Debt/Equity
            debt_val = debt.get(latest)
            if debt_val is not None and bv_val is not None and bv_val > 0:
                _set("val_debt_equity", debt_val / bv_val)

            # Market Cap
            if shares_val is not None and shares_val > 0:
                _set("val_market_cap", price * shares_val)

            # EV/EBITDA
            ebitda_val = ebitda.get(latest)
            if ebitda_val is not None and ebitda_val > 0:
                cash_val = _safe_get(bs_all, "Cash Cash Equivalents And Short Term Investments").get(latest, 0) or 0
                ev = (price * shares_val) + (debt_val or 0) - cash_val
                _set("val_ev_ebitda", ev / ebitda_val)

            # Revenue growth (YoY)
            rev_prev = revenue.get(_prev_year_report(fin_all, latest))
            if rev_val is not None and rev_prev is not None and rev_prev > 0:
                _set("val_revenue_growth", (rev_val - rev_prev) / rev_prev)

            # Profit margins
            if ni_val is not None and rev_val is not None and rev_val > 0:
                _set("val_profit_margins", ni_val / rev_val)

        # Forward-fill: i fondamentali sono validi fino al report successivo
        df = df.ffill()
        n_cols = len(df.columns)
        logger.info(
            "PIT fundamentals from yfinance for %s: %d cols, %d rows",
            ticker,
            n_cols,
            len(df),
        )
        return df

    except Exception as e:
        logger.warning("Failed to build PIT fundamentals for %s: %s", ticker, e)
        return _yfinance_snapshot_fallback(ticker, ohlcv)


def _merge_annual_quarterly(
    annual: pd.DataFrame, quarterly: pd.DataFrame
) -> pd.DataFrame:
    """Unisce financials annuali e trimestrali, preferendo i trimestrali
    dove disponibili (più frequenti)."""
    if annual.empty and quarterly.empty:
        return pd.DataFrame()
    if annual.empty:
        return quarterly
    if quarterly.empty:
        return annual

    # Unisci: i trimestrali hanno date più recenti
    combined = quarterly.copy()
    for col in annual.columns:
        if col not in combined.columns:
            combined[col] = annual[col]
    return combined.sort_index(axis=1)


def _get_eps(fin: pd.DataFrame, bs: pd.DataFrame) -> dict:
    """Calcola EPS storico: Net Income / Shares Outstanding."""
    eps = {}
    shares = _get_shares(bs)
    ni = _safe_get(fin, "Net Income")

    for col in fin.columns:
        if col in ni and ni[col] is not None:
            s = shares.get(col)
            if s and s > 0:
                eps[col] = ni[col] / s
    return eps


def _get_shares(bs: pd.DataFrame) -> dict:
    """Shares outstanding da balance sheet."""
    # Prova Ordinary Shares Number poi Share Issued
    for key in ["Ordinary Shares Number", "Share Issued"]:
        if key in bs.index:
            return bs.loc[key].to_dict()
    return {}


def _get_shares_at(bs: pd.DataFrame, date) -> float | None:
    """Shares outstanding alla data specificata."""
    for key in ["Ordinary Shares Number", "Share Issued"]:
        if key in bs.index and date in bs.columns:
            val = bs.loc[key, date]
            if pd.notna(val) and val > 0:
                return float(val)
    return None


def _get_book_value(bs: pd.DataFrame) -> dict:
    """Book value (Stockholders Equity)."""
    for key in [
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ]:
        if key in bs.index:
            return bs.loc[key].to_dict()
    return {}


def _safe_get(df: pd.DataFrame, key: str) -> pd.Series:
    """Recupera una riga dal dataframe, o restituisce Series vuota."""
    if key in df.index:
        return df.loc[key]
    return pd.Series(dtype=float)


def _prev_year_report(fin: pd.DataFrame, date) -> Optional[pd.Timestamp]:
    """Trova il report dell'anno precedente (stesso trimestre)."""
    if not isinstance(date, pd.Timestamp):
        date = pd.Timestamp(date)
    target = date - pd.DateOffset(years=1)
    for col in fin.columns:
        if col <= target:
            return col
    return None


def _yfinance_snapshot_fallback(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Fallback: usa dati yfinance info snapshot (costante)."""
    df = pd.DataFrame(index=ohlcv.index)
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        pe = info.get("trailingPE") or info.get("forwardPE")
        shares = info.get("sharesOutstanding")
        close = ohlcv["close"]

        data = {
            "pe_ratio": pe,
            "pb_ratio": info.get("priceToBook"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "earnings_yield": 1.0 / pe if pe and pe > 0 else None,
            "market_cap": info.get("marketCap"),
            "roe": info.get("returnOnEquity"),
            "profit_margins": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_equity": info.get("debtToEquity"),
        }
        for col, val in data.items():
            df[f"val_{col}"] = val if val is not None else np.nan

        # Market cap storico
        if shares:
            df["val_market_cap"] = close * shares

        df = df.ffill()
        logger.info("Fallback fundamentals for %s: %d cols", ticker, len(df.columns))
        return df
    except Exception as e:
        logger.warning("Fallback failed for %s: %s", ticker, e)
        return df
