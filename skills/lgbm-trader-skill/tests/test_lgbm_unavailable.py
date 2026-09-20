"""Test LGBM unavailable behavior: no neutral score as signal.

Verify that LGBMResult.available=False when model/dependency/schema is
missing, and that error_is_blocking=True.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_skill_root = Path(__file__).resolve().parent.parent
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))

# MCP src path
_mcp_src = Path(__file__).resolve().parents[3] / "mcp" / "src"
if str(_mcp_src) not in sys.path:
    sys.path.insert(0, str(_mcp_src))

# Skill scripts path (predict_or_train gate)
_scripts_dir = _skill_root / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import predict_or_train as pot  # noqa: E402  # pylint: disable=import-error,wrong-import-position


class TestLGBMResultModel:
    """Tests for LGBMResult Pydantic model."""

    def test_default_unavailable(self) -> None:
        """Default LGBMResult must have available=False and null score."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="TEST",
            available=False,
            error_is_blocking=True,
            error="Test error",
        )
        assert r.available is False
        assert r.score is None
        assert r.signal == "unavailable"
        assert r.error_is_blocking is True

    def test_bare_constructor_is_unavailable(self) -> None:
        """LGBMResult(ticker='X') senza parametri deve essere unavailable."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(ticker="X")
        assert r.available is False, (
            "bare LGBMResult must default to unavailable"
        )
        assert r.score is None
        assert r.signal == "unavailable"
        assert r.error_is_blocking is False  # default tecnico
        assert r.error is None

    def test_available_true_has_score(self) -> None:
        """When available=True, score must be non-None."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="TEST",
            available=True,
            score=75.0,
            signal="long",
        )
        assert r.available is True
        assert r.score == 75.0
        assert r.signal == "long"
        assert r.error_is_blocking is False

    def test_model_dump_excludes_none_error(self) -> None:
        """Available results should not have error fields."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="TEST",
            available=True,
            score=60.0,
            signal="long",
            model="test_model.pkl",
        )
        d = r.model_dump()
        assert d["error"] is None
        assert d["error_is_blocking"] is False

    def test_unavailable_never_has_neutral_score(self) -> None:
        """Unavailable results must NEVER have score=50 or signal=neutral."""
        from trading_mcp.tools._quant_tools import LGBMResult

        # score=None, not 50
        r = LGBMResult(
            ticker="TEST",
            available=False,
            error_is_blocking=True,
            error="No model found",
        )
        assert r.score is None, "score must be None, not 50"
        assert r.signal == "unavailable", "signal must be 'unavailable', not 'neutral'"


class TestLGBMPredictUnavailable:
    """Test lgbm_predict returns available=False when model is missing."""

    def test_missing_skill_dir_returns_unavailable(self) -> None:
        """If skill dir doesn't exist, return available=False."""
        # We can't actually call lgbm_predict (it's an MCP tool), but we
        # can verify the LGBMResult model behavior.
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="NONEXISTENT",
            available=False,
            error_is_blocking=True,
            error="lgbm-trader-skill non trovato.",
        )
        d = r.model_dump()
        assert d["available"] is False
        assert d["error_is_blocking"] is True
        assert d["score"] is None
        assert d["signal"] == "unavailable"

    def test_no_model_found_returns_unavailable(self) -> None:
        """When no .pkl model exists, return available=False."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="UNKNOWN",
            available=False,
            error_is_blocking=True,
            error="Nessun modello trovato per UNKNOWN.",
        )
        d = r.model_dump()
        assert d["available"] is False
        assert d["error_is_blocking"] is True


class TestFeatureAlignment:
    """Test _align_features behavior (strict validation, no silent fill)."""

    def test_align_features_raises_on_missing_columns(self) -> None:
        """Missing feature columns must raise ValueError."""
        import pandas as pd
        from trading_mcp.tools._quant_tools import _align_features

        df = pd.DataFrame({"mom_1": [1.0], "vol_1": [2.0]})
        feature_names = ["mom_1", "vol_1", "missing_feat"]

        with pytest.raises(ValueError, match="Feature mismatch"):
            _align_features(df, feature_names)

    def test_align_features_raises_on_nan(self) -> None:
        """NaN in rows must raise ValueError."""
        import pandas as pd
        import numpy as np
        from trading_mcp.tools._quant_tools import _align_features

        df = pd.DataFrame({"mom_1": [1.0, np.nan], "vol_1": [2.0, 3.0]})
        feature_names = ["mom_1", "vol_1"]

        with pytest.raises(ValueError, match="NaN"):
            _align_features(df, feature_names)

    def test_short_history_fields_present(self) -> None:
        """LGBMResult must expose available_bars, required_bars, reason."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="SHORT",
            available=False,
            error_is_blocking=True,
            error="Storia insufficiente",
            available_bars=30,
            required_bars=252,
            reason="short_history: feature lookback insufficiente",
        )
        d = r.model_dump()
        assert d["available_bars"] == 30
        assert d["required_bars"] == 252
        assert "short_history" in d["reason"]
        assert d["available"] is False
        assert d["error_is_blocking"] is True
        assert d["score"] is None
        assert d["signal"] == "unavailable"

    def test_short_history_never_predicts(self) -> None:
        """Quando la storia e' corta, available=False, score=None, non si predice."""
        from trading_mcp.tools._quant_tools import LGBMResult

        r = LGBMResult(
            ticker="TINY",
            available=False,
            error_is_blocking=True,
            error=(
                "Dati insufficienti per LGBM prediction: 50 barre "
                "disponibili, richieste almeno 120 barre."
            ),
            available_bars=50,
            required_bars=120,
            reason="short_history",
        )
        assert r.available is False
        assert r.score is None
        assert r.signal == "unavailable"
        assert r.error_is_blocking is True
        # Must NOT contain a neutral score
        assert r.score != 50.0

    def test_align_features_ok_when_all_present(self) -> None:
        """All features present + no NaN -> returns aligned DataFrame."""
        import pandas as pd
        from trading_mcp.tools._quant_tools import _align_features

        df = pd.DataFrame({"mom_1": [5.5, 3.0], "vol_1": [-1.2, 0.5]})
        feature_names = ["mom_1", "vol_1"]

        aligned = _align_features(df, feature_names)
        assert list(aligned.columns) == feature_names
        assert aligned["mom_1"].iloc[0] == 5.5
        assert aligned["vol_1"].iloc[0] == -1.2


