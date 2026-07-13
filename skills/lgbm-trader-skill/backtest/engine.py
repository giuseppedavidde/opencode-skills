"""Realistic backtest engine with slippage and commission modelling.

Positions are sized as a fraction of equity (``position_size_pct``), entries
and exits are executed at the close plus/minus slippage, and a round-trip
commission is charged in basis points. The strategy is **long-only**: a
score above the threshold opens a long, anything below flattens to cash.
"""

from __future__ import annotations

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

    def metrics(self, backtest_df: pd.DataFrame) -> dict:
        """Convenience wrapper around :func:`backtest.metrics.calculate_metrics`."""
        if backtest_df is None or backtest_df.empty or "returns" not in backtest_df:
            return {}
        return calculate_metrics(backtest_df["returns"])