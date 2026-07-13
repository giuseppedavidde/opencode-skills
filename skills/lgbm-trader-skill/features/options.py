"""Options-based features per il modello opzioni decorrelato.

Vengono aggiunte alla pipeline feature principale e usate anche come feature
set separato per il modello ``options`` nello stacking ensemble. Tutte le
colonne sono prefissate con ``opt_`` per evitare collisioni con le famiglie
esistenti (``mom_``, ``trend_``, ``vol_``, ``prc_``, ``ms_``, ``macro_``).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger("features.options")


FEATURE_DESCRIPTIONS: dict[str, str] = {
    "opt_iv_est": "Estimated implied volatility (RV * 1.2 + 0.05)",
    "opt_rv_21d": "Realized volatility 21d (annualized)",
    "opt_vrp": "Volatility risk premium (IV - RV)",
    "opt_vrp_zscore": "VRP z-score over 63d",
    "opt_iv_rank_252d": "IV percentile rank over 252d",
    "opt_iv_percentile_252d": "IV percentile (rolling 252d)",
    "opt_iv_skew_est": "Estimated IV skew (return skewness 63d proxy)",
    "opt_vol_regime": "Vol regime: 0=low, 1=normal, 2=high (from IV rank)",
    "opt_iv_atm": "Live ATM IV (snapshot, forward-filled)",
    "opt_pcr_vol": "Live put/call volume ratio (snapshot, ffilled)",
    "opt_pcr_oi": "Live put/call open-interest ratio (snapshot, ffilled)",
    "opt_iv_skew": "Live IV skew (call IV - put IV, snapshot, ffilled)",
    "opt_vrp_real": "Live VRP (IV_ATM - RV snapshot, ffilled)",
}


def add_options_features(
    df: pd.DataFrame,
    options_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Aggiunge feature opzioni al DataFrame principale.

    Parameters
    ----------
    df:
        DataFrame OHLCV + feature esistenti.
    options_df:
        DataFrame con feature opzioni (da
        :func:`data.options_fetcher.build_historical_options_features`).
        Se ``None`` le feature vengono calcolate internamente da OHLCV.

    Returns
    -------
    pandas.DataFrame
        ``df`` con feature opzioni aggiunte (prefisso ``opt_``).
    """
    out = df.copy()

    if options_df is not None and not options_df.empty:
        for col in options_df.columns:
            if col.startswith("opt_"):
                out[col] = options_df[col].reindex(out.index)
    else:
        logger.info("No pre-computed options frame, computing from OHLCV")
        close = out["close"] if "close" in out.columns else out["Close"]
        returns = close.pct_change()
        rv_21d = returns.rolling(21).std() * np.sqrt(252)
        iv_est = rv_21d * 1.2 + 0.05
        vrp = iv_est - rv_21d

        out["opt_rv_21d"] = rv_21d
        out["opt_iv_est"] = iv_est
        out["opt_vrp"] = vrp
        out["opt_iv_rank_252d"] = iv_est.rolling(252).rank(pct=True)
        out["opt_iv_percentile_252d"] = out["opt_iv_rank_252d"]

    # Feature derivate (calcolate sempre, idempotenti)
    if "opt_vrp" in out.columns:
        std = out["opt_vrp"].rolling(63).std().replace(0.0, np.nan)
        out["opt_vrp_zscore"] = (
            out["opt_vrp"] - out["opt_vrp"].rolling(63).mean()
        ) / std

    if "opt_iv_rank_252d" in out.columns:
        ir = out["opt_iv_rank_252d"]
        out["opt_vol_regime"] = np.where(ir < 0.25, 0, np.where(ir < 0.75, 1, 2))

    close = out["close"] if "close" in out.columns else out["Close"]
    out["opt_iv_skew_est"] = close.pct_change().rolling(63).skew()

    n_opt = len(get_options_feature_columns(out))
    logger.info("Options features attached: %d columns", n_opt)
    return out


def get_options_feature_columns(df: pd.DataFrame) -> list[str]:
    """Restituisce le colonne feature opzioni presenti in ``df``."""
    return [c for c in df.columns if c.startswith("opt_")]


def get_options_feature_names() -> list[str]:
    """Restituisce i nomi di tutte le feature opzioni conosciute."""
    return list(FEATURE_DESCRIPTIONS.keys())


def feature_columns() -> list[str]:
    """Alias per coerenza con :mod:`features.macro`."""
    return get_options_feature_names()