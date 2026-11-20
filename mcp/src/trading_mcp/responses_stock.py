"""Wire models of the stock tools.

``scan_market``, ``analyze_stock``, ``breakout_context`` and ``tsmom_signals``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from trading_mcp.responses import PayloadModel, QuoteStamp, ToolResponse


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
    price_as_of: str | None = None
    price_source: str | None = None
    pattern: str = ""
    sentiment_breakdown: dict[str, Any] | None = None


class ScanMarketResponse(ToolResponse):
    """Output of ``scan_market``.

    Scores use complete daily bars only. ``degraded`` is True when any ticker
    failed or the deadline cut the scan: ``failed_tickers`` lists them and
    ``coverage_pct`` is the share of tickers that were processed. A degraded
    scan is never cached. ``results`` is never a complete ranking when
    ``coverage_pct`` < 100.
    """
    data_source: str = "yfinance"
    data_quality: str = "daily_complete_bars"

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
    tickers_processed: int = 0
    coverage_pct: float | None = None
    failed_tickers: list[dict[str, Any]] = Field(default_factory=list)
    deadline_s: float | None = None
    deadline_hit: bool = False
    limits: dict[str, Any] = Field(default_factory=dict)
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
    price_as_of: str | None = None
    price_source: str | None = None
    quote: QuoteStamp | None = None
    action_recommendation: dict[str, Any] = Field(default_factory=dict)
    data_freshness: str | None = None
    last_data_date: str | None = None
    bars_as_of: str | None = None
    indicators: dict[str, Any] | None = None
    sentiment_breakdown: dict[str, Any] | None = None
    momentum_bias_warning: dict[str, Any] | None = None
    options_context: dict[str, Any] | None = None
    status: str | None = None
    history_bars: int | None = None
    required_bars: int | None = None
    reason: str | None = None
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


class TSMomResult(ToolResponse):
    """Output of ``tsmom_signals`` (Moskowitz, Ooi & Pedersen 2012)."""
    data_source: str = "yfinance"
    data_quality: str = "eod"

    ticker: str
    available: bool = False
    price: float | None = None
    lookback_months: int = 12
    cum_return_lookback: float | None = None
    signal: int | None = None
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
