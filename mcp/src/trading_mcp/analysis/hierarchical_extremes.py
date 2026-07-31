"""Hierarchical extremes detection: multi-level swing points via rolling windows.

Detects swing highs and lows at exponentially increasing granularity levels
using rolling-window peak/valley detection, then determines trend direction
from the most recent swing points at each level.
"""

from __future__ import annotations

import numpy as np


class HierarchicalExtremes:
    """Hierarchical swing-point detection at multiple timeframe levels.

    Each bar is processed sequentially via ``process_bar``.  After a bar
    has enough neighbours on both sides (determined by the level's window),
    we check whether it is a local swing high or swing low.

    Level 0 uses the smallest window (most granular, many swings);
    higher levels use larger windows (coarser, macro structure).

    Attributes:
        level_highs: dict mapping level (int) -> list of swing-high prices.
        level_lows: dict mapping level (int) -> list of swing-low prices.
        atr: current Average True Range (float).
    """

    def __init__(self, levels: int = 4, atr_lookback: int = 14) -> None:
        """Initialise the detector.

        Args:
            levels: Number of granularity levels (default 4).
            atr_lookback: Lookback for ATR calculation (default 14).
        """
        self._levels = levels
        self._atr_lookback = atr_lookback

        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []
        self._tr_values: list[float] = []

        self._atr: float = 0.0

        self.level_highs: dict[int, list[float]] = {i: [] for i in range(levels)}
        self.level_lows: dict[int, list[float]] = {i: [] for i in range(levels)}

        # Exponential window sizes per level.
        # Level 0: 3 bars → 7 needed for full context; Level 3: 12 bars.
        self._windows: dict[int, int] = {
            i: int(3 + i * 3) for i in range(levels)
        }

    @property
    def atr(self) -> float:
        """Current Average True Range."""
        return self._atr

    def process_bar(self, high: float, low: float, close: float) -> None:
        """Ingest a single OHLC bar and update internal state.

        Args:
            high: Bar high price.
            low: Bar low price.
            close: Bar close price.
        """
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        # ---- True Range & ATR ----
        if len(self._closes) >= 2:
            prev_close = self._closes[-2]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        else:
            tr = high - low
        self._tr_values.append(tr)

        n = len(self._tr_values)
        if n >= self._atr_lookback:
            self._atr = float(np.mean(self._tr_values[-self._atr_lookback:]))
        elif n > 0:
            self._atr = float(np.mean(self._tr_values))

        # ---- Swing-point detection per level ----
        total = len(self._highs)

        for level in range(self._levels):
            window = self._windows[level]
            if total < 2 * window + 1:
                continue

            # Check the bar that now has full left+right context.
            check_idx = total - 1 - window

            left = max(0, check_idx - window)
            right = min(total, check_idx + window + 1)

            seg_high = self._highs[left:right]
            h_val = self._highs[check_idx]
            if h_val == max(seg_high) and seg_high.count(h_val) == 1:
                if (
                    not self.level_highs[level]
                    or self.level_highs[level][-1] != h_val
                ):
                    self.level_highs[level].append(h_val)

            seg_low = self._lows[left:right]
            l_val = self._lows[check_idx]
            if l_val == min(seg_low) and seg_low.count(l_val) == 1:
                if (
                    not self.level_lows[level]
                    or self.level_lows[level][-1] != l_val
                ):
                    self.level_lows[level].append(l_val)


def determine_trend(
    l_highs: list[float], l_lows: list[float]
) -> str:
    """Determine trend direction from the last two swing highs and lows.

    Args:
        l_highs: Swing-high prices (most recent last).
        l_lows: Swing-low prices (most recent last).

    Returns:
        ``"uptrend"`` if both last highs and lows are rising,
        ``"downtrend"`` if both are falling,
        ``"range"`` otherwise.
    """
    if len(l_highs) < 2 or len(l_lows) < 2:
        return "range"

    highs_rising = l_highs[-1] > l_highs[-2]
    lows_rising = l_lows[-1] > l_lows[-2]

    if highs_rising and lows_rising:
        return "uptrend"
    if not highs_rising and not lows_rising:
        return "downtrend"
    return "range"
