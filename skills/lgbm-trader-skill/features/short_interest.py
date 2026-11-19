"""Short interest features — completamente decorrelate dal prezzo."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from utils.logger import get_logger

logger = get_logger("features.short_interest")

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "si_short_ratio": "Short ratio (short volume / avg volume)",
    "si_short_pct_float": "Short % of float",
    "si_shares_outstanding": "Shares outstanding (billions)",
    "si_short_interest": "Short interest (shares)",
    "si_days_to_cover": "Days to cover (short interest / avg volume)",
    "si_squeeze_score": "Squeeze score composito (short ratio x days to cover / 100)",
}


def fetch_short_interest(ticker: str) -> dict:
    """Fetcha short interest da yfinance info."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        si = {
            "si_short_ratio": info.get("shortRatio"),
            "si_short_pct_float": info.get("shortPercentOfFloat"),
            "si_shares_outstanding": info.get("sharesOutstanding"),
            "si_short_interest": info.get("sharesShort"),
            "si_days_to_cover": info.get("shortRatio"),
        }
        sr = si["si_short_ratio"]
        if sr is not None and sr > 0:
            si["si_squeeze_score"] = sr * sr / 100.0
        else:
            si["si_squeeze_score"] = None
        return si
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to fetch short interest for %s: %s", ticker, e)
        return {}


def build_historical_short_interest(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Costruisce feature short interest. Snapshot corrente propagato all'indietro."""
    df = pd.DataFrame(index=ohlcv.index)
    si = fetch_short_interest(ticker)
    if si:
        # Same rule as the point-in-time builder: a snapshot is not a history.
        for col, val in si.items():
            df[col] = np.nan
            if val is not None and len(df.index) > 0:
                df.iloc[-1, df.columns.get_loc(col)] = val
    else:
        avg_vol = ohlcv["volume"].rolling(21).mean()
        df["si_short_ratio"] = ohlcv["volume"] / avg_vol
        df["si_squeeze_score"] = df["si_short_ratio"] / 100.0
    # No fill: a single observation at the latest bar stays a single
    # observation. Backfilling it would recreate the look-ahead just removed.
    # Drop columns entirely NaN (yfinance occasionally returns None for some keys)
    df = df.loc[:, df.notna().any()]
    return df


def build_point_in_time_short_interest(ticker: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Short interest point-in-time.

    FMP non fornisce short interest storico gratis. Usiamo il dato più
    recente disponibile con forward-fill: in assenza di storico reale è
    comunque più onesto propagare in **avanti** dal primo giorno del
    dataset che all'indietro (no backward-fill).

    Per dati veramente storici:
    https://www.buyins.com/free.html o il file Nasdaq `ftxtab.txt`.

    Parameters:
        ticker: Simbolo.
        ohlcv: DataFrame OHLCV indicizzato per data.

    Returns:
        DataFrame indicizzato come ``ohlcv`` con colonne ``si_*``.
    """
    df = pd.DataFrame(index=ohlcv.index)
    si = fetch_short_interest(ticker)

    if si:
        # There is no free historical short-interest series. Writing today's
        # snapshot on every row would leak future information into the whole
        # training history and make the ``decorr`` group a flat constant.
        # Instead the values are published only on the last bar; older bars
        # stay NaN, so the trainer treats the group as missing history and the
        # live path fills it from the current snapshot.
        for col, val in si.items():
            if col.startswith("si_"):
                df[col] = np.nan
                if val is not None and len(df.index) > 0:
                    df.iloc[-1, df.columns.get_loc(col)] = val
    else:
        # Fallback: volume proxy
        avg_vol = ohlcv["volume"].rolling(21).mean()
        df["si_short_ratio"] = ohlcv["volume"] / avg_vol
        df["si_squeeze_score"] = df["si_short_ratio"] / 100.0

    df = df.loc[:, df.notna().any()]
    logger.info("Point-in-time short interest for %s: %d cols", ticker, len(df.columns))
    return df


def get_short_interest_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return short-interest feature columns present in ``df``."""
    return [c for c in df.columns if c.startswith("si_")]
