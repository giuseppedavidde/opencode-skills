"""Earnings surprise trend (SIG-13) and the earnings-history fetch through the shared Yahoo bucket.

- :func:`fetch_earnings_history` calls yfinance ``earnings_history`` under
  :data:`trading_mcp.data.http_policy.YAHOO_BUCKET` with the provider retry
  policy (the DataProvider has no endpoint for it), and caches the answer
  for 6 h (failures for 30 s).
- :func:`compute_earnings_surprise` scores the CURRENT streak: quarters are
  sorted by date, and the streak counts the consecutive quarters with the
  same surprise sign, starting from the most recent one (a sign change ends
  it). Score (0-100, 50 = neutral, mirrored): streak of 4+ beats +25,
  2-3 beats +15, the same for misses with a minus sign; mean surprise above
  +5% +10, below -5% -10. ``surprisePercent`` from Yahoo is a FRACTION
  (0.0372 = 3.72%); values above 3 in absolute size are read as percent.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pandas as pd

from trading_mcp.data.http_policy import YAHOO_BUCKET, UpstreamFailure, call_with_retry

_HISTORY_TTL_S = 6 * 3600.0
_FAILURE_TTL_S = 30.0
_cache: dict[str, tuple[float, Any, str | None]] = {}
_cache_lock = threading.Lock()


def _yf_earnings_history(symbol: str) -> Any:
    import yfinance as yf  # pylint: disable=import-outside-toplevel

    return yf.Ticker(symbol).earnings_history


def fetch_earnings_history(symbol: str) -> tuple[pd.DataFrame | None, str | None]:
    """``(earnings_history frame or None, error)`` with a 6 h cache under the Yahoo bucket."""
    key = symbol.upper()
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
    if entry is not None:
        stamp, frame, error = entry
        ttl = _HISTORY_TTL_S if error is None else _FAILURE_TTL_S
        if now - stamp < ttl:
            return (frame.copy() if isinstance(frame, pd.DataFrame) else None), error
    try:
        frame = call_with_retry(lambda: _yf_earnings_history(key), what=f"earnings_history {key}",
                                bucket=YAHOO_BUCKET, max_attempts=2)
        error = None if isinstance(frame, pd.DataFrame) and not frame.empty else "no earnings history"
    except UpstreamFailure as exc:
        frame, error = None, f"{exc.kind}: {exc.message}"
    with _cache_lock:
        _cache[key] = (now, frame if isinstance(frame, pd.DataFrame) else None, error)
    return (frame.copy() if isinstance(frame, pd.DataFrame) else None), error


def clear_earnings_cache() -> None:
    """Drop the cached earnings histories (tests)."""
    with _cache_lock:
        _cache.clear()


def _surprises(earnings: pd.DataFrame) -> list[float]:
    frame = earnings
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.sort_index()
    elif "quarter" in frame.columns:
        frame = frame.sort_values("quarter")
    values = pd.to_numeric(frame["surprisePercent"], errors="coerce").dropna().tolist()
    if values and max(abs(v) for v in values) <= 3.0:
        values = [v * 100.0 for v in values]
    return values


def current_streak(surprises_oldest_first: list[float]) -> int:
    """Signed length of the current run of beats (+) or misses (-); 0 when the last is flat."""
    streak = 0
    for value in reversed(surprises_oldest_first):
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if sign == 0:
            break
        if streak == 0 or (streak > 0) == (sign > 0):
            streak += sign
        else:
            break
    return streak


def score_surprises(surprises_oldest_first: list[float]) -> tuple[int, str]:
    """Score of a surprise series in percent, oldest first (see the module docstring)."""
    recent = surprises_oldest_first[-8:]
    streak = current_streak(recent)
    score = 50
    details: list[str] = []
    if streak >= 4:
        score += 25
        details.append(f"Earnings beat streak: {streak}Q (+25)")
    elif streak >= 2:
        score += 15
        details.append(f"Earnings beat streak: {streak}Q (+15)")
    elif streak <= -4:
        score -= 25
        details.append(f"Earnings miss streak: {abs(streak)}Q (-25)")
    elif streak <= -2:
        score -= 15
        details.append(f"Earnings miss streak: {abs(streak)}Q (-15)")
    avg = sum(recent) / len(recent)
    if avg > 5:
        score += 10
        details.append(f"Avg surprise {avg:+.1f}% (+10)")
    elif avg < -5:
        score -= 10
        details.append(f"Avg surprise {avg:+.1f}% (-10)")
    beats = sum(1 for s in recent if s > 0)
    misses = sum(1 for s in recent if s < 0)
    details.append(f"Beats: {beats}/{len(recent)}, Misses: {misses}/{len(recent)}")
    return min(100, max(0, score)), " | ".join(details)


def compute_earnings_surprise(ticker: Any) -> tuple[int | None, str]:
    """Earnings-surprise score of a symbol (or a ``yf.Ticker``); ``None`` without data."""
    symbol = ticker if isinstance(ticker, str) else str(getattr(ticker, "ticker", "") or "")
    if not symbol:
        return None, "No symbol"
    earnings, error = fetch_earnings_history(symbol)
    if earnings is None or earnings.empty:
        return None, error or "No earnings history"
    if "surprisePercent" not in earnings.columns:
        return None, "No surprisePercent column"
    surprises = _surprises(earnings)
    if not surprises:
        return None, "No surprise data"
    return score_surprises(surprises)


def earnings_proximity_adjustment(
    _symbol: str, days_to_earnings: int | None, _iv_rank: float | None
) -> float | None:
    """Legacy proximity factor (0.15 / 0.10 / 0.05 / 0.0); not used by the composite.

    Earnings proximity is reported in the ``earnings`` block of the output
    and gates the trade plan (blackout window), not the score.
    """
    if days_to_earnings is None:
        return None
    if days_to_earnings <= 3:
        return 0.15
    if days_to_earnings <= 7:
        return 0.10
    if days_to_earnings <= 14:
        return 0.05
    return 0.0