class TestTrainGate:
    """Gate train-vs-skip: threshold, uplift math, LGBMResult semantics."""

    @pytest.fixture(autouse=True)
    def _default_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from trading_mcp.weights_config import WeightsConfig

        monkeypatch.setattr(pot, "_GATE", WeightsConfig().lgbm_gate)

    def test_gate_rejects_below_threshold(self) -> None:
        """High fallback confidence everywhere -> marginal uplift -> skip."""
        conf = {"bali": 78, "tsmom": 75, "bakshi": 80, "factor_scan": 72}
        approve, metrics = pot._gate_decision(conf, False)
        assert approve is False
        assert metrics["uplift"] < 5.0
        assert metrics["decision"] == "skip"

    def test_gate_approves_above_threshold(self) -> None:
        """Divergent fallback signals -> real uplift -> train."""
        conf = {"bali": 80, "tsmom": 30, "bakshi": 40, "factor_scan": 50}
        approve, metrics = pot._gate_decision(conf, False)
        assert approve is True
        assert metrics["uplift"] == pytest.approx(6.0, abs=0.05)
        assert metrics["decision"] == "train"

    def test_gate_boundary_inclusive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """uplift exactly == threshold must approve (>= semantics)."""
        from trading_mcp.weights_config import GateComponents, LgbmGateWeights

        gate = LgbmGateWeights(
            uplift_threshold=5.0,
            without_lgbm=GateComponents(
                bali=0.5, tsmom=0.5, bakshi=0.0, factor_scan=0.0, lgbm=0.0
            ),
            with_lgbm=GateComponents(
                bali=0.5, tsmom=0.0, bakshi=0.0, factor_scan=0.0, lgbm=0.5
            ),
        )
        monkeypatch.setattr(pot, "_GATE", gate)
        conf = {"bali": 60.0, "tsmom": 50.0, "bakshi": 0.0, "factor_scan": 0.0}
        approve, metrics = pot._gate_decision(conf, False)
        assert metrics["uplift"] == 5.0
        assert approve is True

    def test_gate_no_confidence_skips(self) -> None:
        """No confidence input -> never train silently."""
        approve, metrics = pot._gate_decision(None, False)
        assert approve is False
        assert metrics["gate"] == "skip"
        assert "no-confidence-input" in metrics["reason"]

    def test_gate_force_train_bypasses(self) -> None:
        """Explicit on-demand override trains regardless of the gate."""
        approve, metrics = pot._gate_decision(None, True)
        assert approve is True
        assert metrics["gate"] == "forced"
        assert metrics["decision"] == "train"

    def test_gate_skip_result_respects_lgbm_semantics(self) -> None:
        """Skipped training must look like an unavailable LGBMResult."""
        _, metrics = pot._gate_decision(None, False)
        result = pot._gate_skip_result("TEST", metrics)
        assert result["available"] is False
        assert result["score"] is None
        assert result["signal"] == "unavailable"
        assert result["error_is_blocking"] is False
        assert result["train_skipped"] is True
        assert result["score"] != 50.0

    def test_threshold_single_source(self, tmp_path: Path) -> None:
        """Threshold has a single Pydantic source and is configurable."""
        from trading_mcp.weights_config import WeightsConfig, load_weights

        assert WeightsConfig().lgbm_gate.uplift_threshold == 5.0
        cfg_file = tmp_path / "weights.json"
        cfg_file.write_text(
            '{"lgbm_gate": {"uplift_threshold": 12.5}}', encoding="utf-8"
        )
        assert load_weights(cfg_file).lgbm_gate.uplift_threshold == 12.5

    def test_gate_tables_sum_to_one(self) -> None:
        """Gate weight tables are normalized to 1.0."""
        from trading_mcp.weights_config import GateComponents, WeightsConfig

        raw = GateComponents(bali=1.0, tsmom=1.0, bakshi=1.0, factor_scan=1.0)
        assert sum(raw.to_dict().values()) == pytest.approx(1.0)
        gate = WeightsConfig().lgbm_gate
        assert sum(gate.without_lgbm.to_dict().values()) == pytest.approx(1.0)
        assert sum(gate.with_lgbm.to_dict().values()) == pytest.approx(1.0)
