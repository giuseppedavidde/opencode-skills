"""Backtest performance metrics.

Pure functions operating on a daily-return Series. All ratios are
annualised assuming 252 trading days unless the caller overrides.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils.helpers import calculate_sharpe, calculate_sortino


def calculate_metrics(returns: pd.Series, periods: int = 252) -> dict:
    """Compute a full performance report from a daily return Series.

    Parameters
    ----------
    returns:
        Daily (or generic-period) strategy returns.
    periods:
        Periods per year (252 for daily).

    Returns
    -------
    dict
        Sharpe, Sortino, max drawdown, Calmar, win rate, profit factor,
        avg win / avg loss, number of trades (non-zero return periods).
    """
    r = returns.dropna().astype(float)
    if r.empty:
        return {
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "n_trades": 0,
            "annual_return": 0.0,
            "annual_vol": 0.0,
        }

    ann_ret = float(np.mean(r) * periods)
    ann_vol = float(np.std(r, ddof=1) * np.sqrt(periods))
    sharpe = calculate_sharpe(r, periods=periods)
    sortino = calculate_sortino(r, periods=periods)

    cum = (1.0 + r).cumprod()
    running_max = cum.cummax()
    drawdown = (cum - running_max) / running_max
    max_dd = float(drawdown.min())

    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0

    wins = r[r > 0]
    losses = r[r < 0]
    win_rate = float(wins.size / (wins.size + losses.size)) if (wins.size + losses.size) else 0.0
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(losses.mean()) if losses.size else 0.0

    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "n_trades": int(r[r != 0].size),
        "annual_return": ann_ret,
        "annual_vol": ann_vol,
    }