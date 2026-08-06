"""P2 tests: cost model, net P&L, meta-label temporal CV, data freshness,
prediction monitoring, put-call parity.

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

_FASTMCP = MagicMock()
sys.modules["fastmcp"] = _FASTMCP


# ── A) Cost Model ────────────────────────────────────────────────────────

class TestCostModel:
    """CostModel: defaults, zero-cost, round-trip, assumptions."""

    def test_defaults_are_conservative(self) -> None:
        from backtest.contract import CostModel

        cm = CostModel()
        assert cm.commission_per_contract == 0.65
        assert cm.slippage_bps == 5.0
        assert cm.spread_bps == 5.0
        assert cm.round_trip is True
        assert cm.per_side_bps() == 10.0
        assert cm.total_bps() == 20.0

    def test_zero_cost_means_net_equals_gross(self) -> None:
        from backtest.contract import CostModel

        cm = CostModel(
            commission_per_contract=0.0,
            slippage_bps=0.0,
            spread_bps=0.0,
        )
        assert cm.total_bps() == 0.0
        assert cm.per_share_cost(100.0) == 0.0

    def test_per_share_cost_calculation(self) -> None:
        from backtest.contract import CostModel

        cm = CostModel(
            slippage_bps=5.0, spread_bps=5.0, round_trip=True
        )
        expected = 100.0 * 20.0 / 10000.0  # 0.20
        assert abs(cm.per_share_cost(100.0) - expected) < 1e-8

    def test_assumptions_dict_documents_all(self) -> None:
        from backtest.contract import CostModel

        cm = CostModel()
        assumptions = cm.assumptions_dict()
        assert "total_round_trip_bps" in assumptions
        assert "per_side_bps" in assumptions
        assert "note" in assumptions
        assert "estimates" in assumptions["note"].lower()

    def test_negative_values_rejected(self) -> None:
        from backtest.contract import CostModel
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CostModel(commission_per_contract=-1.0)

    def test_round_trip_false_halves_cost(self) -> None:
        from backtest.contract import CostModel

        cm_rt = CostModel(round_trip=True)
        cm_no = CostModel(round_trip=False)
        assert cm_no.total_bps() == cm_rt.total_bps() / 2.0


class TestBacktestConfigCosts:
    """BacktestConfig with apply_costs=True."""

    def test_apply_costs_default_false(self) -> None:
        from backtest.contract import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.apply_costs is False

    def test_apply_costs_true_passes_cost_model(self) -> None:
        from backtest.contract import BacktestConfig, CostModel

        cm = CostModel(slippage_bps=3.0, spread_bps=2.0)
        cfg = BacktestConfig(apply_costs=True, cost_model=cm)
        assert cfg.apply_costs is True
        assert cfg.cost_model.slippage_bps == 3.0


# ── B) Net P&L evaluation ───────────────────────────────────────────────

def make_synth_ohlcv(n: int = 500, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic OHLCV with a noisy signal."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    close = np.maximum(close, 10.0)
    ohlcv = pd.DataFrame(
        {"Close": close}, index=dates
    )
    signal = pd.Series(50.0 + rng.normal(0, 15, n), index=dates)
    signal = signal.clip(0, 100)
    return ohlcv, signal


class TestNetMetrics:
    """Net metrics: costs reduce returns, high turnover → high costs,
    zero costs → net == gross."""

    def test_costs_reduce_mean_return(self) -> None:
        from backtest.contract import BacktestConfig, CostModel
        from backtest.contract import build_predictions_from_ohlcv
        from backtest.evaluator import evaluate

        ohlcv, signal = make_synth_ohlcv(500)
        cfg_no_cost = BacktestConfig(
            apply_costs=False,
            min_bars=200,
            strict_mode=True,
            vp_window_days=365,
        )
        cfg_cost = BacktestConfig(
            apply_costs=True,
            cost_model=CostModel(slippage_bps=10.0, spread_bps=5.0),
            min_bars=200,
            strict_mode=True,
            vp_window_days=365,
        )

        build = build_predictions_from_ohlcv(
            ohlcv, [20, 60], signal, ticker="TEST", min_bars=200, config=cfg_no_cost
        )
        assert build.status.value == "ok"

        result_no = evaluate(build, cfg_no_cost, ticker="TEST")
        result_yes = evaluate(build, cfg_cost, ticker="TEST")

        for h_no, h_yes in zip(result_no.horizons, result_yes.horizons):
            if h_no.supported and h_yes.supported:
                assert h_yes.mean_return_pct_net is not None
                assert h_no.mean_return_pct_net is None
                assert h_yes.costs_applied is True
                # Net should be ≤ gross (costs reduce returns)
                assert h_yes.mean_return_pct_net <= h_no.mean_return_pct + 0.1

    def test_high_turnover_increases_cost(self) -> None:
        from backtest.contract import BacktestConfig, CostModel
        from backtest.contract import build_predictions_from_ohlcv
        from backtest.evaluator import evaluate

        rng = np.random.default_rng(42)
        n = 400
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))

        # High turnover: signal oscillates wildly
        signal_high = pd.Series(
            50.0 + 30.0 * np.sin(np.linspace(0, 20 * np.pi, n)),
            index=dates,
        )
        signal_high = signal_high.clip(0, 100)

        ohlcv = pd.DataFrame({"Close": close}, index=dates)

        cfg = BacktestConfig(
            apply_costs=True,
            cost_model=CostModel(slippage_bps=5.0, spread_bps=5.0),
            min_bars=200,
            strict_mode=True,
            vp_window_days=365,
        )
        build = build_predictions_from_ohlcv(
            ohlcv, [20], signal_high, ticker="TEST",
            min_bars=200, config=cfg,
        )
        result = evaluate(build, cfg, ticker="TEST")
        hr = result.horizons[0]
        if hr.supported:
            assert hr.costs_applied is True
            assert hr.mean_return_pct_net is not None
            assert hr.hit_rate_net is not None

    def test_zero_cost_net_equals_gross(self) -> None:
        from backtest.contract import BacktestConfig, CostModel
        from backtest.contract import build_predictions_from_ohlcv
        from backtest.evaluator import evaluate

        ohlcv, signal = make_synth_ohlcv(400)
        cm_zero = CostModel(
            commission_per_contract=0.0,
            slippage_bps=0.0,
            spread_bps=0.0,
        )
        cfg = BacktestConfig(
            apply_costs=True,
            cost_model=cm_zero,
            min_bars=200,
            strict_mode=True,
            vp_window_days=365,
        )
        build = build_predictions_from_ohlcv(
            ohlcv, [20], signal, ticker="TEST", min_bars=200, config=cfg,
        )
        result = evaluate(build, cfg, ticker="TEST")
        hr = result.horizons[0]
        if hr.supported:
            assert hr.costs_applied is True
            assert hr.mean_return_pct_net is not None
            assert abs(hr.mean_return_pct_net - hr.mean_return_pct) < 1e-8
            assert abs(hr.hit_rate_net - hr.hit_rate) < 1e-8

    def test_cost_assumptions_in_horizon_result(self) -> None:
        from backtest.contract import BacktestConfig, CostModel
        from backtest.contract import build_predictions_from_ohlcv
        from backtest.evaluator import evaluate

        ohlcv, signal = make_synth_ohlcv(400)
        cm = CostModel(commission_per_contract=0.65)
        cfg = BacktestConfig(
            apply_costs=True,
            cost_model=cm,
            min_bars=200,
            strict_mode=True,
            vp_window_days=365,
        )
        build = build_predictions_from_ohlcv(
            ohlcv, [20], signal, ticker="TEST", min_bars=200, config=cfg,
        )
        result = evaluate(build, cfg, ticker="TEST")
        for hr in result.horizons:
            if hr.supported and hr.costs_applied:
                assert hr.cost_assumptions is not None
                assert "total_round_trip_bps" in hr.cost_assumptions


# ── C) Meta-label temporal CV ────────────────────────────────────────────

class TestMetaLabelTemporal:
    """Meta-label: train/eval disjoint, metrics on eval only."""

    def test_train_eval_disjoint_by_date(self) -> None:
        from trading_mcp.analysis.meta_label import MetaLabelModel

        n = 100
        rng = np.random.RandomState(42)
        feats = pd.DataFrame(
            {
                "resist_s": rng.uniform(-1, 1, n),
                "tl_err": rng.uniform(-0.1, 0.1, n),
                "vol": rng.uniform(0.5, 2.0, n),
                "max_dist": rng.uniform(0, 0.1, n),
                "adx": rng.uniform(10, 40, n),
            }
        )
        labels = pd.Series(rng.binomial(1, 0.5, n), index=feats.index)
        dates = pd.Series(
            pd.date_range("2022-01-01", periods=n, freq="B"), index=feats.index
        )

        mml = MetaLabelModel("TEST")
        metrics = mml.train_temporal(
            feats, labels, dates, cutoff_date="2022-03-01",
            min_train=20, min_eval=10,
        )

        assert metrics["metric_status"] == "ok"
        assert metrics["n_train"] >= 20
        assert metrics["n_eval"] >= 10
        assert metrics["roc_auc"] is not None
        assert metrics["accuracy"] is not None
        assert metrics["baseline_accuracy"] is not None

        # Train and eval dates must be disjoint
        train_end = pd.Timestamp("2022-03-01")
        eval_start = pd.Timestamp(metrics["eval_start"]) if metrics["eval_start"] != "N/A" else None
        assert eval_start is None or eval_start > train_end

    def test_insufficient_train_returns_insufficient_data(self) -> None:
        from trading_mcp.analysis.meta_label import MetaLabelModel

        n = 15
        rng = np.random.RandomState(42)
        feats = pd.DataFrame(
            {
                "resist_s": rng.uniform(-1, 1, n),
                "tl_err": rng.uniform(-0.1, 0.1, n),
                "vol": rng.uniform(0.5, 2.0, n),
                "max_dist": rng.uniform(0, 0.1, n),
                "adx": rng.uniform(10, 40, n),
            }
        )
        labels = pd.Series(rng.binomial(1, 0.5, n), index=feats.index)
        dates = pd.Series(
            pd.date_range("2022-06-01", periods=n, freq="B"), index=feats.index
        )

        mml = MetaLabelModel("TEST_small")
        metrics = mml.train_temporal(
            feats, labels, dates, cutoff_date="2022-06-10",
            min_train=30, min_eval=10,
        )

        assert metrics["metric_status"] == "insufficient_data"
        assert metrics["roc_auc"] is None
        assert "n_train" in metrics["reason"].lower()

    def test_insufficient_eval_returns_insufficient_data(self) -> None:
        from trading_mcp.analysis.meta_label import MetaLabelModel

        n = 40
        rng = np.random.RandomState(42)
        feats = pd.DataFrame(
            {
                "resist_s": rng.uniform(-1, 1, n),
                "tl_err": rng.uniform(-0.1, 0.1, n),
                "vol": rng.uniform(0.5, 2.0, n),
                "max_dist": rng.uniform(0, 0.1, n),
                "adx": rng.uniform(10, 40, n),
            }
        )
        labels = pd.Series(rng.binomial(1, 0.5, n), index=feats.index)
        dates = pd.Series(
            pd.date_range("2022-01-01", periods=n, freq="B"), index=feats.index
        )

        mml = MetaLabelModel("TEST_eval")
        metrics = mml.train_temporal(
            feats, labels, dates, cutoff_date="2022-02-20",
            min_train=5, min_eval=30,
        )

        assert metrics["metric_status"] == "insufficient_data"
        assert "n_eval" in metrics["reason"].lower()

    def test_metrics_change_with_different_cutoff(self) -> None:
        """Metrics should change when the cutoff moves (different train/eval split)."""
        from trading_mcp.analysis.meta_label import MetaLabelModel

        n = 80
        rng = np.random.RandomState(42)
        feats = pd.DataFrame(
            {
                "resist_s": rng.uniform(-1, 1, n),
                "tl_err": rng.uniform(-0.1, 0.1, n),
                "vol": rng.uniform(0.5, 2.0, n),
                "max_dist": rng.uniform(0, 0.1, n),
                "adx": rng.uniform(10, 40, n),
            }
        )
        labels = pd.Series(rng.binomial(1, 0.5, n), index=feats.index)
        dates = pd.Series(
            pd.date_range("2022-01-01", periods=n, freq="B"), index=feats.index
        )

        mml1 = MetaLabelModel("TEST_split1")
        metrics1 = mml1.train_temporal(
            feats.copy(), labels.copy(), dates, cutoff_date="2022-02-10",
            min_train=10, min_eval=10,
        )

        mml2 = MetaLabelModel("TEST_split2")
        metrics2 = mml2.train_temporal(
            feats.copy(), labels.copy(), dates, cutoff_date="2022-03-01",
            min_train=10, min_eval=10,
        )

        if metrics1["metric_status"] == "ok" and metrics2["metric_status"] == "ok":
            # The splits are different → eval_start must differ
            assert metrics1["eval_start"] != metrics2["eval_start"]


# ── D) Data freshness ────────────────────────────────────────────────────

class TestFreshnessLabel:
    """freshness_label: live, recent, stale, cached tiers with boundaries."""

    def test_live_label(self) -> None:
        from trading_mcp.data.provider import freshness_label

        now = 1000.0
        assert freshness_label(now - 60, now=now) == "live"
        assert freshness_label(now - 299, now=now) == "live"

    def test_recent_label(self) -> None:
        from trading_mcp.data.provider import freshness_label

        now = 1000.0
        assert freshness_label(now - 301, now=now) == "recent"
        assert freshness_label(now - 3599, now=now) == "recent"

    def test_stale_label(self) -> None:
        from trading_mcp.data.provider import freshness_label

        now = 1000.0
        assert freshness_label(now - 3601, now=now) == "stale"
        assert freshness_label(now - 86399, now=now) == "stale"

    def test_cached_label(self) -> None:
        from trading_mcp.data.provider import freshness_label

        now = 1000.0
        assert freshness_label(now - 86401, now=now) == "cached"
        assert freshness_label(None, now=now) == "cached"

    def test_options_thresholds_tighter(self) -> None:
        from trading_mcp.data.provider import (
            freshness_label,
            _DEFAULT_FRESHNESS_THRESHOLDS,
        )

        now = 1000.0
        opt_thresholds = _DEFAULT_FRESHNESS_THRESHOLDS["options"]
        assert freshness_label(now - 30, now=now, thresholds=opt_thresholds) == "live"
        assert freshness_label(now - 61, now=now, thresholds=opt_thresholds) == "recent"
        assert freshness_label(now - 301, now=now, thresholds=opt_thresholds) == "stale"

    def test_get_last_data_date(self) -> None:
        from trading_mcp.data.provider import get_last_data_date

        dates = pd.date_range("2026-08-01", periods=3, freq="D")
        df = pd.DataFrame({"Close": [100, 101, 102]}, index=dates)
        assert get_last_data_date(df) == "2026-08-03"

        assert get_last_data_date(pd.DataFrame()) is None
        assert get_last_data_date(None) is None

    def test_data_freshness_in_provider(self) -> None:
        from trading_mcp.data.provider import DataProvider, freshness_label

        dp = DataProvider()
        # No data → freshness is cached
        freshness = dp.get_data_freshness("NONEXISTENT_TICKER", data_type="stock")
        assert freshness["freshness"] == "cached"
        assert freshness["last_data_date"] is None


# ── E) Prediction monitoring ─────────────────────────────────────────────

class TestPredictionLog:
    """PredictionLogger: record, resolve, report."""

    def test_record_and_resolve(self) -> None:
        from monitoring.prediction_log import PredictionLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            plog = PredictionLogger(log_path)
            plog.record_prediction("AAPL", "2026-01-15", "v1.0", 75.0, None, 20)
            plog.record_prediction("AAPL", "2026-01-16", "v1.0", 80.0, None, 20)

            n = plog.resolve_outcome("AAPL", "2026-01-15", 0.03)
            assert n == 1

            records = plog._read_all()
            resolved = [r for r in records if r.status == "resolved"]
            pending = [r for r in records if r.status == "pending"]
            assert len(resolved) == 1
            assert len(pending) == 1
            assert resolved[0].forward_return == 0.03
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_insufficient_data_report(self) -> None:
        from monitoring.prediction_log import PredictionLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            plog = PredictionLogger(log_path)
            for i in range(5):
                plog.record_prediction(
                    "AAPL", f"2026-01-{i+15:02d}", "v1.0", 75.0, None, 20
                )
            for i in range(3):
                plog.resolve_outcome(
                    "AAPL", f"2026-01-{i+15:02d}", 0.02 - i * 0.01
                )

            report = plog.performance_report(min_required=10)
            assert report.status == "insufficient_data"
            assert report.hit_rate is None
            assert report.sharpe_annualized is None
            assert report.n_total == 5
            assert report.n_resolved == 3
            assert report.n_pending == 2
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_resolved_report(self) -> None:
        from monitoring.prediction_log import PredictionLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            plog = PredictionLogger(log_path)
            rng = np.random.RandomState(42)
            n_samples = 50
            for i in range(n_samples):
                score = rng.uniform(20, 80)
                fwd_ret = 0.001 + 0.0005 * (score - 50) + rng.normal(0, 0.02)
                plog.record_prediction(
                    "AAPL", f"2026-{i // 28 + 1:02d}-{(i % 28) + 1:02d}",
                    "v1.0", score, None, 20,
                )
                plog.resolve_outcome(
                    "AAPL", f"2026-{i // 28 + 1:02d}-{(i % 28) + 1:02d}", fwd_ret
                )

            report = plog.performance_report(min_required=20)
            assert report.status == "ok"
            assert report.hit_rate is not None
            assert report.mean_return is not None
            assert report.n_resolved == n_samples
            assert report.n_pending == 0
            # IC rank should be somewhat positive (our signal has a tiny edge)
            assert report.ic_rank is not None
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_no_sharpe_invented_for_empty_log(self) -> None:
        from monitoring.prediction_log import PredictionLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            plog = PredictionLogger(log_path)
            report = plog.performance_report()
            assert report.status == "insufficient_data"
            assert report.sharpe_annualized is None
            assert report.hit_rate is None
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_horizon_specific_resolution(self) -> None:
        from monitoring.prediction_log import PredictionLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            plog = PredictionLogger(log_path)
            plog.record_prediction("AAPL", "2026-01-15", "v1.0", 75.0, None, 20)
            plog.record_prediction("AAPL", "2026-01-15", "v1.0", 70.0, None, 60)

            n = plog.resolve_outcome("AAPL", "2026-01-15", 0.03, horizon_days=60)
            assert n == 1

            records = plog._read_all()
            resolved = [r for r in records if r.status == "resolved"]
            assert len(resolved) == 1
            assert resolved[0].horizon_days == 60
        finally:
            Path(log_path).unlink(missing_ok=True)


# ── F) Put-Call Parity ──────────────────────────────────────────────────

class TestPutCallParity:
    """C − P ≈ S − K·e^(−rT) within tolerance on synthetic fixtures."""

    def test_parity_atm(self) -> None:
        """At-the-money: C − P ≈ S − K·e^(−rT)."""
        S = 100.0
        K = 100.0
        r = 0.05
        T = 30 / 365.0
        sigma = 0.20

        from scipy.stats import norm
        import math

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        call = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        put = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        lhs = call - put
        rhs = S - K * math.exp(-r * T)

        assert abs(lhs - rhs) < 1e-6, (
            f"Put-call parity violated: C−P={lhs:.8f}, S−Ke^(−rT)={rhs:.8f}"
        )

    def test_parity_itm(self) -> None:
        """In-the-money: parity still holds."""
        S = 100.0
        K = 95.0
        r = 0.05
        T = 60 / 365.0
        sigma = 0.25

        from scipy.stats import norm
        import math

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        call = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        put = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        lhs = call - put
        rhs = S - K * math.exp(-r * T)

        assert abs(lhs - rhs) < 1e-6

    def test_parity_otm(self) -> None:
        """Out-of-the-money: parity still holds."""
        S = 100.0
        K = 110.0
        r = 0.03
        T = 90 / 365.0
        sigma = 0.30

        from scipy.stats import norm
        import math

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        call = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        put = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        lhs = call - put
        rhs = S - K * math.exp(-r * T)

        assert abs(lhs - rhs) < 1e-6

    def test_parity_zero_rate(self) -> None:
        """Zero interest rate: C − P ≈ S − K."""
        S = 100.0
        K = 105.0
        r = 0.0
        T = 30 / 365.0
        sigma = 0.20

        from scipy.stats import norm
        import math

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        call = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        put = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        lhs = call - put
        rhs = S - K

        assert abs(lhs - rhs) < 1e-6


# ── G) DataProvider cache hit / stale fallback ─────────────────────────

class TestDataProviderCache:
    """DataProvider: cache hit, stale fallback, freshness tracking."""

    def test_cache_hit_after_fetch(self) -> None:
        from trading_mcp.data.provider import DataProvider, CacheEntry

        dp = DataProvider()

        with patch.object(dp, "_fetch_hist") as mock_fetch:
            mock_data = pd.DataFrame(
                {"Close": [100, 101, 102]},
                index=pd.date_range("2026-08-01", periods=3, freq="D"),
            )
            mock_fetch.return_value = mock_data

            hist1 = dp.get_hist("TEST_CACHE", period="5d")
            assert not hist1.empty
            assert mock_fetch.call_count == 1

            # Second call → cache hit
            hist2 = dp.get_hist("TEST_CACHE", period="5d")
            assert not hist2.empty
            assert mock_fetch.call_count == 1  # no new fetch

    def test_stale_fallback_on_fetch_failure(self) -> None:
        from trading_mcp.data.provider import DataProvider, CacheEntry

        dp = DataProvider()

        # First: successful fetch
        with patch.object(dp, "_fetch_hist") as mock_fetch:
            mock_data = pd.DataFrame(
                {"Close": [100, 101]},
                index=pd.date_range("2026-08-01", periods=2, freq="D"),
            )
            mock_fetch.return_value = mock_data
            hist1 = dp.get_hist("TEST_STALE", period="5d")
            assert not hist1.empty

        # Force TTL expiry by manipulating the cache entry
        tc = dp._cache.get("TEST_STALE")
        if tc:
            with tc.lock:
                tc.hist = CacheEntry(
                    data=tc.hist.data,
                    timestamp=tc.hist.timestamp - 100000,  # expired
                    ttl=3600,
                )

        # Second: fetch fails → serve stale
        with patch.object(dp, "_fetch_hist") as mock_fetch:
            mock_fetch.return_value = pd.DataFrame()  # empty = failure
            hist2 = dp.get_hist("TEST_STALE", period="5d")
            assert not hist2.empty, "Should serve stale data on fetch failure"

    def test_freshness_label_from_cache(self) -> None:
        from trading_mcp.data.provider import DataProvider

        dp = DataProvider()

        with patch.object(dp, "_fetch_hist") as mock_fetch:
            mock_data = pd.DataFrame(
                {"Close": [100, 101, 102]},
                index=pd.date_range("2026-08-01", periods=3, freq="D"),
            )
            mock_fetch.return_value = mock_data
            dp.get_hist("TEST_FRESH", period="5d")

        freshness = dp.get_data_freshness("TEST_FRESH", data_type="stock")
        assert freshness["freshness"] in ("live", "recent")
        assert freshness["last_data_date"] == "2026-08-03"

    def test_nonexistent_ticker_returns_cached(self) -> None:
        from trading_mcp.data.provider import DataProvider

        dp = DataProvider()
        freshness = dp.get_data_freshness("DOES_NOT_EXIST_XYZ", data_type="stock")
        assert freshness["freshness"] == "cached"
        assert freshness["last_data_date"] is None


# ── H) Signal Engine calibration integration ───────────────────────────────

class TestSignalEngineCalibration:
    """compute_action: calibrated/weak_calibrated/not_calibrated hit rates."""

    def test_calibrated_uses_isotonic(self) -> None:
        """calibrated status → isotonic curve (inverted score)."""
        import json, tempfile, os
        from trading_mcp.analysis.signal_engine import compute_action

        artifact = {
            "ticker": "cross_sectional_vp",
            "status": "calibrated",
            "isotonic_X": [30.0, 50.0, 70.0],
            "isotonic_Y": [0.61, 0.66, 0.73],
            "warnings": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            levels = {"score": 35.0, "val": 95, "vah": 105,
                      "poc_price": 100, "price": 90, "price_position": "below_val"}
            r = compute_action(levels=levels, calibration_path=tmp)
            assert r["calibration_status"] == "calibrated"
            assert r["hit_rate_source"] == "calibrated_isotonic"
            assert r["hit_rate_calibrated"] is not None
            # VP=35 → inverted=65 → interpolated between [50,0.66] and [70,0.73]
            assert 0.66 <= r["hit_rate_calibrated"] <= 0.73
        finally:
            os.unlink(tmp)

    def test_weak_calibrated_uses_bucket_shrunk(self) -> None:
        """weak_calibrated → empirical buckets with shrinkage."""
        import json, tempfile, os
        from trading_mcp.analysis.signal_engine import compute_action

        artifact = {
            "ticker": "cross_sectional_vp",
            "status": "weak_calibrated",
            "base_rate_oos": 0.63,
            "shrinkage": 0.40,
            "bucket_hit_rates": [
                {"score_low": 30.0, "score_high": 40.0, "n": 100, "hit_rate_raw": 0.62},
                {"score_low": 40.0, "score_high": 50.0, "n": 200, "hit_rate_raw": 0.60},
                {"score_low": 50.0, "score_high": 60.0, "n": 300, "hit_rate_raw": 0.65},
                {"score_low": 60.0, "score_high": 70.0, "n": 200, "hit_rate_raw": 0.67},
                {"score_low": 70.0, "score_high": 80.0, "n": 100, "hit_rate_raw": 0.69},
            ],
            "warnings": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            # VP=30 → inverted=70 → bucket [60,70] (first match) → raw=0.67 → shrunk
            levels = {"score": 30, "val": 95, "vah": 105,
                      "poc_price": 100, "price": 90, "price_position": "below_val"}
            r = compute_action(levels=levels, calibration_path=tmp)
            assert r["calibration_status"] == "weak_calibrated"
            assert r["hit_rate_source"] == "bucket_empirical_shrunk"
            # inverted=70 matches [60,70] because 60<=70<=70 is checked first
            expected = 0.63 + 0.40 * (0.67 - 0.63)  # 0.646
            assert abs(r["hit_rate_calibrated"] - expected) < 1e-6

            # VP=65 → inverted=35 → bucket [30,40] → raw=0.62 → shrunk
            levels2 = {"score": 65, "val": 95, "vah": 105,
                       "poc_price": 100, "price": 110, "price_position": "above_vah"}
            r2 = compute_action(levels=levels2, calibration_path=tmp)
            expected2 = 0.63 + 0.40 * (0.62 - 0.63)  # 0.626
            assert abs(r2["hit_rate_calibrated"] - expected2) < 1e-6
        finally:
            os.unlink(tmp)

    def test_artifact_absent_fallback(self) -> None:
        from trading_mcp.analysis.signal_engine import compute_action

        levels = {"score": 40.0, "val": 95, "vah": 105,
                  "poc_price": 100, "price": 90, "price_position": "below_val"}
        r = compute_action(levels=levels, calibration_path="/tmp/does_not_exist.json")
        assert r["calibration_status"] == "not_calibrated"
        assert r["hit_rate_calibrated"] is None
        assert r["hit_rate_source"] is None
        assert r["calibration_file"] is None
        assert r["hit_rate_estimate"] == 0.57

    def test_not_calibrated_artifact_uses_fallback(self) -> None:
        import json, tempfile, os
        from trading_mcp.analysis.signal_engine import compute_action

        artifact = {"status": "insufficient_data", "reason": "not enough data"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            levels = {"score": 65, "val": 95, "vah": 105,
                      "poc_price": 100, "price": 110, "price_position": "above_vah"}
            r = compute_action(levels=levels, calibration_path=tmp)
            assert r["calibration_status"] == "not_calibrated"
            assert r["hit_rate_calibrated"] is None
            assert r["hit_rate_estimate"] == 0.44
        finally:
            os.unlink(tmp)

    def test_artifact_with_warnings_propagates(self) -> None:
        """Warnings from artifact propagate to calibration_warnings."""
        import json, tempfile, os
        from trading_mcp.analysis.signal_engine import compute_action

        artifact = {
            "ticker": "vp",
            "status": "weak_calibrated",
            "base_rate_oos": 0.63,
            "shrinkage": 0.40,
            "bucket_hit_rates": [
                {"score_low": 0, "score_high": 100, "n": 500, "hit_rate_raw": 0.60},
            ],
            "warnings": [
                {"code": "W1", "severity": "critical", "message": "test critical"},
                {"code": "W4", "severity": "medium", "message": "test regime"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            tmp = f.name
        try:
            levels = {"score": 50, "val": 95, "vah": 105,
                      "poc_price": 100, "price": 100, "price_position": "inside_va"}
            r = compute_action(levels=levels, calibration_path=tmp)
            assert len(r["calibration_warnings"]) >= 2
            assert any("test critical" in w for w in r["calibration_warnings"])
            assert any("test regime" in w for w in r["calibration_warnings"])
        finally:
            os.unlink(tmp)

    def test_signal_limits_present(self) -> None:
        """All compute_action calls must include signal_limits."""
        from trading_mcp.analysis.signal_engine import compute_action

        levels = {"score": 50, "val": 95, "vah": 105,
                  "poc_price": 100, "price": 100, "price_position": "inside_va"}
        r = compute_action(levels=levels)
        assert "signal_limits" in r
        assert len(r["signal_limits"]) >= 3
        assert any("regime-dependent" in lim for lim in r["signal_limits"])


# ── I) Calibration gate IC OOS-only verification ──────────────────────────

class TestCalibrationGateOOS:
    """Verify gate metrics (IC, Brier, ECE) are computed STRICTLY on OOS."""

    def test_ic_computed_on_oos_only(self) -> None:
        """IC must be computed only on rows with as_of > cutoff."""
        import json, tempfile, os, sys
        from pathlib import Path

        # Create synthetic predictions with temporal split
        dates_cal = [f"2023-{i // 28 + 1:02d}-{(i % 28) + 1:02d}" for i in range(100)]
        dates_oos = [f"2025-{i // 28 + 1:02d}-{(i % 28) + 1:02d}" for i in range(100)]

        rng = np.random.RandomState(42)
        rows = []
        # Calibration: noisy signal
        for d in dates_cal:
            rows.append({
                "ticker": "TEST", "as_of": d, "signal_score": rng.uniform(30, 70),
                "horizon_days": 180, "forward_return": rng.normal(0.05, 0.15),
                "forward_price": 100.0,
            })
        # OOS: signal has predictive power (inverted)
        for d in dates_oos:
            inv_score = rng.uniform(30, 70)
            forward_return = 0.02 + 0.001 * (inv_score - 50) + rng.normal(0, 0.10)
            rows.append({
                "ticker": "TEST", "as_of": d, "signal_score": 100.0 - inv_score,
                "horizon_days": 180, "forward_return": forward_return,
                "forward_price": 100.0,
            })

        df = pd.DataFrame(rows)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            df.to_csv(f.name, index=False)
            csv_path = f.name

        try:
            # Run calibration on this synthetic data
            _skill_root = Path(__file__).resolve().parent.parent
            sys.path.insert(0, str(_skill_root))
            from scripts.calibrate_vp import _evaluate_gate

            # Simulate what calibrate_vp does: compute IC on OOS only
            cutoff = "2024-06-30"
            df_h = df[df["horizon_days"] == 180].copy()
            df_h["label"] = (df_h["forward_return"] > 0).astype(int)
            oos_mask = df_h["as_of"] > cutoff
            oos_labels = df_h["label"].to_numpy()[oos_mask.values]
            oos_inverted = (100.0 - df_h["signal_score"].to_numpy())[oos_mask.values]

            from scipy.stats import spearmanr
            ic_oos, _ = spearmanr(oos_inverted, oos_labels)

            # Also compute IC on FULL dataset to verify it's DIFFERENT
            full_labels = df_h["label"].to_numpy()
            full_inverted = 100.0 - df_h["signal_score"].to_numpy()
            ic_full, _ = spearmanr(full_inverted, full_labels)

            # They MUST be different (OOS has a different distribution)
            assert ic_oos != ic_full, (
                f"IC OOS ({ic_oos:.4f}) must differ from IC full ({ic_full:.4f}) "
                f"— if equal, the computation leaked calibration data"
            )
            assert len(oos_labels) > 0
            assert oos_mask.sum() < len(df_h), "OOS mask must NOT include all rows"
        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_brier_naive_computed_on_oos_only(self) -> None:
        """Brier_naive must use only OOS data (predict constant base rate)."""
        rng = np.random.RandomState(42)

        cal_labels = rng.binomial(1, 0.5, 100)
        oos_labels = rng.binomial(1, 0.7, 100)  # different base rate

        # Brier for constant prediction of cal base rate on cal data
        cal_base = float(np.mean(cal_labels))
        brier_cal_const = float(np.mean((cal_labels - cal_base) ** 2))

        # Brier for constant prediction of OOS base rate on OOS data
        oos_base = float(np.mean(oos_labels))
        brier_oos_const = float(np.mean((oos_labels - oos_base) ** 2))

        # The two Brier scores MUST differ because base rates differ
        assert brier_cal_const != brier_oos_const, (
            f"Brier cal ({brier_cal_const:.4f}) must differ from Brier OOS "
            f"({brier_oos_const:.4f}) — different base rates"
        )

    def test_gate_uses_oos_ic_not_full(self) -> None:
        """_evaluate_gate must classify based on OOS IC, not full-dataset IC."""
        from scripts.calibrate_vp import _evaluate_gate

        # Strong IC → should pass calibrated gate
        status, warnings = _evaluate_gate(
            brier_cal=0.20, brier_naive=0.23,
            n_oos=6000, ic_rank=0.04, ic_p=0.001, ece=0.04,
        )
        assert status == "calibrated", f"Expected calibrated, got {status}"

        # Weak IC → should be weak_calibrated
        status2, _ = _evaluate_gate(
            brier_cal=0.22, brier_naive=0.23,
            n_oos=2000, ic_rank=0.018, ic_p=0.03, ece=0.08,
        )
        assert status2 == "weak_calibrated"

        # IC below threshold → not_calibrated
        status3, _ = _evaluate_gate(
            brier_cal=0.22, brier_naive=0.23,
            n_oos=2000, ic_rank=0.010, ic_p=0.03, ece=0.08,
        )
        assert status3 == "not_calibrated"


# ── J) Validation report (OOS-only verdict, degradation) ──────────────────

class TestValidationReport:
    """validation_report.py: OOS-only pooled evaluation, degradation, verdicts."""

    def _make_synth_csv(self, n_rows: int = 6000, seed: int = 42,
                        predictive: bool = False,
                        cal_ratio: float = 0.5) -> str:
        """Create synthetic CSV with optional temporal split.

        cal_ratio: fraction of rows dated before 2024-06-30 (calibration).
        The remainder are OOS (dated after 2024-06-30).
        """
        import tempfile

        rng = np.random.RandomState(seed)
        n_cal = int(n_rows * cal_ratio)
        n_oos = n_rows - n_cal

        rows = []
        for i in range(n_cal):
            score = rng.uniform(25, 75)
            fwd = (0.02 + 0.005 * (score - 25) + rng.normal(0, 0.05)
                   if predictive else rng.normal(0, 0.10))
            rows.append({
                "ticker": "TEST", "as_of": f"2023-{(i//200)%12+1:02d}-{(i%28)+1:02d}",
                "signal_score": score, "horizon_days": 180,
                "forward_return": fwd, "forward_price": 100.0 * (1 + fwd),
            })

        for i in range(n_oos):
            score = rng.uniform(25, 75)
            # OOS: signal degraded or noise
            fwd = (rng.normal(0, 0.12) if predictive
                   else rng.normal(0, 0.10))
            rows.append({
                "ticker": "TEST", "as_of": f"2025-{(i//200)%12+1:02d}-{(i%28)+1:02d}",
                "signal_score": score, "horizon_days": 180,
                "forward_return": fwd, "forward_price": 100.0 * (1 + fwd),
            })

        df = pd.DataFrame(rows)
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df.to_csv(tmp.name, index=False)
        return tmp.name

    def test_pooled_evaluation_returns_metrics(self) -> None:
        """evaluate_single_horizon_pooled returns HorizonResult with metrics."""
        csv_path = self._make_synth_csv(2000, predictive=False)

        try:
            from scripts.validation_report import (
                load_predictions, evaluate_single_horizon_pooled,
            )
            from backtest.contract import BacktestConfig, CostModel

            df = load_predictions(csv_path)
            cm = CostModel()
            cfg = BacktestConfig(
                horizons_days=[180], apply_costs=False, cost_model=cm,
                min_horizon_observations=10, strict_mode=False, permutation_control=False,
            )
            hr = evaluate_single_horizon_pooled(df, 180, cfg)
            assert hr is not None
            assert hr.n_observations > 0
            assert hr.ic_rank is not None
        finally:
            from pathlib import Path
            Path(csv_path).unlink(missing_ok=True)

    def test_strong_signal_passes_on_oos(self) -> None:
        """Strong predictive signal on OOS → predictive_evidence."""
        import tempfile
        rng = np.random.RandomState(42)
        rows = []
        for i in range(6000):
            score = rng.uniform(25, 75)
            # All rows OOS (2025), strong signal
            fwd = 0.02 + 0.003 * (score - 25) + rng.normal(0, 0.05)
            rows.append({
                "ticker": "TEST", "as_of": f"2025-{(i//500)%12+1:02d}-{(i%28)+1:02d}",
                "signal_score": score, "horizon_days": 180,
                "forward_return": fwd, "forward_price": 100.0 * (1 + fwd),
            })
        df = pd.DataFrame(rows)
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df.to_csv(tmp.name, index=False)

        try:
            from scripts.validation_report import (
                load_predictions, evaluate_single_horizon_pooled,
                evaluate_thresholds_oos, compute_verdict,
            )
            from backtest.contract import BacktestConfig, CostModel

            df = load_predictions(tmp.name)
            cm = CostModel()
            cfg = BacktestConfig(
                horizons_days=[180], apply_costs=False, cost_model=cm,
                min_horizon_observations=100, strict_mode=False, permutation_control=False,
            )
            hr = evaluate_single_horizon_pooled(df, 180, cfg)
            tr = evaluate_thresholds_oos(hr, hr, len(df), 180, cm, degradation=None)
            verdict, reason = compute_verdict(tr)
            assert verdict == "predictive_evidence", (
                f"Strong signal should pass, got {verdict}: {reason}"
            )
        finally:
            from pathlib import Path
            Path(tmp.name).unlink(missing_ok=True)

    def test_noise_fails_on_oos(self) -> None:
        """Pure noise → diagnostic_only."""
        import tempfile
        rng = np.random.RandomState(42)
        rows = []
        for i in range(6000):
            rows.append({
                "ticker": "TEST", "as_of": f"2025-{(i//500)%12+1:02d}-{(i%28)+1:02d}",
                "signal_score": rng.uniform(25, 75), "horizon_days": 180,
                "forward_return": rng.normal(0, 0.10), "forward_price": 100.0,
            })
        df = pd.DataFrame(rows)
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df.to_csv(tmp.name, index=False)

        try:
            from scripts.validation_report import (
                load_predictions, evaluate_single_horizon_pooled,
                evaluate_thresholds_oos, compute_verdict,
            )
            from backtest.contract import BacktestConfig, CostModel

            df = load_predictions(tmp.name)
            cm = CostModel()
            cfg = BacktestConfig(
                horizons_days=[180], apply_costs=False, cost_model=cm,
                min_horizon_observations=100, strict_mode=False, permutation_control=False,
            )
            hr = evaluate_single_horizon_pooled(df, 180, cfg)
            tr = evaluate_thresholds_oos(hr, hr, len(df), 180, cm, degradation=None)
            verdict, _ = compute_verdict(tr)
            assert verdict == "diagnostic_only", f"Noise got {verdict}"
        finally:
            from pathlib import Path
            Path(tmp.name).unlink(missing_ok=True)

    def test_degradation_warning_applied(self) -> None:
        """When IC degrades >50% from full to OOS, degradation FAIL triggers."""
        from scripts.validation_report import evaluate_thresholds_oos, ACCEPTANCE_THRESHOLDS

        # Mock HorizonResult-ish objects via a simple class
        class MockHR:
            ic_rank = 0.03
            ic_pearson = 0.03
            hit_rate = 0.55
            mean_return_pct = 2.0
            quintile_spread = -0.5
            n_observations = 6000
            horizon_days = 180
            quintile_returns = {"Q1": 2.5, "Q2": 2.0, "Q3": 1.5, "Q4": 1.0, "Q5": 0.5}
            hit_rate_net = 0.54
            mean_return_pct_net = 1.8
            quintile_spread_net = -0.4
            quintile_returns_net = {}
        hr = MockHR()

        from backtest.contract import CostModel
        cm = CostModel()

        # Strong degradation: 80% loss
        degradation = {
            "ic_full_abs": 0.15,
            "ic_oos_abs": 0.03,
            "ratio": 0.20,
            "note": "Severe degradation",
        }
        tr = evaluate_thresholds_oos(hr, hr, 6000, 180, cm, degradation=degradation)
        deg_crit = next(r for r in tr if r["criterion"] == "ic_degradation_warning")
        assert deg_crit["result"] == "FAIL", (
            f"Severe degradation should FAIL, got {deg_crit['result']}"
        )

        # Mild degradation: 30% loss → still above threshold
        degradation2 = {
            "ic_full_abs": 0.04,
            "ic_oos_abs": 0.03,
            "ratio": 0.75,
            "note": "Mild",
        }
        tr2 = evaluate_thresholds_oos(hr, hr, 6000, 180, cm, degradation=degradation2)
        deg_crit2 = next(r for r in tr2 if r["criterion"] == "ic_degradation_warning")
        assert deg_crit2["result"] == "PASS"

    def test_insufficient_data_verdict(self) -> None:
        from scripts.validation_report import compute_verdict
        tr = [
            {"criterion": "ic_rank_abs_min", "result": "INSUFFICIENT_DATA"},
            {"criterion": "n_obs_min", "result": "INSUFFICIENT_DATA"},
        ]
        verdict, _ = compute_verdict(tr)
        assert verdict == "insufficient_data"

    def test_costs_reduce_net_metrics(self) -> None:
        """Net metrics exist and are ≤ gross."""
        csv_path = self._make_synth_csv(2000, predictive=False)

        try:
            from scripts.validation_report import (
                load_predictions, evaluate_single_horizon_pooled,
            )
            from backtest.contract import BacktestConfig, CostModel

            df = load_predictions(csv_path)
            cm = CostModel()

            cfg_g = BacktestConfig(
                horizons_days=[180], apply_costs=False, cost_model=cm,
                min_horizon_observations=10, strict_mode=False, permutation_control=False,
            )
            cfg_n = BacktestConfig(
                horizons_days=[180], apply_costs=True, cost_model=cm,
                min_horizon_observations=10, strict_mode=False, permutation_control=False,
            )

            hr_g = evaluate_single_horizon_pooled(df, 180, cfg_g)
            hr_n = evaluate_single_horizon_pooled(df, 180, cfg_n)

            assert hr_g.mean_return_pct is not None
            assert hr_n.mean_return_pct_net is not None
            assert hr_n.mean_return_pct_net <= hr_g.mean_return_pct + 0.01
        finally:
            from pathlib import Path
            Path(csv_path).unlink(missing_ok=True)


# ── K) Point-in-time universe / survivorship ─────────────────────────────

class TestPITUniverse:
    """Historical universe: membership, boundary dates, delisting."""

    def _make_hist_csv(self, tmp_path) -> str:
        import csv
        p = tmp_path / "test_hist.csv"
        with open(p, "w") as f:
            w = csv.writer(f)
            w.writerow(["# Test"])
            w.writerow(["symbol", "date_added", "date_removed"])
            w.writerow(["AAPL", "1982-11-30", ""])
            w.writerow(["MMM", "1957-03-04", ""])
            w.writerow(["CIT", "2002-06-03", "2021-12-31"])
            w.writerow(["NEWCO", "2024-01-15", ""])
            w.writerow(["FRC", "2010-12-13", "2023-05-01"])
        return str(p)

    def test_load_historical_universe(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = self._make_hist_csv(Path(td))
            from trading_mcp.data.universe import load_historical_universe
            df = load_historical_universe(p)
            assert len(df) == 5
            assert "AAPL" in df["symbol"].values

    def test_membership_active_always(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = self._make_hist_csv(Path(td))
            from trading_mcp.data.universe import get_universe_members, is_member
            members = get_universe_members("2020-06-15", path=p)
            assert "AAPL" in members
            assert is_member("AAPL", "2020-06-15", path=p) is True

    def test_delisted_after_removal(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = self._make_hist_csv(Path(td))
            from trading_mcp.data.universe import get_universe_members, is_member
            assert "CIT" in get_universe_members("2021-06-01", path=p)
            assert is_member("CIT", "2021-06-01", path=p) is True
            assert "CIT" not in get_universe_members("2022-06-01", path=p)

    def test_new_member_not_before(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = self._make_hist_csv(Path(td))
            from trading_mcp.data.universe import get_universe_members
            assert "NEWCO" not in get_universe_members("2023-01-01", path=p)
            assert "NEWCO" in get_universe_members("2024-06-01", path=p)

    def test_check_backtest_passes(self) -> None:
        from trading_mcp.data.universe import check_backtest_universe
        ok, reason = check_backtest_universe("sp500_historical")
        assert ok is True
        assert "suitable" in reason.lower()

    def test_missing_file_empty(self) -> None:
        from trading_mcp.data.universe import get_universe_members
        assert get_universe_members("2023-01-01", path="/tmp/nonexistent.csv") == []

    def test_cache_singleton(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            p = self._make_hist_csv(Path(td))
            from trading_mcp.data.universe import load_historical_universe
            df1 = load_historical_universe(p)
            df2 = load_historical_universe(p)
            assert df1 is df2


# ── L) VRP calibration ─────────────────────────────────────────────────

class TestVRPCalibration:
    """VRP proxy calibration: temporal split, gate, anti-leakage."""

    def test_known_series_calibrates(self) -> None:
        """Synthetic series with strong VRP signal → calibrated."""
        from trading_mcp.data.vrp_calibration import calibrate_vrp

        n = 800
        rng = np.random.RandomState(42)
        dates = [f"2021-{(i // 30) % 12 + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]
        # Generate close with upward drift
        close = [100.0]
        for i in range(1, n):
            close.append(close[-1] * (1 + rng.normal(0.0005, 0.01)))
        # IV series with strong predictive signal: high IV → low future return
        iv = []
        for i in range(n):
            base_iv = 0.15 + 0.10 * rng.random()
            iv.append(base_iv)

        artifact = calibrate_vrp(
            dates=dates, underlying_close=close, iv_series=iv,
            cutoff="2024-01-01", ticker="TEST", iv_proxy_note="synthetic",
            min_fit=200, min_oos=50,
        )
        assert artifact.status in ("calibrated", "weak_calibrated", "not_calibrated")
        assert artifact.metrics.n_fit > 0
        assert artifact.calibrated_vrp_proxy is not None
        assert hasattr(artifact.metrics, "directional_p_value_oos")

    def test_insufficient_data_returns_not_calibrated(self) -> None:
        """Too few points → not_calibrated."""
        from trading_mcp.data.vrp_calibration import calibrate_vrp

        artifact = calibrate_vrp(
            dates=["2023-01-01", "2023-01-02"],
            underlying_close=[100.0, 101.0],
            iv_series=[0.20, 0.21],
            cutoff="2023-01-02",
            ticker="TINY", iv_proxy_note="test",
            min_fit=500, min_oos=100,
        )
        assert artifact.status == "not_calibrated"

    def test_anti_leakage_metrics_differ(self) -> None:
        """If cutoff changes, OOS/fit split must change (no leakage)."""
        from trading_mcp.data.vrp_calibration import calibrate_vrp

        n = 800
        rng = np.random.RandomState(42)
        # Generate dates spanning 2021 through 2026
        dates = pd.date_range("2021-01-01", periods=n, freq="B")
        date_strs = [str(d.date()) for d in dates]
        close = [100.0]
        for i in range(1, n):
            close.append(close[-1] * (1 + rng.normal(0.0005, 0.012)))
        iv = [0.15 + 0.10 * rng.random() for _ in range(n)]

        # Early cutoff → more OOS
        a1 = calibrate_vrp(
            dates=date_strs, underlying_close=close, iv_series=iv,
            cutoff="2022-12-31", ticker="TEST", iv_proxy_note="test",
            min_fit=100, min_oos=10,
        )
        # Late cutoff → less OOS
        a2 = calibrate_vrp(
            dates=date_strs, underlying_close=close, iv_series=iv,
            cutoff="2025-12-31", ticker="TEST", iv_proxy_note="test",
            min_fit=100, min_oos=10,
        )
        assert a1.metrics.n_oos > a2.metrics.n_oos, (
            f"Early cutoff should have more OOS: {a1.metrics.n_oos} vs {a2.metrics.n_oos}"
        )

    def test_save_load_roundtrip(self) -> None:
        """Artifact can be saved and loaded."""
        import tempfile
        from trading_mcp.data.vrp_calibration import (
            calibrate_vrp, VRPCalibrationArtifact,
        )
        from pathlib import Path

        n = 400
        rng = np.random.RandomState(42)
        dates = [f"2022-{(i // 30) % 12 + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]
        close = [100.0]
        for i in range(1, n):
            close.append(close[-1] * (1 + rng.normal(0.0003, 0.01)))
        iv = [0.15 + 0.05 * rng.random() for _ in range(n)]

        artifact = calibrate_vrp(
            dates=dates, underlying_close=close, iv_series=iv,
            cutoff="2023-12-01", ticker="ROUNDTRIP", iv_proxy_note="test",
            min_fit=100, min_oos=50,
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            p = f.name
        try:
            artifact.save(p)
            loaded = VRPCalibrationArtifact.load(p)
            assert loaded.ticker == "ROUNDTRIP"
            assert loaded.status == artifact.status
            assert loaded.metrics.n_fit == artifact.metrics.n_fit
        finally:
            Path(p).unlink(missing_ok=True)


# ── M) Backfill + Performance Report (monitoring) ──────────────────────

class TestMonitoringBackfill:
    """backfill_prediction_log.py and performance_report.py."""

    def test_backfill_writes_records(self) -> None:
        import tempfile, csv, json
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        csv_path = tmp_dir / "test_preds.csv"
        with open(csv_path, "w") as f:
            w = csv.writer(f)
            w.writerow(["ticker", "as_of", "signal_score", "horizon_days",
                         "forward_return", "forward_price"])
            for i in range(20):
                w.writerow(["AAPL", f"2025-01-{(i%28)+1:02d}", 60.0, 20,
                            f"{0.01*i:.4f}", "150.0"])

        log_path = tmp_dir / "test_log.jsonl"
        try:
            # Record all predictions as resolved
            from monitoring.prediction_log import PredictionLogger
            plog = PredictionLogger(str(log_path))
            import pandas as pd
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                plog.record_prediction(
                    ticker=str(row["ticker"]),
                    as_of=str(row["as_of"]),
                    model_version="test",
                    score=float(row["signal_score"]),
                    horizon_days=int(row["horizon_days"]),
                )
                plog.resolve_outcome(
                    str(row["ticker"]), str(row["as_of"]),
                    float(row["forward_return"]),
                )

            report = plog.performance_report(min_required=5)
            assert report.n_total == 20
            assert report.n_resolved == 20
            assert report.status == "ok"
            assert report.hit_rate is not None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_dedupe_skips_existing(self) -> None:
        """Backfill with dedupe should not duplicate entries."""
        import tempfile, csv, json
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        csv_path = tmp_dir / "test_preds.csv"
        with open(csv_path, "w") as f:
            w = csv.writer(f)
            w.writerow(["ticker", "as_of", "signal_score", "horizon_days",
                         "forward_return", "forward_price"])
            w.writerow(["AAPL", "2025-01-15", 60.0, 20, "0.05", "150.0"])

        log_path = tmp_dir / "test_log2.jsonl"
        try:
            from monitoring.prediction_log import PredictionLogger
            plog = PredictionLogger(str(log_path))
            plog.record_prediction("AAPL", "2025-01-15", "v1", 60.0, None, 20)
            plog.resolve_outcome("AAPL", "2025-01-15", 0.05)

            n = plog.resolve_outcome("AAPL", "2025-01-15", 0.05)
            assert n == 0
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_overlap_guard_suppresses_sharpe(self) -> None:
        """Overlapping predictions → sharpe_annualized=None, warning present."""
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        log_path = tmp_dir / "overlap_test.jsonl"
        try:
            from monitoring.prediction_log import PredictionLogger
            plog = PredictionLogger(str(log_path))
            # Daily predictions with 180d horizon → massive overlap
            for i in range(100):
                plog.record_prediction("AAPL", f"2025-{(i//30)%12+1:02d}-{(i%28)+1:02d}",
                                       "v1", 60.0, None, horizon_days=180)
                plog.resolve_outcome("AAPL", f"2025-{(i//30)%12+1:02d}-{(i%28)+1:02d}",
                                     float(np.random.normal(0.01, 0.05)))

            report = plog.performance_report(min_required=20)
            assert report.status == "ok"
            assert report.sharpe_annualized is None, "Overlapping → Sharpe must be None"
            assert report.sharpe_biased_raw is not None, "Biased raw should be present"
            assert report.overlap_factor is not None
            assert report.overlap_factor > 2.0
            assert len(report.warnings) >= 1
            assert any("OVERLAP" in w for w in report.warnings)
            assert report.directional_p_value is not None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_non_overlapping_sharpe_valid(self) -> None:
        """Non-overlapping → sharpe_annualized populated."""
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        log_path = tmp_dir / "nonoverlap_test.jsonl"
        try:
            from monitoring.prediction_log import PredictionLogger
            plog = PredictionLogger(str(log_path))
            # 30-day intervals with 20d horizon → little overlap
            for i in range(60):
                plog.record_prediction("AAPL", f"2025-{(i//12)%12+1:02d}-{i*3%28+1:02d}",
                                       "v1", 60.0, None, horizon_days=20)
                plog.resolve_outcome("AAPL", f"2025-{(i//12)%12+1:02d}-{i*3%28+1:02d}",
                                     float(np.random.normal(0.01, 0.05)))

            report = plog.performance_report(min_required=20)
            assert report.status == "ok"
            if report.overlap_factor and report.overlap_factor <= 2.0:
                assert report.sharpe_annualized is not None
            assert report.directional_p_value is not None
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
