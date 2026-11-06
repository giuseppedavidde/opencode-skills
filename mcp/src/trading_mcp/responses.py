"""Typed wire contract for every MCP tool.

Each tool annotates its return type with a model from this module. FastMCP
turns that annotation into the tool's ``outputSchema``, so a client knows the
shape before the first call and a malformed payload fails at the boundary
instead of confusing the consumer.

Two rules keep the contract safe and cheap:

- ``extra="allow"``: models document and validate known fields without
  dropping vendor-specific or newly added ones. ``model_dump()`` therefore
  preserves every key (see ``tests/test_responses_contract.py``).
- Nested payloads that are large or vendor-shaped (option legs, per-dimension
  detail, payoff curves) stay ``dict`` / ``list[dict]``. Typing every leaf
  would inflate the schema that is sent on every session without adding
  meaning to the model that reads it.

This module is the *live* contract. :mod:`trading_mcp.schemas` keeps the
shared analysis vocabulary (enums, unified verdict) used across skills.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bump when a payload shape changes. The contract snapshot in
# ``docs/contract/tools.json`` records it, and CI fails on drift without a bump.
CONTRACT_VERSION = "2.0.0"


class PayloadModel(BaseModel):
    """Nested payload fragment: keeps unknown fields, carries no envelope."""

    model_config = ConfigDict(extra="allow")


class ToolResponse(PayloadModel):
    """Top-level tool answer: never drops a field and always says where it came from.

    Provenance uses explicit ``unknown`` defaults instead of invented values:
    a number without a source is not verifiable. ``as_of=None`` means the
    upstream source did not expose a data date.
    """

    schema_version: str = CONTRACT_VERSION
    data_source: str = "unknown"
    data_quality: str = "unknown"
    as_of: str | None = None
    error_kind: str | None = None
    error_retryable: bool | None = None

    @model_validator(mode="after")
    def _derive_error_fields(self) -> "ToolResponse":
        """Fill the error envelope from the legacy per-tool error flags."""
        if self.error_kind is None and getattr(self, "error", None):
            blocking = getattr(self, "error_is_blocking", True)
            object.__setattr__(self, "error_kind", "blocking" if blocking else "degraded")
        return self


# ── Data tools ───────────────────────────────────────────────────────

class OhlcvBar(PayloadModel):
    """One daily OHLCV bar."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockDataResponse(ToolResponse):
    """Output of ``fetch_stock_data``."""
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str
    current_price: float | None = None
    ohlcv: list[OhlcvBar] = Field(default_factory=list)
    info: dict[str, Any] = Field(default_factory=dict)
    indicators: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class CryptoDataResponse(ToolResponse):
    """Output of ``fetch_crypto_data``."""
    data_source: str = "coingecko+yfinance"
    data_quality: str = "eod"

    coin_id: str
    symbol: str | None = None
    current_price_usd: float | None = None
    market_cap: float | None = None
    total_volume: float | None = None
    ohlcv: list[OhlcvBar] = Field(default_factory=list)
    error: str | None = None


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


# ── Analysis tools ───────────────────────────────────────────────────

class ScanResultItem(PayloadModel):
    """One ranked ticker inside a ``scan_market`` batch."""

    ticker: str
    final_score: float | None = None
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    modifiers: dict[str, Any] = Field(default_factory=dict)
    indicators: dict[str, Any] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    sector: str = ""
    price: float | None = None
    pattern: str = ""
    sentiment_breakdown: dict[str, Any] | None = None


class ScanMarketResponse(ToolResponse):
    """Output of ``scan_market``."""
    data_source: str = "yfinance"
    data_quality: str = "eod"

    universe: str
    universe_metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None
    tickers_scanned: int = 0
    tickers_passed: int = 0
    min_score_threshold: float = 0.0
    elapsed_seconds: float | None = None
    workers: int = 0
    failures: int = 0
    insufficient_data_count: int = 0
    insufficient_data_detail: list[dict[str, Any]] = Field(default_factory=list)
    results: list[ScanResultItem] = Field(default_factory=list)
    error: str | None = None


class AnalyzeStockResponse(ToolResponse):
    """Output of ``analyze_stock``.

    ``verdict`` is a free-form operational label; ``composite_score`` and the
    volume-profile semantics behind it live in the analysis code, not here.
    The ``status="insufficient_data"`` variant reports ``history_bars`` and
    ``required_bars`` instead of scores.
    """
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str | None = None
    timestamp: str | None = None
    composite_score: float | None = None
    verdict: str | None = None
    confidence: str | None = None
    signal_alignment: dict[str, Any] = Field(default_factory=dict)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    modifiers: dict[str, Any] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    pattern: str = ""
    sector: str = ""
    price: float | None = None
    action_recommendation: dict[str, Any] = Field(default_factory=dict)
    data_freshness: str | None = None
    last_data_date: str | None = None
    indicators: dict[str, Any] | None = None
    sentiment_breakdown: dict[str, Any] | None = None
    momentum_bias_warning: dict[str, Any] | None = None
    options_context: dict[str, Any] | None = None
    status: str | None = None
    history_bars: int | None = None
    required_bars: int | None = None
    reason: str | None = None
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


