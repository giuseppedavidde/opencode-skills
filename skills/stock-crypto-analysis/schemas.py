"""
Unified JSON schemas for inter-skill communication.

All trading and analysis skills use these Pydantic models to pass structured
data instead of parsing free-form markdown. This file is the single source of
truth for the output format of stock-crypto-analysis, market-accumulation-scanner,
and options-strategy-suggestions.

Version: 1.0
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


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
    PARTIAL = "partial"  # weekly+ daily aligned, 4h contrary
    WEAK = "weak"  # only weekly aligned
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


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    """Score for one analysis dimension (e.g. Wyckoff, Volume Profile)."""

    name: str = Field(..., description="Dimension name (e.g. 'Wyckoff Phase')")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight in final composite")
    score: float = Field(..., ge=0.0, le=100.0, description="Raw dimension score (0-100)")
    contribution: float = Field(0.0, ge=0.0, description="weight * score (computed)")
    detail: str = Field("", description="Short explanation of the score")


# ---------------------------------------------------------------------------
# Adaptive Macro Matrix
# ---------------------------------------------------------------------------


class MacroCondition(BaseModel):
    """Single condition in the Adaptive Macro Matrix scorecard."""

    name: str
    description: str
    met: bool
    points: int = Field(0, ge=0, le=2)


class MacroScore(BaseModel):
    """Phase 0 Adaptive Macro Matrix result."""

    total: int = Field(..., ge=0, le=18, description="Macro score (0-18)")
    window: MacroWindow
    conditions: list[MacroCondition] = Field(default_factory=list)
    geopolitical_sector_impact: SectorImpact = SectorImpact.NEUTRO
    favored_sectors: list[str] = Field(default_factory=list)
    harmed_sectors: list[str] = Field(default_factory=list)
    # Raw data points collected
    fed_rate: Optional[float] = None
    dxy_value: Optional[float] = None
    vix_value: Optional[float] = None
    fear_greed_index: Optional[int] = None
    real_yield_10y: Optional[float] = None
    btc_dominance: Optional[float] = None


# ---------------------------------------------------------------------------
# Multi-timeframe alignment
# ---------------------------------------------------------------------------


class TimeframeTrend(BaseModel):
    """Trend status on a single timeframe."""

    timeframe: str = Field(..., description="e.g. 'weekly', 'daily', '4h'")
    direction: Direction
    description: str = ""


class MultiTimeframeResult(BaseModel):
    """Phase 0b multi-timeframe alignment result."""

    alignment: MultiTfAlignment
    trends: list[TimeframeTrend] = Field(default_factory=list)
    wyckoff_bonus: int = Field(0, description="Bonus/malus applied to Wyckoff dimension")


# ---------------------------------------------------------------------------
# Rally velocity (Phase 3 exhaustion check)
# ---------------------------------------------------------------------------


class RallyVelocityResult(BaseModel):
    """Phase 3 exhaust velocity assessment."""

    velocity_score: float = Field(0.0, ge=-50.0, le=20.0, description="Aggregate velocity score")
    rally_pct: Optional[float] = Field(None, description="% move in recent window")
    rally_days: Optional[int] = Field(None, description="Days of the move")
    consecutive_green_candles: int = 0
    volume_declining: bool = False
    gap_unfilled: bool = False
    is_vertical: bool = Field(False, description="True if rally >30% in <20 days")
    blocks_options: bool = Field(
        False,
        description="True if rally velocity is so high that option entries should be blocked"
    )
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk sizing
# ---------------------------------------------------------------------------


class RiskSizing(BaseModel):
    """Position sizing computed from Risk Sizing Matrix."""

    max_position_pct: float = Field(..., ge=0.0, le=100.0)
    stop_loss_pct: float = Field(..., ge=0.0, le=100.0)
    max_leverage: float = Field(..., ge=1.0)
    note: str = ""


class CorrelationWarning(BaseModel):
    """Portfolio correlation warning (Phase 1.2)."""

    pair: tuple[str, str]
    correlation: float = Field(..., ge=-1.0, le=1.0)
    combined_weight: float
    recommendation: str


# ---------------------------------------------------------------------------
# Entry / exit plan
# ---------------------------------------------------------------------------


class EntryTarget(BaseModel):
    """Entry and target price levels."""

    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_1_pct: float = Field(0.30, description="Pct of position to close at T1")
    target_2: Optional[float] = None
    target_2_pct: float = Field(0.70, description="Pct of position to close at T2")


class InvalidationRule(BaseModel):
    """A single exit/invalidation condition."""

    category: str = Field(..., description="'technical', 'sentiment', 'event', or 'time'")
    condition: str
    action: str


# ---------------------------------------------------------------------------
# Unified Verdict (main output of stock-crypto-analysis)
# ---------------------------------------------------------------------------


class UnifiedVerdict(BaseModel):
    """Complete output of a stock-crypto-analysis run."""

    # Metadata
    ticker: str
    is_crypto: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    schema_version: str = "1.0"

    # Scores
    composite_score: float = Field(..., ge=0.0, le=100.0)
    analysis_score: float = Field(..., ge=0.0, le=100.0)
    macro_score: int = Field(..., ge=0, le=18)

    # Verdict
    verdict: Verdict
    direction: Direction

    # Dimensions
    dimensions: list[DimensionScore] = Field(default_factory=list)

    # Phase 0
    macro: MacroScore
    multi_timeframe: MultiTimeframeResult
    dynamic_weights: dict[str, float] = Field(default_factory=dict,
                                               description="Phase 1.3 regime-adjusted weights")

    # Phase 3 (optional but present if applicable)
    rally_velocity: Optional[RallyVelocityResult] = None

    # Risk
    risk: RiskSizing
    entry: EntryTarget
    horizon: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM

    # Exit rules
    invalidation: list[InvalidationRule] = Field(default_factory=list)
    correlation_warnings: list[CorrelationWarning] = Field(default_factory=list)

    # Key risk factors (human-readable)
    key_risk_factors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scanner result (market-accumulation-scanner output)
# ---------------------------------------------------------------------------


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
    """Output of a single ticker scan from market-accumulation-scanner."""

    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    universe: str = ""
    final_score: float = Field(..., ge=0.0, le=100.0)
    dimensions: list[DimensionScore] = Field(default_factory=list)
    sentiment_breakdown: Optional[SentimentSubScores] = None
    flags: list[str] = Field(default_factory=list,
                             description="e.g. 'value_trap', 'vertical_rally', 'squeeze_candidate'")


class ScannerBatchResult(BaseModel):
    """Aggregate output of a scanner run over a universe."""

    universe: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tickers_scanned: int
    tickers_passed: int  # met min_score threshold
    min_score_threshold: int = 50
    results: list[ScannerResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Trade log (feedback loop)
# ---------------------------------------------------------------------------


class TradeLogEntry(BaseModel):
    """A single trade record for the feedback loop."""

    trade_id: str = Field(..., description="Unique trade identifier (UUID4)")
    ticker: str
    verdict_snapshot: UnifiedVerdict
    # Entry
    entry_date: Optional[datetime] = None
    entry_price: Optional[float] = None
    position_size_pct: Optional[float] = None
    # Exit
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = Field(
        None, description="'target_1', 'target_2', 'stop_loss', 'invalidation', 'time', 'manual'"
    )
    pnl_pct: Optional[float] = None
    notes: Optional[str] = None
    is_open: bool = True


# ---------------------------------------------------------------------------
# Options strategy (from options-strategy-suggestions)
# ---------------------------------------------------------------------------


class IVRegime(str, Enum):
    """Implied Volatility regime classification."""

    LOW = "low"        # IV Rank < 20
    NORMAL = "normal"  # IV Rank 20-80
    HIGH = "high"      # IV Rank > 80


class TermStructureShape(str, Enum):
    """IV term structure shape."""

    CONTANGO = "contango"
    BACKWARDATION = "backwardation"
    FLAT = "flat"


class IVTermStructureResult(BaseModel):
    """Phase 3.1 IV term structure analysis."""

    iv_rank: float = Field(..., ge=0.0, le=100.0)
    iv_percentile: float = Field(..., ge=0.0, le=100.0)
    current_atm_iv: float
    regime: IVRegime
    shape: TermStructureShape
    expirations: list[dict[str, float]] = Field(
        default_factory=list,
        description="[{date: str, atm_iv: float, call_skew: float, put_skew: float}]"
    )


class GexResult(BaseModel):
    """Phase 3.2 Gamma Exposure analysis."""

    total_gex: Optional[float] = None
    regime: str = "unknown"  # "positive", "negative", "neutral"
    gamma_flip_point: Optional[float] = None
    max_pain: Optional[float] = None
    call_wall_strike: Optional[float] = None
    put_wall_strike: Optional[float] = None


class StrategySuggestion(BaseModel):
    """Output of options-strategy-suggestions."""

    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Input data
    verdict: UnifiedVerdict
    iv_result: IVTermStructureResult
    gex_result: Optional[GexResult] = None
    days_to_earnings: Optional[int] = None
    # Strategy
    strategy_name: str
    strategy_description: str
    legs: list[dict[str, object]] = Field(
        default_factory=list,
        description="Each leg: {type, strike, expiry, action, premium}"
    )
    rationale: list[str] = Field(default_factory=list)
    # Risk
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    # Warnings
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Watchlist / score evolution
# ---------------------------------------------------------------------------


class ScoreSnapshot(BaseModel):
    """A single scan score snapshot for a ticker."""

    date: datetime
    score: float = Field(..., ge=0.0, le=100.0)
    dimensions: dict[str, float] = Field(default_factory=dict)


class WatchlistEntry(BaseModel):
    """Score evolution history for a ticker."""

    ticker: str
    history: list[ScoreSnapshot] = Field(default_factory=list)
    trend: str = "new"  # "improving", "stable", "deteriorating", "new"
    score_delta_7d: float = 0.0
    score_delta_30d: float = 0.0
    alerts: list[str] = Field(default_factory=list)


class WatchlistState(BaseModel):
    """Persistent watchlist state (Phase 2.2)."""

    last_updated: datetime = Field(default_factory=datetime.utcnow)
    tickers: dict[str, WatchlistEntry] = Field(default_factory=dict)
