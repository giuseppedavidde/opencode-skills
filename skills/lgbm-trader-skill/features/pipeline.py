"""End-to-end feature engineering pipeline.

Concatenates technical, microstructural, (optionally) macro and
(optionally) options features, handles residual NaNs and returns a frame
ready to be fed to the model trainer.
"""

from __future__ import annotations

import pandas as pd

from features.macro import add_macro_features, FEATURE_DESCRIPTIONS as _MACRO
from features.microstructural import (
    add_microstructure,
    FEATURE_DESCRIPTIONS as _MS,
)
from features.options import add_options_features, FEATURE_DESCRIPTIONS as _OPT
from features.relative_strength import (
    build_relative_strength_features,
    FEATURE_DESCRIPTIONS as _RS,
)
from features.short_interest import (
    build_historical_short_interest,
    FEATURE_DESCRIPTIONS as _SI,
)
from features.technical import (
    add_all_technical,
    FEATURE_DESCRIPTIONS as _TECH,
)
from features.valutation import (
    build_historical_valutation,
    FEATURE_DESCRIPTIONS as _VAL,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# Aggregate description catalogue --------------------------------------------------
FEATURE_DESCRIPTIONS: dict[str, str] = {}
FEATURE_DESCRIPTIONS.update(_TECH)
FEATURE_DESCRIPTIONS.update(_MS)
FEATURE_DESCRIPTIONS.update(_MACRO)
FEATURE_DESCRIPTIONS.update(_OPT)
FEATURE_DESCRIPTIONS.update(_SI)
FEATURE_DESCRIPTIONS.update(_RS)
FEATURE_DESCRIPTIONS.update(_VAL)


def compute_all_features(
    ohlcv: pd.DataFrame,
    macro_df: pd.DataFrame | None = None,
    options_df: pd.DataFrame | None = None,
    ticker: str | None = None,
    drop_na: bool = True,
) -> pd.DataFrame:
    """Compute ALL features (technical + microstructural + macro + options).

    Parameters
    ----------
    ohlcv:
        OHLCV frame indexed by trading date.
    macro_df:
        Optional macro frame (VIX, DDX, ...). Forward-filled onto the
        OHLCV index.
    options_df:
        Optional options-derived frame (IV, VRP, PCR proxies, ...).
        Aligned onto the OHLCV index.
    ticker:
        Optional ticker symbol. If provided, decorrelated feature
        groups (short interest, relative strength vs SPY/sector,
        fundamental valutation) are fetched via yfinance.
    drop_na:
        Drop rows with residual NaNs (after the warm-up period) before
        returning. Defaults to ``True`` — recommended to train on a clean
        frame but the raw feature frame can be obtained with ``drop_na=False``.

    Returns
    -------
    pandas.DataFrame
        OHLCV columns plus every feature column, indexed by date.
    """
    if ohlcv is None or ohlcv.empty:
        logger.warning("Empty OHLCV frame, no features computed")
        return pd.DataFrame()

    out = add_all_technical(ohlcv)
    out = add_microstructure(out)
    out = add_macro_features(out, macro_df)
    out = add_options_features(out, options_df=options_df)

    # Short interest features -------------------------------------------------
    if ticker:
        logger.info("Building short interest features for %s", ticker)
        si_df = build_historical_short_interest(ticker, out)
        for col in si_df.columns:
            out[col] = si_df[col]

    # Relative strength features ---------------------------------------------
    if ticker:
        logger.info("Building relative strength features for %s", ticker)
        rs_df = build_relative_strength_features(ticker, out)
        for col in rs_df.columns:
            out[col] = rs_df[col]

    # Valutation features -----------------------------------------------------
    if ticker:
        logger.info("Building valutation features for %s", ticker)
        val_df = build_historical_valutation(ticker, out)
        for col in val_df.columns:
            out[col] = val_df[col]

    if drop_na:
        before = len(out)
        # ffill then drop residual NaNs (warm-up windows, lookahead-safe)
        out = out.ffill().dropna()
        logger.info(
            "Feature frame ready: %d rows kept (dropped %d for NaNs)",
            len(out),
            before - len(out),
        )
    return out


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return every feature column present in ``df`` (excludes OHLCV)."""
    ohlcv_cols = {"open", "high", "low", "close", "volume", "target", "target_cont", "atr"}
    return [c for c in df.columns if c not in ohlcv_cols]