class BreakoutContextResponse(ToolResponse):
    """Output of ``breakout_context`` (bias guard, trigger, GEX overlay, risk)."""
    data_source: str = "yfinance+options"
    data_quality: str = "mixed"

    ticker: str
    price: float | None = None
    momentum: dict[str, Any] = Field(default_factory=dict)
    bias_guard: dict[str, Any] = Field(default_factory=dict)
    breakout_triggers: dict[str, Any] = Field(default_factory=dict)
    gex: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# ── Knowledge tools ──────────────────────────────────────────────────

class MacroContextResponse(ToolResponse):
    """Output of ``get_macro_context``.

    ``macro_window`` is derived from ``detected_regime`` so the two can never
    contradict each other.
    """
    data_source: str = "yfinance"
    data_quality: str = "eod"

    timestamp: str | None = None
    vix: float | None = None
    dxy: float | None = None
    dxy_trend: str | None = None
    fed_rate: float | None = None
    btc_dominance: float | None = None
    btc_price: float | None = None
    fear_greed_index: float | None = None
    detected_regime: str | None = None
    macro_window: str | None = None
    dynamic_weights_stock: dict[str, float] = Field(default_factory=dict)
    dynamic_weights_crypto: dict[str, float] = Field(default_factory=dict)


class ClearMacroCacheResponse(ToolResponse):
    """Output of ``clear_macro_cache``."""
    data_source: str = "core"
    data_quality: str = "derived"

    status: str
    message: str = ""


class SkillKnowledgeResponse(ToolResponse):
    """Output of ``get_skill_knowledge``.

    ``content`` is capped (see ``truncated``) and ``sections`` lists the
    available headings so the caller can re-query one section.
    """
    data_source: str = "skill"
    data_quality: str = "derived"

    skill_name: str | None = None
    section: str | None = None
    sections: list[str] | None = None
    content: str | None = None
    files: list[str] = Field(default_factory=list)
    truncated: bool = False
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


# ── Quant tools ──────────────────────────────────────────────────────

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


class TSMomResult(ToolResponse):
    """Output of ``tsmom_signals`` (Moskowitz, Ooi & Pedersen 2012)."""
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str
    available: bool = False
    price: float | None = None
    lookback_months: int = 12
    cum_return_lookback: float | None = None
    signal: int = 0
    ewma_vol: float | None = None
    vol_scaling: float | None = None
    position_size: float | None = None
    mom_score: float | None = None
    direction: str = "unavailable"
    pct_positive_months: float | None = None
    sharpe_lookback: float | None = None
    target_vol: float = 0.40
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 60
    paper_reference: dict[str, Any] = Field(default_factory=dict)


class BakshiVRP(PayloadModel):
    """Variance risk premium estimate (Bakshi & Kapadia 2003)."""

    vrp_annualized: float = 0.0
    vrp_pct_of_premium: float = 0.0
    regime: str = "NORMAL_VOL"
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
    dte: int = 30
    atm_iv: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None
    vrp: BakshiVRP = Field(default_factory=BakshiVRP)
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


class LGBMResult(ToolResponse):
    """Output of ``lgbm_predict``.

    The 0-100 score is not a probability: ``calibrated_probability`` stays
    None until an out-of-sample calibration artifact is validated.
    """
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str
    available: bool = False
    score: float | None = None
    signal: str = "unavailable"
    model: str | None = None
    individual_signals: dict[str, float] = Field(default_factory=dict)
    meta_weights: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 0
    reason: str = ""
    calibrated_probability: float | None = None
    calibration_status: str = "not_calibrated"


class PostProcessAdjustment(PayloadModel):
    """One skill-driven adjustment of the LGBM score."""

    skill: str
    delta: int = 0
    confidence: str = "bassa"
    reason: str = ""
    data_available: bool = True


class PostProcessResult(ToolResponse):
    """Output of ``lgbm_postprocess``."""
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str
    lgbm_raw_score: float = 50.0
    adjusted_score: float = 50.0
    total_adjustment: int = 0
    adjustments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


ResponseT = TypeVar("ResponseT", bound="ToolResponse")


def typed(model: type[ResponseT]) -> Callable[[Callable[..., Any]], Callable[..., ResponseT]]:
    """Coerce a tool answer into its declared model at the boundary.

    FastMCP only serialises fields that were *set*; a dict answer therefore
    loses model defaults such as ``schema_version`` and provenance. Wrapping
    the function makes every payload explicit and self-describing, and keeps
    the return annotation (and therefore the ``outputSchema``) intact.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., ResponseT]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ResponseT:
            result = func(*args, **kwargs)
            return result if isinstance(result, model) else model.model_validate(result)

        return wrapper

    return decorator


def error_payload(
    message: str,
    *,
    kind: str = "blocking",
    retryable: bool = False,
    data_source: str = "unknown",
    **extra: Any,
) -> dict[str, Any]:
    """Build the uniform error answer used by every tool.

    Args:
        message: Human-readable failure reason.
        kind: ``blocking`` when no answer can be produced, ``degraded`` when
            the answer is partial but usable.
        retryable: True when a later identical call may succeed.
        data_source: Where the (missing) data would have come from.
        extra: Additional payload fields for the specific tool.
    """
    return {
        "error": message,
        "error_kind": kind,
        "error_retryable": retryable,
        "data_source": data_source,
        **extra,
    }
