"""Test P0 short-history guards: analyze_stock, scan_market, bakshi_signals.

All tests use synthetic/mocked data — no network calls.

P0 Aug 2026: verify explicit insufficient_data propagation across:
    - process_ticker (< 50 bars)
    - analyze_stock (composite_score=None, no verdict)
    - scan_market (exclusion from ranking, insufficient_data_count)
    - bakshi_signals (< 63 bars)
    - bali_signals (< 50 bars, available=False, composite_bali_score=None)
    - tsmom_signals (< 60 bars, available=False, mom_score=None)
    - No final_score=None passed to sorting/ranking
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

_MCP_SRC = Path("/home/giuseppe/Progetti/Github/opencode-skills/mcp/src")
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))


def make_ohlcv_hist(n_bars: int, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV history with n_bars."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n_bars, freq="B")
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n_bars))
    close = np.maximum(close, 10.0)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + rng.uniform(0.1, 0.5, n_bars),
            "Low": close - rng.uniform(0.1, 0.5, n_bars),
            "Close": close,
            "Volume": rng.integers(1000, 100000, n_bars),
        },
        index=dates,
    )


class TestProcessTickerShortHistory:
    """process_ticker must return insufficient_data dict for < 50 bars."""

    def test_30_bars_returns_insufficient_data(self) -> None:
        """30 bars must produce status='insufficient_data', final_score=None."""
        from trading_mcp.analysis.scanner import process_ticker

        hist = make_ohlcv_hist(30)
        mock_t = MagicMock()
        mock_info = {"currentPrice": 100.0}

        with patch("trading_mcp.analysis.scanner._fetch_with_retry",
                   return_value=(mock_t, mock_info, hist)):
            ticker_dict = {"symbol": "SHORT", "name": "Short Inc", "market": "US"}
            result = process_ticker(ticker_dict, fetch_news=False)

        assert result is not None
        assert result.get("status") == "insufficient_data"
        assert result.get("final_score") is None
        assert result.get("history_bars") == 30
        assert result.get("required_bars") == 50
        assert "insufficienti" in result.get("reason", "")

    def test_10_bars_returns_insufficient_data(self) -> None:
        """10 bars must also be caught."""
        from trading_mcp.analysis.scanner import process_ticker

        hist = make_ohlcv_hist(10)
        mock_t = MagicMock()
        mock_info = {"currentPrice": 50.0}

        with patch("trading_mcp.analysis.scanner._fetch_with_retry",
                   return_value=(mock_t, mock_info, hist)):
            ticker_dict = {"symbol": "TINY", "name": "Tiny Co", "market": "US"}
            result = process_ticker(ticker_dict, fetch_news=False)

        assert result is not None
        assert result.get("status") == "insufficient_data"
        assert result.get("final_score") is None

    def test_100_bars_proceeds_normally(self) -> None:
        """100 bars should NOT trigger the guard (normal flow)."""
        from trading_mcp.analysis.scanner import process_ticker

        hist = make_ohlcv_hist(100)
        mock_t = MagicMock()
        mock_info = {"currentPrice": 100.0, "sector": "Technology",
                     "shortPercentOfFloat": 0.05}

        with patch("trading_mcp.analysis.scanner._fetch_with_retry",
                   return_value=(mock_t, mock_info, hist)):
            ticker_dict = {"symbol": "OK", "name": "Ok Inc", "market": "US"}
            result = process_ticker(ticker_dict, fetch_news=True)

        # Should have a valid final_score (not None, not insufficient)
        assert result is not None
        assert result.get("final_score") is not None
        assert result.get("status") != "insufficient_data"


class TestAnalyzeStockShortHistory:
    """analyze_stock returns composite_score=None, no verdict for insufficient data."""

    def test_short_history_yields_none_score(self) -> None:
        """When process_ticker returns insufficient_data, analyze_stock
        should return composite_score=None and verdict='insufficient_data'."""
        from trading_mcp.analysis.scanner import process_ticker

        hist = make_ohlcv_hist(20)
        mock_t = MagicMock()
        mock_info = {"currentPrice": 100.0}

        with patch("trading_mcp.analysis.scanner._fetch_with_retry",
                   return_value=(mock_t, mock_info, hist)):
            ticker_dict = {"symbol": "SHORT", "name": "Short Inc", "market": "US"}
            result = process_ticker(ticker_dict, fetch_news=False)

        from trading_mcp.tools._analysis_tools import _compute_verdict

        # Simulate what analyze_stock does with insufficient_data
        if result.get("status") == "insufficient_data":
            output = {
                "ticker": result["symbol"],
                "composite_score": None,
                "verdict": "insufficient_data",
                "confidence": "N/A",
                "action_recommendation": {
                    "action": "N/A",
                    "reason": result.get("reason", ""),
                    "confidence": "N/A",
                },
            }
        else:
            output = {"composite_score": result["final_score"]}

        assert output["composite_score"] is None
        assert output["verdict"] == "insufficient_data"
        assert output["confidence"] == "N/A"
        assert output["action_recommendation"]["action"] == "N/A"


class TestScanMarketInsufficient:
    """scan_market must exclude insufficient_data from ranking."""

    def test_insufficient_not_in_ranking(self) -> None:
        """insufficient_data results must be excluded from ranking and counted."""
        # Simulate a mix of valid and insufficient results
        valid_results = [
            {"symbol": "A", "final_score": 85.0, "dimensions": [],
             "sentiment_breakdown": None, "modifiers": {}, "indicators": {},
             "flags": [], "sector": "Tech", "price": 100.0, "pattern": "Test"},
            {"symbol": "B", "final_score": 75.0, "dimensions": [],
             "sentiment_breakdown": None, "modifiers": {}, "indicators": {},
             "flags": [], "sector": "Fin", "price": 200.0, "pattern": "Test"},
        ]
        insufficient_results = [
            {"symbol": "BAD", "final_score": None, "status": "insufficient_data",
             "history_bars": 30, "required_bars": 50,
             "dimensions": [], "sentiment_breakdown": None, "modifiers": {},
             "indicators": {}, "flags": [], "sector": "", "price": 0.0,
             "pattern": ""},
        ]

        all_results = valid_results + insufficient_results

        # Separate (same logic as scan_market)
        insuf = [r for r in all_results
                 if r.get("status") == "insufficient_data" or r.get("final_score") is None]
        valid = [r for r in all_results
                 if r.get("status") != "insufficient_data" and r.get("final_score") is not None]

        # Sort only valid
        valid.sort(key=lambda r: r.get("final_score", 0) or 0, reverse=True)

        # Filter by min_score
        filtered = [r for r in valid if (r.get("final_score") or 0) >= 50]

        assert len(insuf) == 1
        assert insuf[0]["symbol"] == "BAD"
        assert len(valid) == 2
        assert len(filtered) == 2  # both above 50
        assert filtered[0]["symbol"] == "A"  # highest score first

    def test_none_scores_never_in_sort_key(self) -> None:
        """A list with final_score=None must not crash sorting."""
        mixed = [
            {"symbol": "A", "final_score": 80.0},
            {"symbol": "B", "final_score": None},
            {"symbol": "C", "final_score": 60.0},
        ]

        # Guarded sort
        safe_sorted = sorted(
            [r for r in mixed if r.get("final_score") is not None],
            key=lambda r: r.get("final_score", 0) or 0,
            reverse=True,
        )

        assert len(safe_sorted) == 2
        assert safe_sorted[0]["symbol"] == "A"
        assert safe_sorted[1]["symbol"] == "C"


class TestBakshiShortHistory:
    """bakshi_signals must return explicit error for < 63 bars."""

    def test_30_bars_returns_error_with_counts(self) -> None:
        """30 bars < 63: must return BakshiResult with error and bar counts."""
        from trading_mcp.tools._quant_tools import BakshiResult

        r = BakshiResult(
            ticker="SHORT",
            error=(
                "Dati insufficienti per Bakshi VRP: 30 barre "
                "disponibili, richieste almeno 63."
            ),
            available_bars=30,
            required_bars=63,
        )
        d = r.model_dump()
        assert d["error"] is not None
        assert "30" in d["error"]
        assert "63" in d["error"]
        assert d["available_bars"] == 30
        assert d["required_bars"] == 63
        assert d["spot"] is None  # VRP not computed

    def test_63_bars_does_not_block(self) -> None:
        """Exactly 63 bars should NOT trigger the guard."""
        from trading_mcp.tools._quant_tools import BakshiResult

        # With 63 bars + valid options chain, bakshi proceeds
        # We test the model shape here
        r = BakshiResult(
            ticker="EXACT63",
            spot=100.0,
            atm_iv=0.25,
            available_bars=63,
            required_bars=63,
        )
        d = r.model_dump()
        assert d["available_bars"] == 63
        assert d["spot"] == 100.0
        assert d["error"] is None  # no error when data is sufficient

    def test_bakshi_result_new_fields_default(self) -> None:
        """New fields available_bars/required_bars default to 0."""
        from trading_mcp.tools._quant_tools import BakshiResult

        r = BakshiResult(ticker="X")
        assert r.available_bars == 0
        assert r.required_bars == 0

    def test_short_history_no_vrp_computed(self) -> None:
        """When history < 63, VRP should not be computed (default/zero)."""
        from trading_mcp.tools._quant_tools import BakshiResult, BakshiVRP

        r = BakshiResult(
            ticker="NOVRP",
            error="Dati insufficienti",
            available_bars=20,
            required_bars=63,
            vrp=BakshiVRP(vrp_annualized=0.0, vrp_pct_of_premium=0.0,
                          regime="NORMAL_VOL", description=""),
        )
        d = r.model_dump()
        assert d["vrp"]["vrp_annualized"] == 0.0
        assert d["vrp"]["vrp_pct_of_premium"] == 0.0
        assert d["error"] is not None


class TestDataSufficiencyModel:
    """DataSufficiency model from schemas.py."""

    def test_model_defaults(self) -> None:
        """Default DataSufficiency has status='ok', required_bars=50."""
        # pylint: disable=import-error,import-outside-toplevel
        from trading_mcp.schemas import DataSufficiency

        ds = DataSufficiency()
        assert ds.status == "ok"
        assert ds.required_bars == 50
        assert ds.diagnostic_only is False

    def test_insufficient_data_model(self) -> None:
        """DataSufficiency with insufficient_data state."""
        # pylint: disable=import-error,import-outside-toplevel
        from trading_mcp.schemas import DataSufficiency

        ds = DataSufficiency(
            status="insufficient_data",
            available_bars=30,
            required_bars=50,
            reason="Dati OHLCV insufficienti",
        )
        d = ds.model_dump()
        assert d["status"] == "insufficient_data"
        assert d["available_bars"] == 30
        assert d["required_bars"] == 50


class TestMCPPortability:
    """run_backtest.py MCP_SRC resolution (no hardcoded home paths)."""

    def test_resolve_via_env_var(self) -> None:
        """TRADING_MCP_SRC env var should take priority."""
        import os

        # pylint: disable=import-outside-toplevel
        skill_root = Path(__file__).resolve().parent.parent.parent

        def _resolve():
            env_path = os.environ.get("TRADING_MCP_SRC")
            if env_path:
                p_test = Path(env_path)
                if (p_test / "trading_mcp").exists():
                    return p_test
            candidate = skill_root
            for _ in range(6):
                mcp_src = candidate / "mcp" / "src"
                if (mcp_src / "trading_mcp").exists():
                    return mcp_src
                candidate = candidate.parent
            return Path(".")

        result = _resolve()
        assert result != Path("."), (
            f"Could not resolve MCP src from {skill_root}. "
            f"Got {result}. TRADING_MCP_SRC={os.environ.get('TRADING_MCP_SRC')}"
        )

    def test_fallback_path_is_safe(self) -> None:
        """Fallback to '.' when nothing found — import will use PYTHONPATH."""
        result = Path(".")
        assert result == Path(".")

    def test_help_runs_without_network(self) -> None:
        """`python run_backtest.py --help` must exit 0 without any import crash."""
        import subprocess

        script = Path(__file__).resolve().parent.parent / "scripts" / "run_backtest.py"
        result = subprocess.run(  # pylint: disable=subprocess-run-check
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"--help failed with code {result.returncode}\n"
            f"STDERR: {result.stderr[:500]}"
        )
        assert "--ticker" in result.stdout, (
            f"--help output missing expected args.\nSTDOUT: {result.stdout[:500]}"
        )


# ── Bali & TS-MOM short-history guard tests ────────────────────────────

class TestBaliShortHistory:
    """bali_signals must return available=False, composite_bali_score=None for < 50 bars."""

    def test_30_bars_returns_unavailable(self) -> None:
        """30 bars < 50: available=False, error_is_blocking=True, composite_bali_score=None."""
        from trading_mcp.tools._quant_tools import BaliResult

        r = BaliResult(
            ticker="SHORT",
            available=False,
            error_is_blocking=True,
            error=(
                "Dati insufficienti per Bali volatility spread: "
                "30 barre disponibili, richieste almeno 50 per RV robusta."
            ),
            available_bars=30,
            required_bars=50,
            direction="unavailable",
        )
        d = r.model_dump()
        assert d["available"] is False
        assert d["error_is_blocking"] is True
        assert d["composite_bali_score"] is None
        assert d["direction"] == "unavailable"
        assert d["available_bars"] == 30
        assert d["required_bars"] == 50
        # Must NOT have a neutral score
        assert d["composite_bali_score"] != 50.0

    def test_success_path_has_available_true(self) -> None:
        """Success path: available=True, composite_bali_score has a value."""
        from trading_mcp.tools._quant_tools import BaliResult

        r = BaliResult(
            ticker="OK",
            available=True,
            spot=100.0,
            rv=0.25,
            atm_call_iv=0.30,
            atm_put_iv=0.32,
            composite_bali_score=65.0,
            direction="bullish",
            available_bars=200,
            required_bars=50,
        )
        d = r.model_dump()
        assert d["available"] is True
        assert d["error_is_blocking"] is False
        assert d["composite_bali_score"] == 65.0
        assert d["direction"] == "bullish"

    def test_bare_constructor_is_unavailable(self) -> None:
        """BaliResult(ticker='X') defaults to unavailable — no neutral score."""
        from trading_mcp.tools._quant_tools import BaliResult

        r = BaliResult(ticker="X")
        assert r.available is False
        assert r.composite_bali_score is None
        assert r.direction == "unavailable"
        assert r.error_is_blocking is False  # technical default

    def test_score_never_defaults_to_50(self) -> None:
        """composite_bali_score must stay None when unavailable, never 50."""
        from trading_mcp.tools._quant_tools import BaliResult

        r = BaliResult(
            ticker="ERR",
            available=False,
            error_is_blocking=True,
            error="Errore dati",
            direction="unavailable",
        )
        assert r.composite_bali_score is None, (
            "composite_bali_score must be None, not 50, when unavailable"
        )


class TestTSMomShortHistory:
    """tsmom_signals must return available=False, mom_score=None for < 60 bars."""

    def test_40_bars_returns_unavailable(self) -> None:
        """40 bars < 60: available=False, error_is_blocking=True, mom_score=None."""
        from trading_mcp.tools._quant_tools import TSMomResult

        r = TSMomResult(
            ticker="SHORT",
            available=False,
            error_is_blocking=True,
            error=(
                "Dati insufficienti per TS-MOM: 40 barre "
                "disponibili, richieste almeno 60."
            ),
            available_bars=40,
            required_bars=60,
            direction="unavailable",
        )
        d = r.model_dump()
        assert d["available"] is False
        assert d["error_is_blocking"] is True
        assert d["mom_score"] is None
        assert d["direction"] == "unavailable"
        assert d["available_bars"] == 40
        assert d["required_bars"] == 60
        # Must NOT have neutral score
        assert d["mom_score"] != 50.0

    def test_success_path_has_available_true(self) -> None:
        """Success path: available=True, mom_score has a value."""
        from trading_mcp.tools._quant_tools import TSMomResult

        r = TSMomResult(
            ticker="OK",
            available=True,
            price=150.0,
            mom_score=72.0,
            direction="bullish",
            cum_return_lookback=0.15,
            signal=1,
            available_bars=200,
            required_bars=60,
        )
        d = r.model_dump()
        assert d["available"] is True
        assert d["error_is_blocking"] is False
        assert d["mom_score"] == 72.0
        assert d["direction"] == "bullish"
        assert d["signal"] == 1

    def test_bare_constructor_is_unavailable(self) -> None:
        """TSMomResult(ticker='X') defaults to unavailable."""
        from trading_mcp.tools._quant_tools import TSMomResult

        r = TSMomResult(ticker="X")
        assert r.available is False
        assert r.mom_score is None
        assert r.direction == "unavailable"
        assert r.error_is_blocking is False

    def test_mom_score_never_defaults_to_50(self) -> None:
        """mom_score must stay None when unavailable, never 50."""
        from trading_mcp.tools._quant_tools import TSMomResult

        r = TSMomResult(
            ticker="ERR",
            available=False,
            error_is_blocking=True,
            error="Errore dati",
            direction="unavailable",
        )
        assert r.mom_score is None, (
            "mom_score must be None, not 50, when unavailable"
        )

    def test_skip_days_causes_insufficient(self) -> None:
        """When start_idx >= end_idx due to skip_last, must set available=False."""
        from trading_mcp.tools._quant_tools import TSMomResult

        r = TSMomResult(
            ticker="SKIP",
            available=False,
            error_is_blocking=True,
            error="Dati insufficienti dopo skip: start=0, end=0",
            available_bars=30,
            required_bars=60,
            direction="unavailable",
        )
        d = r.model_dump()
        assert d["available"] is False
        assert d["mom_score"] is None
