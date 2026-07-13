"""Realistic backtest engine with slippage and commission modelling.

Positions are sized as a fraction of equity (``position_size_pct``), entries
and exits are executed at the close plus/minus slippage, and a round-trip
commission is charged in basis points. The strategy is **long-only**: a
score above the threshold opens a long, anything below flattens to cash.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.metrics import calculate_metrics
from utils.logger import get_logger

logger = get_logger(__name__)


class BacktestEngine:
    """Backtest engine with slippage, commission and position sizing."""

    def __init__(self, config: dict) -> None:
        trading = config["trading"]
        self.slippage_bps: float = float(trading["slippage_bps"])
        self.commission_bps: float = float(trading["commission_bps"])
        self.min_score: float = float(trading["min_score_threshold"])
        self.position_size: float = float(trading["position_size_pct"])
        self.sizing_mode: str = str(trading.get("sizing_mode", "binary"))
        self.max_position_pct: float = float(
            trading.get("max_position_pct", self.position_size)
        )
        self.target_vol_pct: float = float(trading.get("target_vol_pct", 0.15))
        self.neutral_zone: float = float(trading.get("neutral_zone", 0.05))

    # ------------------------------------------------------------------ #
    def run(
        self,
        prices: pd.Series,
        signals: pd.Series,
        timestamps: pd.Index | None = None,
    ) -> pd.DataFrame:
        """Execute the backtest.

        Parameters
        ----------
        prices:
            Close prices aligned with the signals index.
        signals:
            Score (0-100) per timestamp.
        timestamps:
            Optional override index (defaults to ``prices.index``).

        Returns
        -------
        pandas.DataFrame
            Columns: ``date, position, strategy_returns, cum_returns,
            drawdown``.
        """
        if prices is None or prices.empty:
            logger.warning("Empty prices, backtest skipped")
            return pd.DataFrame()

        prices = prices.copy()
        prices.index = pd.to_datetime(prices.index)
        if timestamps is not None:
            signals = signals.reindex(pd.to_datetime(timestamps))
        else:
            signals = signals.reindex(prices.index)

        signal_long = (signals >= self.min_score).astype(int)
        # Position held next bar = signal decided at today's close
        position = signal_long.shift(1).fillna(0).astype(int)

        asset_returns = prices.pct_change().fillna(0.0)
        slip = self.slippage_bps / 1e4
        comm = self.commission_bps / 1e4

        position_change = position.diff().abs().fillna(position.iloc[0])
        # Apply slippage + commission only when position changes
        cost = position_change * (slip + comm)
        strat_returns = position * asset_returns - cost
        strat_returns = strat_returns * self.position_size
        cum = (1.0 + strat_returns).cumprod()
        running_max = cum.cummax()
        drawdown = (cum - running_max) / running_max

        out = pd.DataFrame(
            {
                "date": prices.index,
                "position": position.to_numpy(),
                "returns": strat_returns.to_numpy(),
                "cum_returns": cum.to_numpy(),
                "dd": drawdown.to_numpy(),
            }
        )
        return out

    def run_continuous(
        self,
        prices: pd.Series,
        signals: pd.Series,
        atr: pd.Series | None = None,
        timestamps: pd.Index | None = None,
        target_vol_pct: float | None = None,
    ) -> pd.DataFrame:
        """Backtest with continuous position sizing and (optional) vol-target.

        Position sizing rules (Moskowitz/Ooi/Pedersen 2012 style):

        1. ``score_norm = (score - 50) / 50``  → range ``[-1, +1]``
        2. If ``|score_norm| < neutral_zone`` → flat (neutral band).
        3. ``size_base = score_norm * max_position_pct``
        4. If ATR (annualised vol) is supplied:
           ``size = size_base * (target_vol / vol_annualized)``
           Leverage DOWN when vol > target, UP when vol < target.
           The resulting size is clipped to ``[0, max_position_pct]``
           to stay long-only and bounded (no leverage beyond the cap).
        5. Otherwise ``size = size_base`` (clip to ``[0, max_position_pct]``).

        Costs (slippage + commission) are charged on every change in the
        position size, proportional to the absolute delta.

        Returns
        -------
        pandas.DataFrame
            Columns: ``date, position, returns, cum_returns, dd``.
        """
        if prices is None or prices.empty:
            logger.warning("Empty prices, continuous backtest skipped")
            return pd.DataFrame()

        prices = prices.copy()
        prices.index = pd.to_datetime(prices.index)
        if timestamps is not None:
            signals = signals.reindex(pd.to_datetime(timestamps))
        else:
            signals = signals.reindex(prices.index)
        if atr is not None:
            atr = atr.reindex(prices.index)

        tv = float(target_vol_pct if target_vol_pct is not None else self.target_vol_pct)
        nz = float(self.neutral_zone)

        score_norm = (signals.astype(float) - 50.0) / 50.0
        # Neutral band → flat (size 0). Out-of-neutral bars get linear sizing.
        size_base = np.where(
            score_norm.abs() < nz, 0.0, score_norm
        ) * self.max_position_pct

        if atr is not None:
            vol_ann = (atr / prices).replace(0.0, np.nan) * np.sqrt(252.0)
            # Scaling factor: reduce size when vol > target, increase below.
            scale = tv / vol_ann
            size_arr = size_base * scale.to_numpy()
        else:
            size_arr = size_base

        # Long-only + bounded: clip between 0 and max_position_pct.
        size_arr = np.clip(np.nan_to_num(size_arr, nan=0.0), 0.0, self.max_position_pct)

        position = pd.Series(size_arr, index=prices.index, name="position")
        # Position is held next bar (decision at today's close).
        position = position.shift(1).fillna(0.0)

        asset_returns = prices.pct_change().fillna(0.0)
        slip = self.slippage_bps / 1e4
        comm = self.commission_bps / 1e4
        position_change = position.diff().abs().fillna(position.iloc[0])
        cost = position_change * (slip + comm)
        strat_returns = position * asset_returns - cost
        cum = (1.0 + strat_returns).cumprod()
        running_max = cum.cummax()
        drawdown = (cum - running_max) / running_max

        return pd.DataFrame(
            {
                "date": prices.index,
                "position": position.to_numpy(),
                "returns": strat_returns.to_numpy(),
                "cum_returns": cum.to_numpy(),
                "dd": drawdown.to_numpy(),
            }
        )

    def metrics(self, backtest_df: pd.DataFrame) -> dict:
        """Convenience wrapper around :func:`backtest.metrics.calculate_metrics`."""
        if backtest_df is None or backtest_df.empty or "returns" not in backtest_df:
            return {}
        return calculate_metrics(backtest_df["returns"])