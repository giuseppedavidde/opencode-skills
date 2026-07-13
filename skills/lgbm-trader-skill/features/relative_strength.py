"""Relative strength — forza relativa vs SPY e settore."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from utils.logger import get_logger

logger = get_logger("features.relative_strength")

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "rs_vs_spy_5d": "Return vs SPY (5d)",
    "rs_vs_spy_21d": "Return vs SPY (21d)",
    "rs_vs_spy_63d": "Return vs SPY (63d)",
    "rs_vs_sector_5d": "Return vs settore (5d)",
    "rs_vs_sector_21d": "Return vs settore (21d)",
    "rs_vs_sector_63d": "Return vs settore (63d)",
    "rs_beta_63d": "Beta vs SPY (63d rolling)",
    "rs_corr_spy_63d": "Correlation vs SPY (63d)",
    "rs_vs_spy_percentile_252d": "Percentile RS vs SPY su 252gg",
}

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financial",
    "XLV": "Health Care",
    "XLY": "Consumer Cyclical",
    "XLP": "Consumer Defensive",
    "XLE": "Energy",
    "XLI": "Industrial",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication",
}


def fetch_sector_etf(ticker: str) -> str | None:
    """Determina l'ETF settoriale per un ticker."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        sector = (info.get("sector") or "") + " " + (info.get("industry") or "")
        for etf, name in SECTOR_ETFS.items():
            if name.lower() in sector.lower():
                return etf
        tech_kw = ["software", "semiconductor", "technology", "internet", "computer", "electronics"]
        fin_kw = ["bank", "insurance", "finance", "investment"]
        if any(k in sector.lower() for k in tech_kw):
            return "XLK"
        if any(k in sector.lower() for k in fin_kw):
            return "XLF"
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed sector lookup for %s: %s", ticker, e)
        return None


def build_relative_strength_features(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """RS vs SPY e settore a 5/21/63gg + beta + correlazione."""
    df = pd.DataFrame(index=ohlcv.index)
    try:
        spy = yf.download("SPY", start=ohlcv.index[0], end=ohlcv.index[-1], progress=False)
        spy_c = spy["Close"].reindex(ohlcv.index)
        if isinstance(spy_c, pd.DataFrame):
            spy_c = spy_c.iloc[:, 0]
    except Exception:  # noqa: BLE001
        spy_c = None

    sector_etf = fetch_sector_etf(ticker)
    sec_c = None
    if sector_etf:
        try:
            sec = yf.download(sector_etf, start=ohlcv.index[0], end=ohlcv.index[-1], progress=False)
            sec_c = sec["Close"].reindex(ohlcv.index)
            if isinstance(sec_c, pd.DataFrame):
                sec_c = sec_c.iloc[:, 0]
        except Exception:  # noqa: BLE001
            pass

    tc = ohlcv["close"]
    tr = tc.pct_change()
    if spy_c is not None:
        sr = spy_c.pct_change()
        for d in [5, 21, 63]:
            df[f"rs_vs_spy_{d}d"] = tr.rolling(d).sum() - sr.rolling(d).sum()
        cov = tr.rolling(63).cov(sr)
        mvar = sr.rolling(63).var()
        df["rs_beta_63d"] = cov / mvar.replace(0, np.nan)
        df["rs_corr_spy_63d"] = tr.rolling(63).corr(sr)
        if "rs_vs_spy_21d" in df.columns:
            df["rs_vs_spy_percentile_252d"] = df["rs_vs_spy_21d"].rank(pct=True)
    if sec_c is not None:
        secr = sec_c.pct_change()
        for d in [5, 21, 63]:
            df[f"rs_vs_sector_{d}d"] = tr.rolling(d).sum() - secr.rolling(d).sum()
    # Drop columns entirely NaN so they cannot poison the downstream dropna
    df = df.loc[:, df.notna().any()]
    return df


def get_relative_strength_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return relative-strength feature columns present in ``df``."""
    return [c for c in df.columns if c.startswith("rs_")]
