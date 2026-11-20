"""Base rates of forward returns, measured on the data (SIG-02).

A rule's hit rate means nothing without the hit rate of a random long over
the same horizon. :func:`forward_base_rate` measures, for one price series,
the share of positive total returns (``Adj Close``) over ``horizon`` bars
for every start date in the history.

Overlapping windows are NOT independent: with ``n`` bars and horizon ``h``
there are only about ``n / h`` independent windows. The block reports both
counts, and its Wilson 95% interval uses the non-overlapping sample (one
window every ``h`` bars, ending at the last bar). No p-value is computed:
a p-value from overlapping labels is not valid.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from trading_mcp.data.prices import adjusted_close

METHOD = (
    "share of positive {h}-bar total returns (Adj Close) over every start date; "
    "n_independent counts non-overlapping windows; the 95% interval is Wilson on the "
    "non-overlapping sample; no p-value (overlapping labels)"
)


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Wilson score interval of a proportion, or ``None`` when ``n`` is 0."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def forward_base_rate(hist: pd.DataFrame, horizon: int, *, symbol: str | None = None,
                      as_of: str | None = None) -> dict[str, Any]:
    """Base rate of positive ``horizon``-bar total returns of one series (see the module docstring)."""
    out: dict[str, Any] = {
        "symbol": symbol, "horizon_days": horizon, "share_positive": None, "median_return": None,
        "n_windows": 0, "n_independent": 0, "share_positive_independent": None, "ci95": None,
        "first_date": None, "last_date": None, "as_of": as_of,
    }
    series = adjusted_close(hist).dropna() if hist is not None else pd.Series(dtype=float)
    series = series[series > 0]
    if len(series) <= horizon:
        out["note"] = f"history too short: {len(series)} bars for a {horizon}-bar horizon"
        return out
    fwd = (series.shift(-horizon) / series - 1.0).dropna()
    independent = fwd.iloc[::-1].iloc[::horizon]
    wins = int((independent > 0).sum())
    interval = wilson_interval(wins, len(independent))
    out.update(
        share_positive=round(float((fwd > 0).mean()), 4),
        median_return=round(float(fwd.median()), 4),
        n_windows=int(len(fwd)),
        n_independent=int(len(independent)),
        share_positive_independent=round(wins / len(independent), 4),
        ci95=[round(interval[0], 4), round(interval[1], 4)] if interval else None,
        first_date=series.index[0].date().isoformat() if hasattr(series.index[0], "date") else str(series.index[0]),
        last_date=series.index[-1].date().isoformat() if hasattr(series.index[-1], "date") else str(series.index[-1]),
    )
    return out


def base_rate_block(
    ticker_hist: pd.DataFrame | None,
    benchmark_hist: pd.DataFrame | None,
    horizon: int,
    *,
    ticker: str,
    benchmark: str,
    ticker_as_of: str | None = None,
    benchmark_as_of: str | None = None,
) -> dict[str, Any]:
    """Base rates of the ticker and of its benchmark over the same horizon."""
    return {
        "horizon_days": horizon,
        "ticker": forward_base_rate(ticker_hist, horizon, symbol=ticker, as_of=ticker_as_of),
        "benchmark": forward_base_rate(benchmark_hist, horizon, symbol=benchmark, as_of=benchmark_as_of),
        "method": METHOD.format(h=horizon),
        "note": "A signal adds value only if its hit rate beats these base rates out of sample; "
                "no such test exists for this rule.",
    }
