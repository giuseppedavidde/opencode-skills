"""
Unified JSON schemas for trading-mcp-server inter-skill communication.

All trading and analysis tools use these Pydantic models to pass structured
data. This file is adapted from stock-crypto-analysis/schemas.py v1.0.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    """Unified verdict produced by stock-crypto-analysis."""

    LONG_TERM = "Long-Term Investment"
    SHORT_TERM_BULL = "Short-Term Speculation (Bullish)"
    SHORT_TERM_NEUTRAL = "Short-Term Speculation (Neutral)"
    AVOID = "Avoid / Wait"


class MacroWindow(str, Enum):
    """Adaptive Macro Matrix operating window."""

    FULL = "FULL"
    NORMAL = "NORMAL"
    SELECTIVE = "SELECTIVE"
    DEFENSIVE = "DEFENSIVE"


class Direction(str, Enum):
    """Trade direction."""

    LONG = "Long"
    SHORT = "Short"
    NEUTRAL = "Neutral"


class MultiTfAlignment(str, Enum):
    """Multi-timeframe trend alignment result."""

    ALIGNED_BULL = "aligned_bull"
    ALIGNED_BEAR = "aligned_bear"
    PARTIAL = "partial"
    WEAK = "weak"
    NONE = "none"


class RiskLevel(str, Enum):
    """Position risk classification."""

    LOW = "Basso"
    MEDIUM = "Medio"
    HIGH = "Alto"


class SectorImpact(str, Enum):
    """Geopolitical sector vector impact on an asset."""

    FAVORITO = "favorito"
    NEUTRO = "neutro"
    SFAVOREVOLE = "sfavorevole"


class IVRegime(str, Enum):
    """Implied Volatility regime classification."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TermStructureShape(str, Enum):
    """IV term structure shape."""

    CONTANGO = "contango"
    BACKWARDATION = "backwardation"
    FLAT = "flat"


class DimensionScore(BaseModel):
    """Score for one analysis dimension (e.g. Wyckoff, Volume Profile)."""

    name: str = Field(..., description="Dimension name (e.g. 'Wyckoff Phase')")
    weight: float = Field(..., ge=0.0, le=1.0)
    score: float = Field(..., ge=0.0, le=100.0)
    contribution: float = Field(0.0, ge=0.0)
    detail: str = Field("")


class MacroCondition(BaseModel):
    """Single condition in the Adaptive Macro Matrix scorecard."""

    name: str
    description: str
    met: bool
    points: int = Field(0, ge=0, le=2)


class MacroScore(BaseModel):
    """Phase 0 Adaptive Macro Matrix result."""

    total: int = Field(..., ge=0, le=18)
    window: MacroWindow
    conditions: list[MacroCondition] = Field(default_factory=list)
    geopolitical_sector_impact: SectorImpact = SectorImpact.NEUTRO
    favored_sectors: list[str] = Field(default_factory=list)
    harmed_sectors: list[str] = Field(default_factory=list)
    fed_rate: Optional[float] = None
    dxy_value: Optional[float] = None
    vix_value: Optional[float] = None
    fear_greed_index: Optional[int] = None
    real_yield_10y: Optional[float] = None
    btc_dominance: Optional[float] = None


class TimeframeTrend(BaseModel):
    """Trend status on a single timeframe."""

    timeframe: str
    direction: Direction
    description: str = ""


class MultiTimeframeResult(BaseModel):
    """Phase 0b multi-timeframe alignment result."""

    alignment: MultiTfAlignment
    trends: list[TimeframeTrend] = Field(default_factory=list)
    wyckoff_bonus: int = Field(0, description="Bonus/malus on Wyckoff dimension")


class RallyVelocityResult(BaseModel):
    """Phase 3 exhaust velocity assessment."""

    velocity_score: float = Field(0.0, ge=-50.0, le=20.0)
    rally_pct: Optional[float] = None
    rally_days: Optional[int] = None
    consecutive_green_candles: int = 0
    volume_declining: bool = False
    gap_unfilled: bool = False
    is_vertical: bool = False
    blocks_options: bool = False
    warnings: list[str] = Field(default_factory=list)


class RiskSizing(BaseModel):
    """Position sizing computed from Risk Sizing Matrix."""

    max_position_pct: float = Field(..., ge=0.0, le=100.0)
    stop_loss_pct: float = Field(..., ge=0.0, le=100.0)
    max_leverage: float = Field(..., ge=1.0)
    note: str = ""


class EntryTarget(BaseModel):
    """Entry and target price levels."""

    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_1_pct: float = 0.30
    target_2: Optional[float] = None
    target_2_pct: float = 0.70


