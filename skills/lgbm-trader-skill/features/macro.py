"""Macro-context features derived from the macro DataFrame.

The macro frame (see :func:`data.fetcher.fetch_macro`) carries columns
``vix``, ``dxy``, ``yield_10y``, ``nasdaq``, ``shy`` (any of them can be
missing). Features are prefixed with ``macro_`` so they cannot collide with
the OHLCV feature families.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


def add_macro_features(
    ohlcv: pd.DataFrame,
    macro: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach macro features to ``ohlcv`` (a copy is returned).

    ``macro`` is reindexed onto the OHLCV index (forward filling missing
    macro dates) before the features are computed. If ``macro`` is ``None``
    or empty, the OHLCV frame is returned untouched.
    """
    out = ohlcv.copy()
    if macro is None or macro.empty:
        logger.info("No macro frame provided, skipping macro features")
        return out

    macro = macro.reindex(out.index).ffill()

    if "vix" in macro.columns:
        out["macro_vix_level"] = macro["vix"]
        out["macro_vix_change_5d"] = macro["vix"].pct_change(5) * 100.0
        out["macro_vix_percentile_252d"] = macro["vix"].rolling(252).rank(pct=True)
        out["macro_vix_ma50_ratio"] = macro["vix"] / macro["vix"].rolling(50).mean().replace(0.0, np.nan)
        out["macro_risk_regime"] = macro["vix"].apply(_risk_regime)
    else:
        out["macro_risk_regime"] = 1

    if "dxy" in macro.columns:
        out["macro_dxy_level"] = macro["dxy"]
        out["macro_dxy_change_5d"] = macro["dxy"].pct_change(5) * 100.0

    if "yield_10y" in macro.columns:
        out["macro_yield_10y"] = macro["yield_10y"]

    if "yield_10y" in macro.columns and "shy" in macro.columns:
        out["macro_yield_spread_10y_2y"] = macro["yield_10y"] - macro["shy"]

    return out


def _risk_regime(vix: float) -> int:
    """Discretise VIX into a 0-3 risk regime classifier."""
    if not np.isfinite(vix):
        return 1
    if vix < 15.0:
        return 0  # calm
    if vix < 25.0:
        return 1  # normal
    if vix < 35.0:
        return 2  # stress
    return 3  # crisis


FEATURE_DESCRIPTIONS: dict[str, str] = {
    "macro_vix_level": "VIX spot level",
    "macro_vix_change_5d": "VIX 5-day % change",
    "macro_vix_percentile_252d": "VIX 1y percentile",
    "macro_vix_ma50_ratio": "VIX / MA50 (mean reversion signal)",
    "macro_risk_regime": "Discrete risk regime 0=calm,1=normal,2=stress,3=crisis",
    "macro_dxy_level": "Dollar index level",
    "macro_dxy_change_5d": "DXY 5-day % change",
    "macro_yield_10y": "10y Treasury yield",
    "macro_yield_spread_10y_2y": "10y-2y yield spread proxy",
}


def feature_columns() -> list[str]:
    """Ordered list of macro feature names."""
    return list(FEATURE_DESCRIPTIONS.keys())