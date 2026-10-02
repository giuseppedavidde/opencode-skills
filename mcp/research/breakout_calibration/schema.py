"""Pydantic v2 schemas for the breakout calibration artifacts.

Convention: every return / distance value is a decimal fraction
(``0.01`` means ``1%``), never a percentage. Hit rates are fractions
in ``[0, 1]``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    """Base model: immutable, no unexpected fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SampleInfo(FrozenModel):
    """Description of the data sample and its known biases."""

    universe_source: str
    universe_note: str
    survivorship_bias: str
    n_symbols_requested: int
    n_symbols_loaded: int
    period_start: str
    period_end: str
    in_sample_end: str
    n_trading_days: int
    n_observations: int


class HorizonStats(FrozenModel):
    """Forward-return statistics for one signal group at one horizon."""

    horizon_days: int = Field(gt=0)
    n_events: int = Field(ge=0)
    mean_fwd_return: float
    median_fwd_return: float
    std_fwd_return: float
    hit_rate: float = Field(ge=0.0, le=1.0)
    mean_excess_return: float
    t_stat: float
    p_value: float = Field(ge=0.0, le=1.0)
    baseline_mean: float
    baseline_hit_rate: float = Field(ge=0.0, le=1.0)
    sample_ok: bool


class BreakoutCell(FrozenModel):
    """One breakout configuration (lookback x volume multiple)."""

    n_days: int = Field(gt=0)
    volume_mult: float = Field(ge=0.0)
    label: str
    sample: str
    horizons: list[HorizonStats]


class MomentumBucket(FrozenModel):
    """Cross-sectional quantile of a momentum/extension metric."""

    metric: str
    quantile: int = Field(ge=1)
    n_quantiles: int = Field(ge=2)
    range_low: float
    range_high: float
    sample: str
    horizons: list[HorizonStats]


class RegimeVariant(FrozenModel):
    """Breakout statistics under a market/trend regime condition."""

    condition: str
    description: str
    n_events: int = Field(ge=0)
    horizons: list[HorizonStats]


class StopOutcome(FrozenModel):
    """Stop/holding simulation result for one ATR multiple and horizon."""

    n_days: int = Field(gt=0)
    volume_mult: float = Field(ge=0.0)
    atr_mult: float = Field(gt=0.0)
    horizon_days: int = Field(gt=0)
    n_events: int = Field(ge=0)
    stop_distance_pct_mean: float
    win_rate: float = Field(ge=0.0, le=1.0)
    mean_return: float
    expectancy_over_risk: float
    profit_factor: float


class RealityCheckResult(FrozenModel):
    """White Reality Check outcome against the data-mining bias."""

    hypothesis: str
    horizon_days: int
    observed_best_excess: float
    best_config: str
    p_value_bootstrap: float = Field(ge=0.0, le=1.0)
    p_value_bonferroni: float = Field(ge=0.0, le=1.0)
    n_bootstrap: int = Field(gt=0)
    block_days: int = Field(gt=0)
    n_configs_tested: int = Field(gt=0)
    note: str


class Thresholds(FrozenModel):
    """Consumable thresholds for Phase 2. See notes for limits."""

    version: str
    generated_at: datetime
    breakout_lookback_days: int = Field(gt=0)
    breakout_volume_mult: float = Field(ge=0.0)
    breakout_requires_volume: bool
    max_extension_atr_above_sma50: float | None
    require_close_above_sma200: bool
    require_market_above_sma200: bool
    min_momentum_12m: float
    atr_window: int = Field(gt=0)
    stop_atr_mult: float = Field(gt=0.0)
    holding_days_preferred: int = Field(gt=0)
    holding_days_max: int = Field(gt=0)
    expected_win_rate: float = Field(ge=0.0, le=1.0)
    expected_excess_return: float
    mean_reversion_bias_warning: str
    gex_limitation: str
    verified: list[str]
    assumptions: list[str]
    caveats: list[str]


class CalibrationReport(FrozenModel):
    """Top-level calibration artifact persisted as ``report.json``."""

    generated_at: datetime
    sample: SampleInfo
    methodology: list[str]
    baseline: list[HorizonStats]
    breakout_grid: list[BreakoutCell]
    regime_analysis: list[RegimeVariant]
    momentum_analysis: list[MomentumBucket]
    stop_analysis: list[StopOutcome]
    in_sample_grid: list[BreakoutCell]
    out_of_sample_grid: list[BreakoutCell]
    reality_check: RealityCheckResult | None
    thresholds: Thresholds
