"""Generic helper utilities for the LightGBM Trading System.

Contains performance metric calculations used across the backtest and signal
generation modules. All functions are pure and operate on numpy arrays or
pandas Series so they can be reused in any context.
"""

from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

ArrayLike = Union[np.ndarray, pd.Series]


def calculate_sharpe(returns: ArrayLike, periods: int = 252) -> float:
    """Annualized Sharpe ratio assuming zero risk-free rate.

    Parameters
    ----------
    returns:
        Periodic returns (e.g. daily).
    periods:
        Number of periods per year (252 for daily, 12 for monthly).
    """
    arr = _to_array(returns)
    if arr.size < 2:
        return 0.0
    std = np.std(arr, ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    mean = np.mean(arr)
    return float(mean / std * np.sqrt(periods))


def calculate_sortino(returns: ArrayLike, periods: int = 252) -> float:
    """Annualized Sortino ratio using downside deviation only."""
    arr = _to_array(returns)
    if arr.size < 2:
        return 0.0
    mean = np.mean(arr)
    downside = arr[arr < 0]
    if downside.size == 0:
        return 0.0
    dd_std = np.std(downside, ddof=1)
    if dd_std == 0 or np.isnan(dd_std):
        return 0.0
    return float(mean / dd_std * np.sqrt(periods))


def calculate_max_drawdown(cum_returns: ArrayLike) -> float:
    """Maximum drawdown of a cumulative return series (as a negative fraction).

    The input is interpreted as a cumulative equity curve (starting > 0).
    Returns the worst peak-to-trough loss, e.g. -0.35 for a 35% drawdown.
    """
    arr = _to_array(cum_returns)
    if arr.size < 2:
        return 0.0
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    worst = np.min(drawdowns)
    if np.isnan(worst):
        return 0.0
    return float(worst)


def _to_array(x: ArrayLike) -> np.ndarray:
    if isinstance(x, pd.Series):
        return x.dropna().to_numpy(dtype=float)
    return np.asarray(x, dtype=float)


def annualized_volatility(returns: ArrayLike, periods: int = 252) -> float:
    """Annualized volatility of returns."""
    arr = _to_array(returns)
    if arr.size < 2:
        return 0.0
    return float(np.std(arr, ddof=1) * np.sqrt(periods))


def hit_rate(returns: ArrayLike) -> float:
    """Fraction of positive return periods."""
    arr = _to_array(returns)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr > 0))