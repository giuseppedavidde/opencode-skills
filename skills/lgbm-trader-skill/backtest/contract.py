"""Backtest contract: explicit prediction/backtest data models.

All models enforce the P0 design rule: signals at time ``t`` use ONLY data
available at ``t``. The ``as_of`` date marks the prediction timestamp; the
forward return is computed from ``as_of + horizon_days`` by the evaluator
with a strict look-ahead check.

P0 August 2026: added explicit status for short-history scenarios.
``build_predictions_from_ohlcv`` now returns a ``BacktestBuildResult``
with ``status`` (``ok`` / ``insufficient_data``), per-horizon capability
flags, and a ``reason`` string — no more silent empty lists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, model_validator


# ── Enums ──────────────────────────────────────────────────────────────

class BacktestBuildStatus(str, Enum):
    """Explicit build status — never hide insufficiency as empty list."""
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"


# ── Config ─────────────────────────────────────────────────────────────

class BacktestConfig(BaseModel):
    """Configuration for a reproducible OHLCV-only backtest.

    Attributes:
        horizons_days: Forward return horizons (e.g. [20, 60, 180]).
        min_bars: Minimum bars required for a valid observation
            (canonical VP window = 252).
        strict_mode: If True (default), requires canonical window +
            >=30 observations per horizon. Insufficient data yields
            ``status=insufficient_data`` and no metrics computed.
        vp_window_days: VP rolling window size (default 365 for 252
            trading-day approx).
        vp_min_window_days: Absolute minimum VP window in diagnostic
            mode (must be >= 20).
        min_horizon_observations: Minimum OOS observations needed
            before computing metrics for a horizon.
        permutation_control: Enable IC permutation sanity check.
        diagnostic_only: If True, results are flagged as diagnostic
            and NOT comparable to canonical 365d calibration.
    """

    horizons_days: list[int] = Field(default_factory=lambda: [20, 60, 180])
    min_bars: int = 252
    strict_mode: bool = True
    vp_window_days: int = 365
    vp_min_window_days: int = 20
    min_horizon_observations: int = 30
    permutation_control: bool = True
    diagnostic_only: bool = False


# ── Prediction record ──────────────────────────────────────────────────

class BacktestPrediction(BaseModel):
    """A single point-in-time prediction record.

    Attributes:
        ticker: Stock ticker.
        as_of: The date at which the prediction was made (close of day).
        signal_score: Signal value at as_of (e.g. VP score, LGBM score).
        forward_price: Price at as_of + horizon (set by evaluator).
        forward_return: Realized return from as_of to as_of + horizon.
    """

    ticker: str
    as_of: str
    signal_score: float
    horizon_days: int
    forward_price: Optional[float] = None
    forward_return: Optional[float] = None

    @model_validator(mode="after")
    def _check_as_of_format(self) -> "BacktestPrediction":
        try:
            datetime.strptime(self.as_of, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"as_of must be YYYY-MM-DD, got {self.as_of}"
            ) from exc
        return self


# ── Per-horizon capability ─────────────────────────────────────────────

class HorizonCapability(BaseModel):
    """Whether a given horizon is supported with the available data.

    A horizon is ``supported`` if ``available_bars >= required_bars``.
    If not supported, predictions for that horizon are NOT generated
    and metrics are NOT computed.
    """

    horizon_days: int
    supported: bool
    required_bars: int
    available_bars: int
    reason: str = ""


# ── Build result (replaces bare list) ─────────────────────────────────

class BacktestBuildResult(BaseModel):
    """Explicit result of ``build_predictions_from_ohlcv``.

    Never returns an empty list without explanation. The ``status``
    field tells the caller whether the data is sufficient.

    Attributes:
        status: ``ok`` or ``insufficient_data``.
        ticker: Ticker label.
        available_bars: Total OHLCV bars available.
        required_bars: Minimum bars required (min_bars + max_horizon).
        minimum_signal_bars: The ``min_bars`` parameter used.
        requested_horizons: List of requested horizon days.
        horizons: Per-horizon capability flags.
        predictions: Point-in-time predictions (may be empty).
        diagnostic_only: True if VP window < canonical 365d.
        reason: Human-readable explanation of status.
        vp_window_effective: Actual VP window days used.
    """

    status: BacktestBuildStatus
    ticker: str
    available_bars: int
    required_bars: int
    minimum_signal_bars: int
    requested_horizons: list[int]
    horizons: list[HorizonCapability]
    predictions: list[BacktestPrediction]
    diagnostic_only: bool = False
    reason: str = ""
    vp_window_effective: int = 365


# ── Horizon evaluation ─────────────────────────────────────────────────

class HorizonResult(BaseModel):
    """Per-horizon evaluation metrics.

    Fields added P0:
        supported: Whether this horizon had enough data.
        required_observations: Minimum observations needed (default 30).
        status: ``ok`` or ``insufficient_data``.
    """

    horizon_days: int
    supported: bool = True
    n_observations: int = 0
    required_observations: int = 30
    status: str = ""
    ic_rank: Optional[float] = None
    ic_pearson: Optional[float] = None
    hit_rate: float = 0.0
    mean_return_pct: float = 0.0
    quintile_spread: Optional[float] = None
    permutation_ic_rank: Optional[float] = None
    permutation_ic_pearson: Optional[float] = None

    quintile_returns: dict[str, float] = Field(default_factory=dict)


# ── Aggregate result ───────────────────────────────────────────────────

class BacktestResult(BaseModel):
    """Aggregate backtest output for a ticker/universe.

    Attributes:
        horizons: Per-horizon results (with supported/unsupported flags).
        as_of_range: Date range covered by the backtest.
        signal_description: Human-readable description of the signal source.
        limits: Known limitations of this backtest.
        diagnostic_only: True if a short VP window or diagnostic mode.
        build_status: OK or insufficient_data from the build phase.
    """

    ticker: str
    horizons: list[HorizonResult] = Field(default_factory=list)
    as_of_range: tuple[str, str] = ("", "")
    signal_description: str = ""
    limits: list[str] = Field(default_factory=list)
    diagnostic_only: bool = False
    build_status: str = ""
    calibration_status: str = "not_calibrated"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Builder function (P0 v2: explicit status) ─────────────────────────

def build_predictions_from_ohlcv(
    ohlcv: pd.DataFrame,
    horizons: list[int],
    signal: pd.Series,
    ticker: str = "UNKNOWN",
    min_bars: int = 252,
    config: BacktestConfig | None = None,
) -> BacktestBuildResult:
    """Build point-in-time predictions from OHLCV + a signal series.

    **P0 v2**: returns ``BacktestBuildResult`` with explicit status
    instead of a bare list. Use ``build_result.predictions`` to get the
    prediction records.

    All predictions are anchored at ``as_of`` = signal bar date.
    Forward returns are computed using STRICTLY future data only
    (``.shift(-h)``). Null predictions (NaN signal, insufficient future
    data, etc.) are dropped.

    Per-horizon capability: a horizon is ``supported`` only if
    ``total_bars >= min_bars + horizon_days``. Unsupported horizons
    produce zero predictions.

    Parameters
    ----------
    ohlcv:
        DataFrame with at least a ``Close`` column and a DatetimeIndex.
    horizons:
        Forward horizons in trading days (NOT calendar days).
    signal:
        Series aligned to ohlcv.index, carrying a score value per bar.
    ticker:
        Ticker label for the output records.
    min_bars:
        Minimum bars across all horizons for a row to be usable.
    config:
        Optional BacktestConfig for vp_window info.

    Returns
    -------
    BacktestBuildResult
    """
    if config is None:
        config = BacktestConfig()

    available_bars = len(ohlcv) if not ohlcv.empty else 0
    max_horizon = max(horizons)
    required_bars = min_bars + max_horizon
    vp_window = config.vp_window_days if not config.diagnostic_only else max(
        config.vp_min_window_days, min(config.vp_window_days // 12, config.vp_window_days)
    )
    # For diagnostic mode, use vp_min_window_days clamped to available
    if config.diagnostic_only:
        vp_window = max(config.vp_min_window_days, available_bars // 4)

    # Per-horizon capability
    horizon_caps: list[HorizonCapability] = []
    for h in sorted(horizons):
        need = min_bars + h
        cap = HorizonCapability(
            horizon_days=h,
            supported=available_bars >= need,
            required_bars=need,
            available_bars=available_bars,
            reason="" if available_bars >= need else (
                f"Need {need} bars (min_bars={min_bars} + horizon={h}), "
                f"have {available_bars}"
            ),
        )
        horizon_caps.append(cap)

    # Global status check
    if ohlcv.empty or signal.empty:
        return BacktestBuildResult(
            status=BacktestBuildStatus.INSUFFICIENT_DATA,
            ticker=ticker,
            available_bars=available_bars,
            required_bars=required_bars,
            minimum_signal_bars=min_bars,
            requested_horizons=horizons,
            horizons=horizon_caps,
            predictions=[],
            diagnostic_only=config.diagnostic_only,
            vp_window_effective=vp_window,
            reason="OHLCV or signal is empty",
        )

    if config.strict_mode and available_bars < required_bars:
        return BacktestBuildResult(
            status=BacktestBuildStatus.INSUFFICIENT_DATA,
            ticker=ticker,
            available_bars=available_bars,
            required_bars=required_bars,
            minimum_signal_bars=min_bars,
            requested_horizons=horizons,
            horizons=horizon_caps,
            predictions=[],
            diagnostic_only=config.diagnostic_only,
            vp_window_effective=vp_window,
            reason=(
                f"Strict mode: {available_bars} bars available, "
                f"{required_bars} required (min_bars={min_bars} + "
                f"max_horizon={max_horizon})"
            ),
        )

    close = ohlcv["Close"]
    aligned_signal = signal.reindex(close.index)
    predictions: list[BacktestPrediction] = []

    supported_horizons = [h for h in horizons if available_bars >= min_bars + h]

    if not supported_horizons:
        return BacktestBuildResult(
            status=BacktestBuildStatus.INSUFFICIENT_DATA,
            ticker=ticker,
            available_bars=available_bars,
            required_bars=required_bars,
            minimum_signal_bars=min_bars,
            requested_horizons=horizons,
            horizons=horizon_caps,
            predictions=[],
            diagnostic_only=config.diagnostic_only,
            vp_window_effective=vp_window,
            reason="No horizon is supported with available data",
        )

    for h in supported_horizons:
        fwd_price = close.shift(-h)
        fwd_return = close.pct_change(h).shift(-h)

        max_i = len(close) - h
        for i in range(max_i):
            as_of_date = close.index[i]
            score_val = aligned_signal.iloc[i]
            fwd_p = fwd_price.iloc[i]
            fwd_r = fwd_return.iloc[i]

            if pd.isna(score_val) or pd.isna(fwd_p) or pd.isna(fwd_r):
                continue

            predictions.append(
                BacktestPrediction(
                    ticker=ticker,
                    as_of=str(as_of_date.date()),
                    signal_score=float(score_val),
                    horizon_days=h,
                    forward_price=float(fwd_p),
                    forward_return=float(fwd_r),
                )
            )

    return BacktestBuildResult(
        status=BacktestBuildStatus.OK,
        ticker=ticker,
        available_bars=available_bars,
        required_bars=required_bars,
        minimum_signal_bars=min_bars,
        requested_horizons=horizons,
        horizons=horizon_caps,
        predictions=predictions,
        diagnostic_only=config.diagnostic_only,
        vp_window_effective=vp_window,
        reason=f"{len(predictions)} predictions across "
        f"{len(supported_horizons)} supported horizon(s)",
    )
