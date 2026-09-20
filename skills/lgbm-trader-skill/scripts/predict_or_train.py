#!/usr/bin/env python3
"""Predict LGBM ensemble score for a ticker, gated train-if-needed.

FAST PATH: model exists -> predict_live.py directly (instant).
SLOW PATH: no model -> run run_stacking.py --predict (trains + predicts,
~30-60s). It is GATED: training is authorized only if the estimated composite
confidence uplift (with-LGBM vs. fallback baseline) reaches the configured
threshold (weights.json -> lgbm_gate.uplift_threshold, default 5.0 pts), or
with --force-train. Otherwise an explicit train-skipped result is returned and
the caller proceeds with the fallback signals.

Never returns score=50 silently. Either a real trained prediction, an explicit
error, or a gated skip.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "saved"
PREDICT_SCRIPT = ROOT / "scripts" / "predict_live.py"
STACKING_SCRIPT = ROOT / "scripts" / "run_stacking.py"
VENV_PYTHON = os.environ.get("LGBM_VENV_PYTHON", sys.executable)

# --- Train-vs-skip gate ---------------------------------------------------
# Single source of the threshold: weights_config.LgbmGateWeights
# (weights.json -> lgbm_gate.uplift_threshold). The constants below are a
# mirror used only when the MCP package is not importable; drift is locked by
# tests/test_lgbm_unavailable.py::TestTrainGate::test_threshold_single_source.
#
# Threshold rationale (default 5.0 pts on the 0-100 composite scale):
# cross-signal confidence noise sits around +/-5 pts, so a smaller uplift is
# not distinguishable from noise and does not justify the ~30-60s training
# cost nor the risk of overfitting a fresh model. 5 pts is the smallest
# uplift that is both measurable and decision-relevant; configurable via
# weights.json -> lgbm_gate.uplift_threshold (env override only as fallback).
_MCP_SRC = Path(__file__).resolve().parents[3] / "mcp" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

try:
    from trading_mcp.weights_config import get_weights  # pylint: disable=import-error

    _GATE: Any = get_weights().lgbm_gate
except ImportError:  # pragma: no cover - fallback mirror
    _GATE = None

_GATE_COMPONENTS: tuple[str, ...] = ("bali", "tsmom", "bakshi", "factor_scan")
_FALLBACK_THRESHOLD = 5.0
_FALLBACK_WITHOUT: dict[str, float] = {
    "bali": 0.30,
    "tsmom": 0.30,
    "bakshi": 0.20,
    "factor_scan": 0.20,
}
_FALLBACK_WITH: dict[str, float] = {
    "bali": 0.25,
    "tsmom": 0.25,
    "bakshi": 0.15,
    "factor_scan": 0.15,
    "lgbm": 0.20,
}


def _gate_settings() -> tuple[float, dict[str, float], dict[str, float]]:
    """Return (threshold, without_lgbm weights, with_lgbm weights)."""
    if _GATE is not None:
        return (
            float(_GATE.uplift_threshold),  # pylint: disable=no-member
            dict(_GATE.without_lgbm.to_dict()),  # pylint: disable=no-member
            dict(_GATE.with_lgbm.to_dict()),  # pylint: disable=no-member
        )
    threshold = float(os.environ.get("LGBM_GATE_UPLIFT_THRESHOLD", "5.0"))
    return threshold, dict(_FALLBACK_WITHOUT), dict(_FALLBACK_WITH)


def _gate_decision(
    fallback_confidence: dict[str, float] | None,
    force_train: bool,
) -> tuple[bool, dict]:
    """Decide whether on-demand training is worth it.

    Compares the estimated composite confidence with-LGBM against the
    without-LGBM fallback baseline and approves training only if the uplift
    reaches the configured threshold (inclusive). ``c_best = max(c_i)`` is an
    optimistic bound: it assumes LGBM agrees with the strongest fallback
    signal. Without confidence input the gate denies (no silent training).
    """
    if force_train:
        return True, {"gate": "forced", "decision": "train"}

    if not fallback_confidence:
        return False, {
            "gate": "skip",
            "reason": "no-confidence-input",
            "decision": "skip",
        }

    missing = [key for key in _GATE_COMPONENTS if key not in fallback_confidence]
    if missing:
        raise ValueError(f"fallback_confidence missing keys: {missing}")
    conf = {}
    for key in _GATE_COMPONENTS:
        value = float(fallback_confidence[key])
        if not 0.0 <= value <= 100.0:
            raise ValueError(f"confidence {key}={value} out of range [0, 100]")
        conf[key] = value

    threshold, weights_without, weights_with = _gate_settings()
    conf_without = sum(weights_without[key] * conf[key] for key in _GATE_COMPONENTS)
    c_best = max(conf[key] for key in _GATE_COMPONENTS)
    conf_with = sum(weights_with[key] * conf[key] for key in _GATE_COMPONENTS)
    conf_with += weights_with["lgbm"] * c_best
    uplift = conf_with - conf_without
    approve = uplift >= threshold
    metrics = {
        "conf_with_lgbm": round(conf_with, 2),
        "conf_without_lgbm": round(conf_without, 2),
        "uplift": round(uplift, 2),
        "threshold": round(threshold, 2),
        "decision": "train" if approve else "skip",
    }
    return approve, metrics


def _gate_skip_result(ticker: str, metrics: dict) -> dict:
    """Explicit train-skip result respecting the LGBMResult semantics."""
    if "reason" in metrics:
        reason = f"train-gate: {metrics['reason']}"
    else:
        reason = (
            f"train-gate: uplift {metrics.get('uplift')} < threshold "
            f"{metrics.get('threshold')}"
        )
    return {
        "ticker": ticker,
        "available": False,
        "score": None,
        "signal": "unavailable",
        "error": None,
        "error_is_blocking": False,
        "reason": reason,
        "model": None,
        "individual_signals": {},
        "meta_weights": {},
        "train_skipped": True,
        "gate": metrics,
    }


def predict(
    ticker: str,
    start: str = "2020-01-01",
    fallback_confidence: dict[str, float] | None = None,
    force_train: bool = False,
) -> dict:
    """Get LGBM prediction for ticker, training only if the gate approves."""
    models = _find_models(ticker)

    if not models:
        approve, metrics = _gate_decision(fallback_confidence, force_train)
        if not approve:
            return _gate_skip_result(ticker, metrics)
        return _train_and_predict(ticker, start)

    output = _predict_direct(ticker)
    if output.get("model") is not None:
        return output

    # Model file exists but is unusable -> retrain, still gated.
    approve, metrics = _gate_decision(fallback_confidence, force_train)
    if not approve:
        return _gate_skip_result(ticker, metrics)
    print(
        f"[LGBM] Model {models[0].name} unusable: "
        f"{output.get('error', 'unknown')}. Retraining...",
        file=sys.stderr,
    )
    return _train_and_predict(ticker, start)


def _find_models(ticker: str) -> list[Path]:
    """Return all model files for ticker, newest first."""
    stacking = sorted(MODEL_DIR.glob(f"{ticker}_stacking_*.pkl"), reverse=True)
    single = sorted(MODEL_DIR.glob(f"{ticker}_lgbm_*.pkl"), reverse=True)
    return stacking + single


def _extract_json_from_stdout(stdout: str) -> dict | None:
    """Extract the last JSON object from mixed stdout (logs + json).

    ``run_stacking.py --predict`` prints logs to stdout (StreamHandler(sys.stdout))
    AND the final live prediction via ``print(json.dumps(live, indent=2))``.
    Because the prediction JSON is pretty-printed (multi-line), the opening ``{``
    sits on its own line. We locate the last line whose stripped form starts with
    ``{`` and parse everything from that line to the end of stdout as a single
    JSON object. This works for both single-line and indent=2 multi-line output.
    """
    lines = stdout.strip().split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].lstrip().startswith("{"):
            continue
        candidate = "\n".join(lines[i:])
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            # Fall back to the single line alone (compact single-line JSON).
            try:
                obj = json.loads(lines[i])
            except json.JSONDecodeError:
                continue
        if isinstance(obj, dict):
            return obj
    return None


def _predict_direct(ticker: str) -> dict:
    """Fast path: use existing model."""
    cmd = [VENV_PYTHON, str(PREDICT_SCRIPT), "--ticker", ticker, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        output = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "ticker": ticker,
            "error": f"Predict output parse failed: {result.stderr[:500]}",
            "score": 50,
            "signal": "neutral",
            "model": None,
            "individual_signals": {},
            "meta_weights": {},
        }
    return output


def _train_and_predict(ticker: str, start: str) -> dict:
    """Slow path: train stacking ensemble, then predict."""
    print(
        f"[LGBM] No model for {ticker}. Training stacking ensemble "
        f"(start={start})...\n[LGBM] This takes ~30-60s...",
        file=sys.stderr,
    )

    cmd = [
        VENV_PYTHON,
        str(STACKING_SCRIPT),
        "--ticker",
        ticker,
        "--start",
        start,
        "--predict",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300, check=False
    )

    if result.returncode != 0:
        return {
            "ticker": ticker,
            "error": (
                f"Training failed (exit={result.returncode}): {result.stderr[:500]}"
            ),
            "score": 50,
            "signal": "neutral",
            "model": None,
            "individual_signals": {},
            "meta_weights": {},
        }

    output = _extract_json_from_stdout(result.stdout)
    if output is not None and output.get("model") is not None:
        return output

    error_detail = (
        output.get("error", "Unknown") if output
        else "No JSON prediction found in output"
    )
    return {
        "ticker": ticker,
        "error": f"Training done but prediction missing: {error_detail}",
        "score": 50,
        "signal": "neutral",
        "model": None,
        "individual_signals": {},
        "meta_weights": {},
    }


def _print_human(result: dict) -> None:
    status = "+" if result.get("model") else "X"
    print(f"\n{'=' * 50}")
    print(f"  LGBM TRADER -- {result.get('ticker', 'N/A')}")
    print(f"{'=' * 50}")
    print(f"  Score:  {result.get('score', 'N/A')}/100")
    print(f"  Signal: {str(result.get('signal', 'N/A')).upper()}")
    if result.get("model"):
        print(f"  Model:  {result['model']}")
    if result.get("individual_signals"):
        print(f"  Sub-signals: {result['individual_signals']}")
    if result.get("error"):
        print(f"  [{status}] {result['error']}")
    if result.get("train_skipped"):
        gate = result.get("gate", {})
        print(f"  [GATE] {result.get('reason', 'skip')}")
        if gate.get("uplift") is not None:
            print(
                f"  [GATE] uplift={gate.get('uplift')} "
                f"threshold={gate.get('threshold')}"
            )
    print(f"{'=' * 50}\n")


def main() -> int:
    """Parse CLI arguments and print the gated prediction result."""
    parser = argparse.ArgumentParser(
        description="Predict LGBM score (gated train-if-needed)"
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--start",
        default="2020-01-01",
        help="Training start date (only used when the gate approves training)",
    )
    parser.add_argument(
        "--fallback-confidence",
        type=json.loads,
        default=None,
        help=(
            "JSON of fallback signal confidence 0-100, e.g. "
            "'{\"bali\":80,\"tsmom\":30,\"bakshi\":40,\"factor_scan\":50}'. "
            "Required by the train-vs-skip gate."
        ),
    )
    parser.add_argument(
        "--force-train",
        action="store_true",
        help="Explicit on-demand override: train regardless of the gate.",
    )
    args = parser.parse_args()

    result = predict(
        args.ticker, args.start, args.fallback_confidence, args.force_train
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)

    if result.get("train_skipped"):
        return 2
    return 0 if result.get("model") else 1


if __name__ == "__main__":
    sys.exit(main())
