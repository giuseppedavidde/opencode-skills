"""Data layer: fetching and preprocessing OHLCV + macro data."""

from data.fetcher import fetch_ohlcv, fetch_macro, fetch_ohlcv_batch
from data.preprocessor import (
    align_dates,
    handle_missing,
    add_target,
    triple_barrier_label,
)

__all__ = [
    "fetch_ohlcv",
    "fetch_ohlcv_batch",
    "fetch_macro",
    "align_dates",
    "handle_missing",
    "add_target",
    "triple_barrier_label",
]