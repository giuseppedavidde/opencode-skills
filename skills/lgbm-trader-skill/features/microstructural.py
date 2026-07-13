"""Microstructural / bar-pattern features.

Binary or count features that describe the local structure of the price
series at the bar level (daily). All prefixed with ``ms_`` to keep them
clearly separated from the technical indicator family.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from features.technical import _normalize  # reuse the lowercase helper


def add_microstructure(df: pd.DataFrame) -> pd.DataFrame:
    """Append every microstructural flag to ``df``."""
    out = _normalize(df)
    out = add_nr7(out)
    out = add_nr4_inside(out)
    out = add_outside_inside_bars(out)
    out = add_hh_ll_counts(out)
    out = add_consecutive_direction(out)
    out = add_close_position(out)
    out = add_gap_flags(out)
    out = add_range_expansion(out)
    return out


# --------------------------------------------------------------------------- #
# Narrow range 7
# --------------------------------------------------------------------------- #
def add_nr7(out: pd.DataFrame) -> pd.DataFrame:
    """``ms_nr7_flag`` = 1 if today's range is the smallest of the last 7."""
    rng = out["high"] - out["low"]
    out["ms_nr7_flag"] = (rng == rng.rolling(7).min()).astype(int)
    return out


# --------------------------------------------------------------------------- #
# NR4 + inside day
# --------------------------------------------------------------------------- #
def add_nr4_inside(out: pd.DataFrame) -> pd.DataFrame:
    """``ms_id_nr4_flag`` = 1 if today is an inside day *and* narrow range 4."""
    high, low = out["high"], out["low"]
    rng = high - low
    is_nr4 = rng == rng.rolling(4).min()
    is_inside = (high <= high.shift(1)) & (low >= low.shift(1))
    out["ms_id_nr4_flag"] = (is_nr4 & is_inside).astype(int)
    return out


# --------------------------------------------------------------------------- #
# Outside / inside bars
# --------------------------------------------------------------------------- #
def add_outside_inside_bars(out: pd.DataFrame) -> pd.DataFrame:
    """``ms_outside_bar_flag`` and ``ms_inside_bar_flag``."""
    high, low = out["high"], out["low"]
    out["ms_outside_bar_flag"] = (
        (high > high.shift(1)) & (low < low.shift(1))
    ).astype(int)
    out["ms_inside_bar_flag"] = (
        (high <= high.shift(1)) & (low >= low.shift(1))
    ).astype(int)
    return out


# --------------------------------------------------------------------------- #
# Higher-highs / lower-lows counts
# --------------------------------------------------------------------------- #
def add_hh_ll_counts(out: pd.DataFrame) -> pd.DataFrame:
    """Count of new 20-bar higher highs / lower lows ending today."""
    high, low = out["high"], out["low"]
    hh = (high > high.shift(1)).rolling(20).sum()
    ll = (low < low.shift(1)).rolling(20).sum()
    out["ms_hh_count_20d"] = hh.fillna(0).astype(int)
    out["ms_ll_count_20d"] = ll.fillna(0).astype(int)
    return out


# --------------------------------------------------------------------------- #
# Consecutive up/down close days
# --------------------------------------------------------------------------- #
def add_consecutive_direction(out: pd.DataFrame) -> pd.DataFrame:
    """Length of the current run of up-closes / down-closes."""
    close = out["close"]
    up = (close > close.shift(1)).astype(int)
    down = (close < close.shift(1)).astype(int)

    out["ms_consecutive_up_days"] = _streak(up)
    out["ms_consecutive_down_days"] = _streak(down)
    return out


def _streak(flag: pd.Series) -> pd.Series:
    """Run-length encode the given 0/1 series (resets at every 0)."""
    grp = (flag != flag.shift(1)).cumsum()
    return flag.groupby(grp).cumsum().astype(int)


# --------------------------------------------------------------------------- #
# Close position within the bar range
# --------------------------------------------------------------------------- #
def add_close_position(out: pd.DataFrame) -> pd.DataFrame:
    """Where the close sits in today's range (0 = low, 1 = high)."""
    high, low, close = out["high"], out["low"], out["close"]
    rng = (high - low).replace(0.0, np.nan)
    out["ms_close_position_in_range"] = ((close - low) / rng).fillna(0.5)
    return out


# --------------------------------------------------------------------------- #
# Gap flags
# --------------------------------------------------------------------------- #
def add_gap_flags(out: pd.DataFrame) -> pd.DataFrame:
    """``ms_gap_up_flag`` / ``ms_gap_down_flag`` based on previous close."""
    close = out["close"]
    prev_close = close.shift(1)
    gap = (close - prev_close) / prev_close.replace(0.0, np.nan)
    out["ms_gap_up_flag"] = (gap > 0.01).astype(int)
    out["ms_gap_down_flag"] = (gap < -0.01).astype(int)
    return out


# --------------------------------------------------------------------------- #
# Range expansion
# --------------------------------------------------------------------------- #
def add_range_expansion(out: pd.DataFrame) -> pd.DataFrame:
    """``ms_range_expansion_flag`` = 1 if today's range > 1.5 * yesterday's."""
    rng = out["high"] - out["low"]
    out["ms_range_expansion_flag"] = (
        rng > (rng.shift(1) * 1.5)
    ).astype(int)
    return out


FEATURE_DESCRIPTIONS: dict[str, str] = {
    "ms_nr7_flag": "Narrow range 7 flag",
    "ms_id_nr4_flag": "Inside day + narrow range 4 flag",
    "ms_outside_bar_flag": "Outside bar flag",
    "ms_inside_bar_flag": "Inside bar flag",
    "ms_hh_count_20d": "Count of higher highs (20d)",
    "ms_ll_count_20d": "Count of lower lows (20d)",
    "ms_consecutive_up_days": "Streak of up-close days",
    "ms_consecutive_down_days": "Streak of down-close days",
    "ms_close_position_in_range": "Position of close within bar range (0-1)",
    "ms_gap_up_flag": "Gap up (>1%) flag",
    "ms_gap_down_flag": "Gap down (>1%) flag",
    "ms_range_expansion_flag": "Range > 1.5x prior range flag",
}


def feature_columns() -> list[str]:
    """Ordered list of microstructural feature names."""
    return list(FEATURE_DESCRIPTIONS.keys())