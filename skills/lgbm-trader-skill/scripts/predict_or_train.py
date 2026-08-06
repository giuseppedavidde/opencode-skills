#!/usr/bin/env python3
"""Predict LGBM ensemble score for a ticker, auto-training if no model exists.

FAST PATH: model exists -> predict_live.py directly (instant).
SLOW PATH: no model -> run run_stacking.py --predict (trains + predicts, ~30-60s).

Never returns score=50 silently. Either a real trained prediction or an error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "saved"
PREDICT_SCRIPT = ROOT / "scripts" / "predict_live.py"
STACKING_SCRIPT = ROOT / "scripts" / "run_stacking.py"
VENV_PYTHON = os.environ.get("LGBM_VENV_PYTHON", sys.executable)


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


def predict(ticker: str, start: str = "2020-01-01") -> dict:
    """Get LGBM prediction for ticker, training first if needed."""
    models = _find_models(ticker)

    if not models:
        return _train_and_predict(ticker, start)

    output = _predict_direct(ticker)
    if output.get("model") is not None:
        return output

    # Model file exists but is unusable -> retrain.
    print(
        f"[LGBM] Model {models[0].name} unusable: "
        f"{output.get('error', 'unknown')}. Retraining...",
        file=sys.stderr,
    )
    return _train_and_predict(ticker, start)


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
    print(f"{'=' * 50}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Predict LGBM score (auto-train if no model exists)"
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--start",
        default="2020-01-01",
        help="Training start date (only used if no model exists)",
    )
    args = parser.parse_args()

    result = predict(args.ticker, args.start)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)

    return 0 if result.get("model") else 1


if __name__ == "__main__":
    sys.exit(main())