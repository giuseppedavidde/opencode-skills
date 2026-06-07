"""Basic validation tests for schemas.py models.

Run: python3 schemas_test.py
"""
from __future__ import annotations

from schemas import (
    DimensionScore,
    Direction,
    EntryTarget,
    MacroCondition,
    MacroScore,
    MacroWindow,
    MultiTfAlignment,
    MultiTimeframeResult,
    RiskLevel,
    RiskSizing,
    ScannerResult,
    SentimentSubScores,
    UnifiedVerdict,
    Verdict,
    WatchlistEntry,
    WatchlistState,
)


def test_dimension_score() -> None:
    """Verify DimensionScore creation."""
    d = DimensionScore(name="Wyckoff Phase", weight=0.15, score=72,
                       detail="Phase C Spring detected")
    assert d.name == "Wyckoff Phase"
    assert d.weight == 0.15


def test_macro_score() -> None:
    """Verify MacroScore with conditions."""
    c = MacroCondition(name="Fed Policy", description="Rates stable", met=True, points=2)
    m = MacroScore(
        total=14, window=MacroWindow.FULL, conditions=[c],
        vix_value=18.5, fear_greed_index=42,
    )
    assert m.window == MacroWindow.FULL
    assert len(m.conditions) == 1


def test_unified_verdict() -> None:
    """Verify full UnifiedVerdict creation and fields."""
    uv = UnifiedVerdict(
        ticker="AAPL",
        is_crypto=False,
        composite_score=76.5,
        analysis_score=74.0,
        macro_score=14,
        verdict=Verdict.LONG_TERM,
        direction=Direction.LONG,
        dimensions=[
            DimensionScore(name="Wyckoff Phase", weight=0.15, score=80, detail="Phase D"),
        ],
        macro=MacroScore(total=14, window=MacroWindow.FULL),
        multi_timeframe=MultiTimeframeResult(alignment=MultiTfAlignment.ALIGNED_BULL),
        risk=RiskSizing(max_position_pct=7.0, stop_loss_pct=5.0, max_leverage=1.5),
        entry=EntryTarget(entry_min=150.0, entry_max=155.0, stop_loss=142.0,
                          target_1=165.0, target_2=180.0),
        horizon="6-12 mesi",
        risk_level=RiskLevel.MEDIUM,
        key_risk_factors=["Earnings tra 3 settimane", "VIX in aumento"],
    )
    assert uv.ticker == "AAPL"
    assert uv.verdict == Verdict.LONG_TERM
    assert uv.risk.max_position_pct == 7.0


def test_scanner_result() -> None:
    """Verify ScannerResult with sentiment breakdown."""
    sr = ScannerResult(
        ticker="MSFT", universe="us_large", final_score=81.0,
        dimensions=[
            DimensionScore(name="Wyckoff", weight=0.15, score=72, detail=""),
        ],
        sentiment_breakdown=SentimentSubScores(
            short_interest=65.0, institutional=70.0, web_news=55.0,
        ),
    )
    assert sr.final_score == 81.0
    assert sr.sentiment_breakdown is not None
    assert sr.sentiment_breakdown.institutional == 70.0


def test_watchlist_state() -> None:
    """Verify WatchlistState persistence."""
    ws = WatchlistState()
    ws.tickers["AAPL"] = WatchlistEntry(
        ticker="AAPL", trend="improving",
        score_delta_7d=4.5, score_delta_30d=12.0,
    )
    assert len(ws.tickers) == 1


def test_json_serialization() -> None:
    """All models should round-trip through JSON."""
    uv = UnifiedVerdict(
        ticker="AAPL", is_crypto=False,
        composite_score=76.5, analysis_score=74.0, macro_score=14,
        verdict=Verdict.LONG_TERM, direction=Direction.LONG,
        macro=MacroScore(total=14, window=MacroWindow.FULL),
        multi_timeframe=MultiTimeframeResult(alignment=MultiTfAlignment.ALIGNED_BULL),
        risk=RiskSizing(max_position_pct=7.0, stop_loss_pct=5.0, max_leverage=1.5),
        entry=EntryTarget(),
        horizon="6-12 mesi",
        risk_level=RiskLevel.MEDIUM,
    )
    raw = uv.model_dump_json()
    assert "AAPL" in raw
    parsed = UnifiedVerdict.model_validate_json(raw)
    assert parsed.ticker == "AAPL"
    assert parsed.composite_score == 76.5


def test_cross_reference() -> None:
    """Verify enum member counts."""
    assert len(Verdict.__members__) == 4
    assert len(MacroWindow.__members__) == 4
    assert len(Direction.__members__) == 3
    assert len(RiskLevel.__members__) == 3


if __name__ == "__main__":
    test_dimension_score()
    test_macro_score()
    test_unified_verdict()
    test_scanner_result()
    test_watchlist_state()
    test_json_serialization()
    test_cross_reference()
    print("\u2713 All schema tests passed")
