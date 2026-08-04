"""P1 tests: risk-free rate provider, calibration, universe metadata,
Bakshi VRP calibration status, ablation.

All tests are offline — no network calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

_MCP_SRC = Path("/home/giuseppe/Progetti/Github/opencode-skills/mcp/src")
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

# Mock fastmcp before any trading_mcp imports happen
_FASTMCP = MagicMock()
sys.modules["fastmcp"] = _FASTMCP


# ── A) Risk-Free Rate Provider ──────────────────────────────────────────

class TestRiskFreeSnapshot:
    """RiskFreeSnapshot model: rate_decimal, rate_pct, is_live, is_stale."""

    def test_live_snapshot_has_no_fallback(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeSnapshot

        snap = RiskFreeSnapshot(value=0.045, fallback_reason=None)
        assert snap.is_live is True
        assert snap.rate_decimal() == 0.045
        assert snap.rate_pct() == 4.5

    def test_fallback_snapshot_is_not_live(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeSnapshot

        snap = RiskFreeSnapshot(
            value=0.045,
            fallback_reason="^IRX fetch failed: timeout",
        )
        assert snap.is_live is False
        assert snap.fallback_reason == "^IRX fetch failed: timeout"

    def test_stale_flag(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeSnapshot

        snap = RiskFreeSnapshot(value=0.05, stale=True)
        assert snap.is_stale is True

        snap2 = RiskFreeSnapshot(value=0.05, stale=False)
        assert snap2.is_stale is False

    def test_rate_pct_conversion(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeSnapshot

        snap = RiskFreeSnapshot(value=0.0525)
        assert snap.rate_pct() == 5.25
        assert snap.rate_decimal() == 0.0525

    def test_value_bounds(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeSnapshot

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RiskFreeSnapshot(value=1.5)

        with pytest.raises(ValidationError):
            RiskFreeSnapshot(value=-0.1)


class TestRiskFreeProvider:
    """RiskFreeProvider: cache, TTL, fallback, force_refresh."""

    def test_cache_hit_within_ttl(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeProvider, RiskFreeSnapshot

        provider = RiskFreeProvider(ttl_seconds=3600)
        recent = datetime.now(timezone.utc).isoformat()
        snap = RiskFreeSnapshot(
            value=0.048,
            fetched_at=recent,
            fallback_reason=None,
        )
        provider._snapshot = snap

        result = provider.get_rate()
        assert result.value == 0.048
        assert result.is_live is True

    def test_force_refresh_calls_fetch(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeProvider, RiskFreeSnapshot

        provider = RiskFreeProvider(ttl_seconds=3600)
        provider._snapshot = RiskFreeSnapshot(
            value=0.10,
            fetched_at="2026-08-04T10:00:00+00:00",
        )

        live_snap = RiskFreeSnapshot(
            value=0.045,
            source_ticker="^IRX",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            fallback_reason=None,
            stale=False,
        )

        with patch.object(provider, "_fetch_live", return_value=live_snap):
            result = provider.get_rate(force_refresh=True)

        assert result.value == 0.045
        assert result.is_live is True

    def test_fetch_failure_uses_fallback(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeProvider

        provider = RiskFreeProvider(ttl_seconds=3600)

        with patch.object(
            provider, "_fetch_live", side_effect=ValueError("Network error")
        ):
            result = provider.get_rate(force_refresh=True)

        assert result.is_live is False
        assert result.fallback_reason is not None
        assert "Network error" in result.fallback_reason
        assert result.stale is True
        assert result.value == 0.045  # fallback 4.5%

    def test_invalidate_clears_cache(self) -> None:
        from trading_mcp.data.risk_free import RiskFreeProvider, RiskFreeSnapshot

        provider = RiskFreeProvider(ttl_seconds=3600)
        provider._snapshot = RiskFreeSnapshot(value=0.10)

        live_snap = RiskFreeSnapshot(
            value=0.045,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            fallback_reason=None,
        )

        provider.invalidate()
        assert provider._snapshot is None

        with patch.object(provider, "_fetch_live", return_value=live_snap):
            result = provider.get_rate()

        assert result.value == 0.045

    def test_singleton_provider(self) -> None:
        from trading_mcp.data.risk_free import (
            get_risk_free_provider,
            get_risk_free_rate,
        )
        from trading_mcp.data.risk_free import _risk_free_provider

        # Reset singleton
        import trading_mcp.data.risk_free as rf
        rf._risk_free_provider = None

        provider = get_risk_free_provider()
        assert provider is not None

        # singleton: second call returns same instance
        provider2 = get_risk_free_provider()
        assert provider is provider2


# ── B) Calibration ──────────────────────────────────────────────────────

class TestCalibrationArtifact:
    """CalibrationArtifact: save, load, calibrate, metadata."""

    def test_not_calibrated_returns_none(self) -> None:
        from calibration import CalibrationArtifact  # type: ignore[import-untyped]

        artifact = CalibrationArtifact(ticker="AAPL")
        assert artifact.calibrate(50.0) is None

    def test_calibrated_interpolation(self) -> None:
        from calibration import (
            CalibrationArtifact,
            CalibrationStatus,
        )

        artifact = CalibrationArtifact(
            ticker="AAPL",
            status=CalibrationStatus.CALIBRATED,
            isotonic_X=[0.0, 50.0, 100.0],
            isotonic_Y=[0.0, 0.5, 1.0],
        )

        prob = artifact.calibrate(50.0)
        assert prob == 0.5

        prob_low = artifact.calibrate(0.0)
        assert prob_low == 0.0

        prob_high = artifact.calibrate(100.0)
        assert prob_high == 1.0

        prob_mid = artifact.calibrate(75.0)
        assert 0.5 < prob_mid < 1.0

    def test_save_and_load_roundtrip(self) -> None:
        from calibration import (
            CalibrationArtifact,
            CalibrationStatus,
        )

        artifact = CalibrationArtifact(
            ticker="TEST",
            status=CalibrationStatus.CALIBRATED,
            isotonic_X=[0.0, 50.0, 100.0],
            isotonic_Y=[0.0, 0.5, 1.0],
            calibration_start="2020-01-01",
            calibration_end="2022-12-31",
            oos_start="2023-01-01",
            oos_end="2024-12-31",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            artifact.save(path)
            loaded = CalibrationArtifact.load(path)
            assert loaded.ticker == "TEST"
            assert loaded.status == CalibrationStatus.CALIBRATED
            assert loaded.isotonic_X == [0.0, 50.0, 100.0]
            assert loaded.calibrate(50.0) == 0.5
        finally:
            path.unlink(missing_ok=True)

    def test_load_nonexistent_raises(self) -> None:
        from calibration import CalibrationArtifact

        with pytest.raises(FileNotFoundError):
            CalibrationArtifact.load("/tmp/nonexistent_calibration.json")

    def test_isotonic_validation_mismatched_arrays(self) -> None:
        from calibration import (
            CalibrationArtifact,
            CalibrationStatus,
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CalibrationArtifact(
                ticker="X",
                status=CalibrationStatus.CALIBRATED,
                isotonic_X=[0.0, 100.0],
                isotonic_Y=[0.0, 0.5, 1.0],  # mismatched length
            )

    def test_calibrate_out_of_range_clamps(self) -> None:
        from calibration import (
            CalibrationArtifact,
            CalibrationStatus,
        )

        artifact = CalibrationArtifact(
            ticker="TEST",
            status=CalibrationStatus.CALIBRATED,
            isotonic_X=[10.0, 90.0],
            isotonic_Y=[0.1, 0.9],
        )

        assert artifact.calibrate(-5.0) == 0.1
        assert artifact.calibrate(150.0) == 0.9


class TestCalibrationIsotonic:
    """calibrate_isotonic: temporal split, min samples, metrics."""

    def test_insufficient_total_samples(self) -> None:
        from calibration import (
            calibrate_isotonic,
            CalibrationStatus,
        )

        scores = np.linspace(0, 100, 50)
        labels = np.random.RandomState(42).binomial(1, 0.5, 50)
        dates = [f"2023-{i // 30 + 1:02d}-{(i % 28) + 1:02d}" for i in range(50)]

        artifact = calibrate_isotonic(
            scores, labels, dates,
            calibration_end_date="2023-06-01",
            min_calibration=100, min_oos=50,
        )
        assert artifact.status == CalibrationStatus.INSUFFICIENT_DATA

    def test_insufficient_oos_samples(self) -> None:
        from calibration import (
            calibrate_isotonic,
            CalibrationStatus,
        )

        n = 200
        rng = np.random.RandomState(42)
        scores = rng.uniform(0, 100, n)
        labels = rng.binomial(1, 0.5, n)
        dates = [
            f"2023-{(i % 6) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)
        ]

        artifact = calibrate_isotonic(
            scores, labels, dates,
            calibration_end_date="2023-01-01",
            min_calibration=10, min_oos=200,
        )
        assert artifact.status == CalibrationStatus.INSUFFICIENT_DATA

    def test_successful_calibration(self) -> None:
        from calibration import (
            calibrate_isotonic,
            CalibrationStatus,
        )

        n = 500
        rng = np.random.RandomState(42)
        scores = rng.uniform(0, 100, n)
        # Create a signal: higher scores -> more likely label=1
        prob = 0.3 + 0.4 * (scores / 100.0)
        labels = rng.binomial(1, prob, n)
        # Temporal split: first 300 calibration, last 200 OOS
        dates = [f"2023-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]

        artifact = calibrate_isotonic(
            scores, labels, dates,
            calibration_end_date="2023-07-01",
            min_calibration=100, min_oos=50,
            ticker="TEST",
        )

        assert artifact.status == CalibrationStatus.CALIBRATED
        assert artifact.ticker == "TEST"
        assert len(artifact.isotonic_X) > 0
        assert len(artifact.isotonic_Y) > 0
        assert artifact.metrics.brier_score is not None
        assert artifact.metrics.log_loss is not None
        assert artifact.metrics.ece is not None
        assert artifact.metrics.n_calibration > 0
        assert artifact.metrics.n_oos >= 50
        assert artifact.calibration_start is not None
        assert artifact.oos_start is not None

    def test_temporal_split_enforcement(self) -> None:
        from calibration import calibrate_isotonic, CalibrationStatus

        n = 300
        rng = np.random.RandomState(42)
        scores = rng.uniform(0, 100, n)
        labels = rng.binomial(1, 0.5, n)
        dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2020-01-01", periods=n, freq="D")]

        artifact = calibrate_isotonic(
            scores, labels, dates,
            calibration_end_date="2021-01-01",
            min_calibration=100, min_oos=50,
        )

        assert artifact.status == CalibrationStatus.INSUFFICIENT_DATA
        assert any("OOS" in n or "oos" in str(n).lower() for n in (artifact.notes or []))


class TestCalibrationMetrics:
    """Brier, log-loss, ECE computation."""

    def test_brier_score_perfect(self) -> None:
        from calibration import compute_brier_score

        y_true = np.array([1.0, 1.0, 0.0, 0.0])
        y_prob = np.array([0.99, 0.99, 0.01, 0.01])
        brier = compute_brier_score(y_true, y_prob)
        assert brier < 0.01

    def test_log_loss_perfect(self) -> None:
        from calibration import compute_log_loss

        y_true = np.array([1.0, 0.0])
        y_prob = np.array([0.99, 0.01])
        logloss = compute_log_loss(y_true, y_prob)
        assert logloss < 0.1

    def test_ece_bins(self) -> None:
        from calibration import compute_ece

        rng = np.random.RandomState(42)
        n = 200
        y_prob = rng.uniform(0.1, 0.9, n)
        y_true = (rng.uniform(0, 1, n) < y_prob).astype(float)

        ece, bins = compute_ece(y_true, y_prob, n_bins=5)
        assert isinstance(ece, float)
        assert len(bins) == 5
        total_bin_counts = sum(b["count"] for b in bins)
        assert total_bin_counts == n


# ── D) Bakshi VRP calibration status ────────────────────────────────────

class TestBakshiResultP1:
    """BakshiResult P1 fields: calibration_status, calibrated, rate_source."""

    def test_default_is_not_calibrated(self) -> None:
        from trading_mcp.tools._quant_tools import BakshiResult

        r = BakshiResult(ticker="AAPL")
        assert r.calibration_status == "not_calibrated"
        assert r.calibrated is False
        assert r.calibrated_vrp is None

    def test_explicitly_not_calibrated(self) -> None:
        from trading_mcp.tools._quant_tools import BakshiResult

        r = BakshiResult(
            ticker="NVDA",
            calibration_status="not_calibrated",
            calibration_source="Bakshi & Kapadia (2003), Table 4 (S&P 500 only)",
            calibrated=False,
            calibrated_vrp=None,
            rate_source="^IRX",
            rate_as_of="2026-08-04T10:00:00+00:00",
        )
        d = r.model_dump()
        assert d["calibration_status"] == "not_calibrated"
        assert d["calibrated"] is False
        assert d["calibrated_vrp"] is None
        assert d["rate_source"] == "^IRX"

    def test_paper_reference_includes_calibration_source(self) -> None:
        from trading_mcp.tools._quant_tools import _VRP_CALIBRATION_SOURCE

        assert "S&P 500" in _VRP_CALIBRATION_SOURCE
        assert "Bakshi" in _VRP_CALIBRATION_SOURCE


# ── C) Universe metadata ────────────────────────────────────────────────

class TestUniverseMetadata:
    """UniverseMetadata: registry, backtest suitability, warnings."""

    def test_us_large_has_survivorship_warning(self) -> None:
        from trading_mcp.data.universe import get_universe_metadata

        meta = get_universe_metadata("us_large")
        assert meta is not None
        assert meta.survivorship_warning is True
        assert meta.universe_type.value == "current"
        assert meta.historical_universe_available is False

    def test_custom_universe_returns_none(self) -> None:
        from trading_mcp.data.universe import get_universe_metadata

        meta = get_universe_metadata("random_xyz")
        assert meta is None

    def test_check_backtest_rejects_current_universe(self) -> None:
        from trading_mcp.data.universe import check_backtest_universe

        is_suitable, reason = check_backtest_universe("italy")
        assert is_suitable is False
        assert "survivorship" in reason.lower()

    def test_historical_universe_unavailable_message(self) -> None:
        from trading_mcp.data.universe import historical_universe_unavailable_message

        msg = historical_universe_unavailable_message("us_large")
        assert "historical_universe_unavailable" in msg
        assert "us_large" in msg
        assert "survivorship" in msg.lower()

    def test_register_universe(self) -> None:
        from trading_mcp.data.universe import (
            UniverseMetadata,
            UniverseType,
            register_universe_metadata,
            get_universe_metadata,
        )

        meta = UniverseMetadata(
            name="test_historical",
            source="test.csv",
            as_of="2020-01-01",
            universe_type=UniverseType.HISTORICAL,
            survivorship_warning=False,
            historical_universe_available=True,
        )
        register_universe_metadata(meta)

        loaded = get_universe_metadata("test_historical")
        assert loaded is not None
        assert loaded.is_suitable_for_backtest is True


# ── E) Ablation ─────────────────────────────────────────────────────────

class TestAblation:
    """Feature ablation: insufficient evidence, real ablated comparison."""

    def test_no_ablated_scores_returns_insufficient_evidence(self) -> None:
        """Without ablated_scores, status is always INSUFFICIENT_EVIDENCE."""
        from calibration.ablation import run_ablation, AblationStatus

        rng = np.random.RandomState(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="B")
        scores = pd.Series(rng.uniform(0, 100, 200), index=dates)
        returns = pd.Series(rng.normal(0.001, 0.02, 200), index=dates)

        report = run_ablation(
            baseline_scores=scores,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-03-01",
            ablated_scores=None,
            min_oos=30,
            ticker="TEST",
        )
        assert report.status == AblationStatus.INSUFFICIENT_EVIDENCE
        assert report.ranked_by_importance == []
        assert "true ablation requires" in report.warnings[0].lower()

    def test_small_oos_returns_insufficient(self) -> None:
        """Small OOS window: insufficient even with ablated scores."""
        from calibration.ablation import run_ablation, AblationStatus

        rng = np.random.RandomState(42)
        dates = pd.date_range("2023-01-01", periods=50, freq="B")
        scores = pd.Series(rng.uniform(0, 100, 50), index=dates)
        returns = pd.Series(rng.normal(0.001, 0.02, 50), index=dates)
        ablated = {
            "momentum_vol": pd.Series(rng.uniform(0, 100, 50), index=dates),
        }

        report = run_ablation(
            baseline_scores=scores,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-04-01",
            ablated_scores=ablated,
            min_oos=100,
        )
        assert report.status == AblationStatus.INSUFFICIENT_EVIDENCE

    def test_with_ablated_scores_computes_comparison(self) -> None:
        """Provided ablated_scores: computes IC/hit-rate delta per group."""
        from calibration.ablation import run_ablation, AblationStatus

        rng = np.random.RandomState(42)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        # Baseline: slightly predictive (rho ~ 0.15)
        noise = rng.normal(0, 0.5, n)
        baseline = pd.Series(
            rng.uniform(0, 100, n) + 3 * (rng.normal(0, 1, n)),
            index=dates,
        )
        returns = pd.Series(
            rng.normal(0.001, 0.02, n) + 0.002 * (baseline - 50),
            index=dates,
        )

        # Ablated: slightly worse (less predictive, same noise scale)
        ablated_mom = pd.Series(
            rng.uniform(0, 100, n) + 1 * (rng.normal(0, 1, n)),
            index=dates,
        )
        ablated_vp = pd.Series(
            rng.uniform(0, 100, n) + 0.5 * (rng.normal(0, 1, n)),
            index=dates,
        )

        report = run_ablation(
            baseline_scores=baseline,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-03-01",
            ablated_scores={
                "momentum_vol": ablated_mom,
                "volume_profile": ablated_vp,
            },
            min_oos=30,
            ticker="TEST",
        )
        assert report.status == AblationStatus.OK
        assert report.baseline_ic_rank is not None
        assert report.baseline_hit_rate is not None
        assert len(report.groups) == 5  # all 5 groups in _FEATURE_GROUPS
        assert len(report.ranked_by_importance) == 5

        # Groups that received ablated_scores should have metrics
        mom_group = next(g for g in report.groups if g.group_name == "momentum_vol")
        assert mom_group.n_oos >= 30
        assert mom_group.status == "ok"
        assert mom_group.ablated_ic_rank is not None
        assert mom_group.ic_rank_delta is not None

        # Groups without ablated_scores should be marked insufficient
        macro_group = next(
            g for g in report.groups if g.group_name == "macro_options"
        )
        assert macro_group.status == "insufficient_evidence"
        assert "no ablated_scores" in macro_group.note.lower()

    def test_ic_delta_sign_direction(self) -> None:
        """IC delta = baseline − ablated; positive = group is useful."""
        from calibration.ablation import run_ablation, AblationStatus

        rng = np.random.RandomState(42)
        n = 300
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        base_noise = rng.normal(0, 1, n)
        truth = rng.normal(0.001, 0.02, n)

        # Baseline: correlated with truth
        baseline = pd.Series(
            50 + 10 * truth + 5 * base_noise, index=dates
        )
        # Ablated: less correlated with truth
        ablated = pd.Series(
            50 + 3 * truth + 7 * base_noise, index=dates
        )
        returns = pd.Series(truth, index=dates)

        report = run_ablation(
            baseline_scores=baseline,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-02-01",
            ablated_scores={"momentum_vol": ablated},
            min_oos=50,
            ticker="TEST",
        )
        assert report.status == AblationStatus.OK

        mom_group = next(
            g for g in report.groups if g.group_name == "momentum_vol"
        )
        assert mom_group.status == "ok"
        assert mom_group.ic_rank_delta is not None
        # Baseline is more correlated → IC delta should be positive
        assert mom_group.ic_rank_delta > 0, (
            f"Expected positive IC delta (baseline more predictive), "
            f"got {mom_group.ic_rank_delta}"
        )

    def test_empty_ablated_scores_dict_is_insufficient(self) -> None:
        """Empty dict {} is same as None: INSUFFICIENT_EVIDENCE."""
        from calibration.ablation import run_ablation, AblationStatus

        rng = np.random.RandomState(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="B")
        scores = pd.Series(rng.uniform(0, 100, 200), index=dates)
        returns = pd.Series(rng.normal(0.001, 0.02, 200), index=dates)

        report = run_ablation(
            baseline_scores=scores,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-03-01",
            ablated_scores={},
            min_oos=30,
        )
        assert report.status == AblationStatus.INSUFFICIENT_EVIDENCE

    def test_ablated_not_interpreted_as_importance_when_missing(self) -> None:
        """Ablation report must NOT suggest importance when missing
        ablated scores for any group — no fake ranking."""
        from calibration.ablation import run_ablation

        rng = np.random.RandomState(42)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        baseline = pd.Series(rng.uniform(0, 100, n), index=dates)
        returns = pd.Series(rng.normal(0.001, 0.02, n), index=dates)

        report = run_ablation(
            baseline_scores=baseline,
            forward_returns=returns,
            dates=dates,
            oos_cutoff="2023-03-01",
            ablated_scores=None,
            min_oos=30,
        )
        # Must NOT return OK with ranked_by_importance
        assert report.ranked_by_importance == []
        for g in report.groups:
            assert g.ic_rank_delta is None
            assert g.ablated_ic_rank is None


# ── LGBMResult calibration fields ───────────────────────────────────────

class TestLGBMResultP1:
    """LGBMResult now has calibrated_probability and calibration_status."""

    def test_default_is_not_calibrated(self) -> None:
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(ticker="AAPL")
        assert r.calibrated_probability is None
        assert r.calibration_status == "not_calibrated"

    def test_score_not_interpreted_as_probability(self) -> None:
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="AAPL",
            available=True,
            score=75.0,
            signal="strong_long",
        )
        assert r.calibrated_probability is None
        assert r.score == 75.0
        assert r.score != r.calibrated_probability  # explicit: score is NOT probability
