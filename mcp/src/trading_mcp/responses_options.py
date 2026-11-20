"""Wire models of the options tools.

``fetch_options_chain``, ``analyze_options``, ``gex_analysis``,
``suggest_options_strategy``, ``bali_signals`` and ``bakshi_signals``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from trading_mcp.responses import PayloadModel, ToolResponse


class IvMetrics(PayloadModel):
    """Implied-volatility aggregates for one chain.

    ``iv_rank`` / ``iv_percentile`` are ``None`` when no historical IV series
    exists; ``iv_range_position`` is the within-chain position, not a rank.
    """

    atm_iv: float | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    iv_range_position: float | None = None
    put_call_ratio_vol: float | None = None
    put_call_ratio_oi: float | None = None
    term_structure: list[dict[str, Any]] = Field(default_factory=list)
    iv_coverage_pct: float | None = None
    num_quote_iv: int = 0
    num_synthetic_iv: int = 0
    num_fallback_iv: int = 0
    smile_fitted: bool = False


class OptionsChainResponse(ToolResponse):
    """Output of ``fetch_options_chain``.

    ``_source`` is ``live``, ``cache`` or ``fallback``; ``data_quality``
    tells whether Greeks are native or Black-Scholes computed locally.
    """

    ticker: str
    underlying_price: float | None = None
    expirations: list[str] = Field(default_factory=list)
    selected_expiry: str | None = None
    dte: int | None = None
    calls: list[dict[str, Any]] = Field(default_factory=list)
    puts: list[dict[str, Any]] = Field(default_factory=list)
    iv_metrics: IvMetrics = Field(default_factory=IvMetrics)
    _source: str | None = None
    _fallback_note: str | None = None
    data_source: str | None = None
    data_quality: str | None = None
    risk_free_rate: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AnalyzeOptionsResponse(ToolResponse):
    """Output of ``analyze_options`` (multi-leg Greeks, payoff, probabilities)."""
    data_source: str = "options"
    data_quality: str = "mixed"

    ticker: str | None = None
    underlying_price: float | None = None
    expiry: str | None = None
    dte: int | None = None
    leg_expiries: list[str] = Field(default_factory=list)
    strategy_classification: str | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list)
    position_greeks: dict[str, Any] = Field(default_factory=dict)
    pnl: dict[str, Any] = Field(default_factory=dict)
    estimated_costs: dict[str, Any] = Field(default_factory=dict)
    payoff_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    breakevens: list[float] = Field(default_factory=list)
    probabilities: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    risk_free_rate: dict[str, Any] = Field(default_factory=dict)
    warning: str | None = None
    error: str | None = None


class GexAnalysisResponse(ToolResponse):
    """Output of ``gex_analysis``.

    ``net_gex`` is in dollars per 1% underlying move (per-share gamma
    convention, see :mod:`trading_mcp.analysis.gex`).
    """

    ticker: str
    underlying_price: float | None = None
    expiries_used: list[str] = Field(default_factory=list)
    n_strikes: int | None = None
    net_gex: float | None = None
    total_call_gex: float | None = None
    total_put_gex: float | None = None
    gamma_flip: float | None = None
    distance_to_flip_pct: float | None = None
    spot_position: str | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    regime: str | None = None
    regime_description: str | None = None
    profile: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None
    data_source: str | None = None
    data_quality: str | None = None
    iv_coverage_pct: float | None = None
    warnings: list[str] = Field(default_factory=list)
    convention: str | None = None
    error: str | None = None


class StrategySuggestionResponse(ToolResponse):
    """Output of ``suggest_options_strategy``."""
    data_source: str = "computed"
    data_quality: str = "derived"

    ticker: str
    timestamp: str | None = None
    strategy_name: str | None = None
    strategy_description: str | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    max_profit: str | None = None
    max_loss: float | None = None
    breakeven: float | None = None
    risk_reward_ratio: float | None = None
    warnings: list[str] = Field(default_factory=list)
    exit_plan: dict[str, Any] = Field(default_factory=dict)


class BaliResult(ToolResponse):
    """Output of ``bali_signals`` (Bali & Hovakimian 2009 volatility spreads).

    ``available=False`` marks a failure path: ``composite_bali_score`` is then
    ``None`` and ``error_is_blocking`` says whether the signal can be used.
    """
    data_source: str = "yfinance+options"
    data_quality: str = "mixed"

    ticker: str
    available: bool = False
    spot: float | None = None
    rv: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None
    atm_straddle_iv: float | None = None
    rvol_ivol_spread: float | None = None
    cvol_pvol_spread: float | None = None
    rvol_ivol_score: float | None = None
    cvol_pvol_score: float | None = None
    composite_bali_score: float | None = None
    direction: str = "unavailable"
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 50
    paper_reference: dict[str, Any] = Field(default_factory=dict)


class BakshiVRP(PayloadModel):
    """Variance risk premium estimate (Bakshi & Kapadia 2003)."""

    vrp_annualized: float | None = None
    vrp_pct_of_premium: float | None = None
    regime: str | None = None
    description: str = ""


class BakshiStrikeAnalysis(PayloadModel):
    """Delta-hedged P&L for one strike."""

    strike: float
    moneyness: float
    option_premium: float
    vega: float
    vega_ratio: float
    seller_profit_per_option: float
    seller_profit_per_contract: float
    buyer_loss_per_option: float
    vrp_pct_of_premium: float
    seller_profit_per_100_notional: float
    zone: str
    recommendation: str


VRP_CALIBRATION_SOURCE = "Bakshi & Kapadia (2003), Table 4 (S&P 500 only)"


class BakshiResult(ToolResponse):
    """Output of ``bakshi_signals``.

    ``calibrated`` is False unless a ticker-specific VRP history exists;
    ``calibrated_vrp`` is then None instead of a misleading estimate.
    """
    data_source: str = "yfinance+options"
    data_quality: str = "mixed"

    ticker: str
    spot: float | None = None
    expiry: str | None = None
    dte: int | None = None
    atm_iv: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None
    vrp: BakshiVRP | None = None
    strikes_analysis: list[BakshiStrikeAnalysis] = Field(default_factory=list)
    error: str | None = None
    available_bars: int = 0
    required_bars: int = 0
    paper_reference: dict[str, Any] = Field(default_factory=dict)
    calibration_status: str = "not_calibrated"
    calibration_source: str = VRP_CALIBRATION_SOURCE
    calibrated: bool = False
    calibrated_vrp: float | None = None
    rate_source: str | None = None
    rate_as_of: str | None = None
    estimated_costs: dict[str, Any] | None = None