class InvalidationRule(BaseModel):
    """A single exit/invalidation condition."""

    category: str
    condition: str
    action: str


class CorrelationWarning(BaseModel):
    """Portfolio correlation warning."""

    pair: tuple[str, str]
    correlation: float = Field(..., ge=-1.0, le=1.0)
    combined_weight: float
    recommendation: str


class UnifiedVerdict(BaseModel):
    """Complete output of a stock-crypto-analysis run."""

    ticker: str
    is_crypto: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = "1.0"

    composite_score: float = Field(..., ge=0.0, le=100.0)
    analysis_score: float = Field(..., ge=0.0, le=100.0)
    macro_score: int = Field(..., ge=0, le=18)

    verdict: Verdict
    direction: Direction

    dimensions: list[DimensionScore] = Field(default_factory=list)

    macro: MacroScore
    multi_timeframe: MultiTimeframeResult
    dynamic_weights: dict[str, float] = Field(default_factory=dict)

    rally_velocity: Optional[RallyVelocityResult] = None

    risk: RiskSizing
    entry: EntryTarget
    horizon: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM

    invalidation: list[InvalidationRule] = Field(default_factory=list)
    correlation_warnings: list[CorrelationWarning] = Field(default_factory=list)

    key_risk_factors: list[str] = Field(default_factory=list)


class SentimentSubScores(BaseModel):
    """Breakdown of sentiment sub-dimensions."""

    short_interest: Optional[float] = Field(None, ge=0.0, le=100.0)
    options_sentiment: Optional[float] = Field(None, ge=0.0, le=100.0)
    insider_trading: Optional[float] = Field(None, ge=0.0, le=100.0)
    institutional: Optional[float] = Field(None, ge=0.0, le=100.0)
    web_news: Optional[float] = Field(None, ge=0.0, le=100.0)
    social_media: Optional[float] = Field(None, ge=0.0, le=100.0)
    earnings_quality: Optional[float] = Field(None, ge=0.0, le=100.0)
    retail_sentiment: Optional[float] = Field(None, ge=0.0, le=100.0)
    momentum: Optional[float] = Field(None, ge=0.0, le=100.0)


class ScannerResult(BaseModel):
    """Output of a single ticker scan."""

    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    universe: str = ""
    final_score: float = Field(..., ge=0.0, le=100.0)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    sentiment_breakdown: Optional[SentimentSubScores] = None
    flags: list[str] = Field(default_factory=list)
    sector: str = ""
    price: float = 0.0
    pattern: str = ""
    market: str = ""
    modifiers: dict = Field(default_factory=dict)
    indicators: dict = Field(default_factory=dict)


class ScannerBatchResult(BaseModel):
    """Aggregate output of a scanner run over a universe."""

    universe: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tickers_scanned: int
    tickers_passed: int
    min_score_threshold: int = 50
    results: list[ScannerResult] = Field(default_factory=list)


class IVTermStructureResult(BaseModel):
    """IV term structure analysis."""

    iv_rank: float = Field(..., ge=0.0, le=100.0)
    iv_percentile: float = Field(..., ge=0.0, le=100.0)
    current_atm_iv: float
    regime: IVRegime
    shape: TermStructureShape
    expirations: list[dict] = Field(default_factory=list)


class GexResult(BaseModel):
    """Gamma Exposure analysis."""

    total_gex: Optional[float] = None
    regime: str = "unknown"
    gamma_flip_point: Optional[float] = None
    max_pain: Optional[float] = None
    call_wall_strike: Optional[float] = None
    put_wall_strike: Optional[float] = None


class StrategySuggestion(BaseModel):
    """Output of options-strategy-suggestions."""

    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strategy_name: str
    strategy_description: str
    legs: list[dict] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    max_profit: str = ""
    max_loss: float = 0.0
    breakeven: float = 0.0
    risk_reward_ratio: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    exit_plan: dict = Field(default_factory=dict)


class TradeLogEntry(BaseModel):
    """A single trade record for the feedback loop."""

    trade_id: str
    ticker: str
    entry_date: Optional[datetime] = None
    entry_price: Optional[float] = None
    position_size_pct: Optional[float] = None
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    is_open: bool = True


class DataSufficiency(BaseModel):
    """Explicit data-sufficiency check result (P0 Aug 2026).

    Used by scanner, analyze_stock, and bakshi_signals to propagate
    explicit status when OHLCV history is too short — never silently
    produce scores on insufficient data.
    """

    status: str = "ok"
    available_bars: int = 0
    required_bars: int = 50
    reason: str = ""
    diagnostic_only: bool = False
