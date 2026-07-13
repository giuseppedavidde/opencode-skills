"""Data preprocessing: alignment, missing handling, and target labeling.

The target is built using the triple-barrier method (Lopez de Prado,
"Advances in Financial Machine Learning", ch. 3) with an ATR-based
vertical barrier at the prediction horizon.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


def align_dates(ohlcv: pd.DataFrame, macro: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Align OHLCV and macro frames on a common trading-day index.

    Reindexes the macro frame onto the OHLCV index (forward filling macro
    which is typically lower-frequency), then drops rows where OHLCV is
    missing. Both returned frames share the same index.
    """
    if ohlcv.empty:
        return ohlcv, macro
    common_index = ohlcv.index
    if not macro.empty:
        macro_aligned = macro.reindex(common_index).ffill()
    else:
        macro_aligned = macro
    return ohlcv.loc[common_index], macro_aligned.loc[common_index] if not macro_aligned.empty else macro_aligned


def handle_missing(df: pd.DataFrame, method: str = "ffill") -> pd.DataFrame:
    """Handle missing values via forward fill, then drop any remaining NaNs.

    Parameters
    ----------
    method:
        ``"ffill"`` (default) or ``"drop"``. ``"ffill"`` forward-fills then
        drops residual NaNs to avoid leakage.
    """
    if df.empty:
        return df
    out = df.copy()
    if method == "ffill":
        out = out.ffill()
    out = out.dropna()
    return out


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / window, adjust=False).mean()
    return atr


def triple_barrier_label(
    df: pd.DataFrame,
    horizon: int = 5,
    atr_multiplier: float = 2.0,
    pt_sl: Optional[Tuple[float, float]] = (0.05, 0.05),
) -> pd.Series:
    """Compute triple-barrier labels aligned to each bar's entry.

    For each bar ``i`` we look ahead ``horizon`` bars; if price first hits
    the upper barrier (``pt_sl[0] * ATR * atr_multiplier`` above close) we
    label ``+1``; if it hits the lower barrier first we label ``-1``;
    otherwise (vertical barrier reached) we label the sign of the realized
    return over the horizon. The returned series is continuous, clipped to
    ``[-1, 1]`` and usable as a regression target.

    Parameters
    ----------
    df:
        DataFrame with columns ``high``, ``low``, ``close`` and an ATR
        column named ``atr`` (computed via :func:`compute_atr` if missing).
    horizon:
        Number of bars ahead for the vertical barrier.
    atr_multiplier:
        Scales the ATR to set barrier widths.
    pt_sl:
        ``(profit_take_frac, stop_loss_frac)`` as fractions of
        ``atr * atr_multiplier``.
    """
    if df.empty:
        return pd.Series(dtype=float, name="target")

    work = df.copy()
    if "atr" not in work.columns:
        work["atr"] = compute_atr(work["high"], work["low"], work["close"])

    high = work["high"].to_numpy()
    low = work["low"].to_numpy()
    close = work["close"].to_numpy()
    atr = work["atr"].to_numpy()
    n = len(work)

    pt_frac, sl_frac = pt_sl if pt_sl is not None else (0.05, 0.05)
    labels = np.full(n, np.nan)

    for i in range(n - horizon):
        entry = close[i]
        a = atr[i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(entry) or entry <= 0:
            continue
        upper = entry + pt_frac * a * atr_multiplier
        lower = entry - sl_frac * a * atr_multiplier
        out_label = 0.0
        for j in range(i + 1, min(i + 1 + horizon, n)):
            if high[j] >= upper:
                out_label = 1.0
                break
            if low[j] <= lower:
                out_label = -1.0
                break
        if out_label == 0.0:
            ret = (close[i + horizon] - entry) / entry
            out_label = float(np.tanh(ret * 10.0))
        labels[i] = out_label

    return pd.Series(labels, index=work.index, name="target")


def add_target(
    df: pd.DataFrame,
    horizon: int = 5,
    atr_multiplier: float = 2.0,
    pt_sl: Optional[Tuple[float, float]] = (0.05, 0.05),
) -> pd.DataFrame:
    """Append a ``target`` column to the OHLCV frame using triple-barrier."""
    target = triple_barrier_label(df, horizon=horizon, atr_multiplier=atr_multiplier, pt_sl=pt_sl)
    out = df.copy()
    out["target"] = target
    n_valid = out["target"].notna().sum()
    logger.info("Target built: %d/%d valid labels", n_valid, len(out))
    return out