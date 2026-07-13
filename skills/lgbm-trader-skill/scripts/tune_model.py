#!/usr/bin/env python3
"""CLI script to run Optuna hyperparameter tuning for the LightGBM model.

Pipeline:
  1. Load YAML config.
  2. Fetch OHLCV + macro data for the requested ticker.
  3. Compute all features.
  4. Build the triple-barrier target.
  5. Run :class:`LGBMTuner` (Optuna + walk-forward purged CV).
  6. Print best params and best value.
  7. Persist ``best_params`` to JSON (``models/saved/best_params_{ticker}.json``).

Usage::

    python scripts/tune_model.py --ticker AAPL --start 2020-01-01 \\
        --end 2024-01-01 --trials 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# allow running as a script from the repository root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from data.fetcher import fetch_macro, fetch_ohlcv  # noqa: E402
from features.pipeline import compute_all_features, get_feature_columns  # noqa: E402
from models.lgbm_trainer import LGBMTrainer  # noqa: E402
from models.tuner import LGBMTuner, TuningConfig, suggest_params_from_study  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("tune_model")

DEFAULT_CONFIG = ROOT / "config" / "config.yaml"
MODEL_DIR = ROOT / "models" / "saved"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description="Optuna tuning for LightGBM trading model")
    p.add_argument("--ticker", required=True, help="Ticker symbol (e.g. AAPL)")
    p.add_argument("--start", default=None, help="ISO start date")
    p.add_argument("--end", default=None, help="ISO end date")
    p.add_argument("--trials", type=int, default=50, help="Number of Optuna trials")
    p.add_argument(
        "--timeout", type=int, default=30, help="Timeout in minutes (default 30)"
    )
    p.add_argument(
        "--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml"
    )
    p.add_argument(
        "--no-macro", action="store_true", help="Skip macro features"
    )
    p.add_argument(
        "--output",
        default=None,
        help="Where to save best_params JSON "
        "(default: models/saved/best_params_{ticker}.json)",
    )
    p.add_argument(
        "--storage",
        default=None,
        help="Optuna storage URI (default: in-memory)",
    )
    p.add_argument(
        "--refit",
        action="store_true",
        help="Refit the model with best params and run a backtest",
    )
    return p.parse_args()


def main() -> int:
    """Entry point for the tuning CLI."""
    args = parse_args()
    cfg = load_config(args.config)
    cfg_dict = cfg.model_dump(by_alias=True)

    # ---------- data -------------------------------------------------- #
    logger.info(
        "Fetching OHLCV for %s (start=%s end=%s)", args.ticker, args.start, args.end
    )
    ohlcv = fetch_ohlcv(args.ticker, start=args.start, end=args.end)
    if ohlcv.empty:
        logger.error("No OHLCV data for %s — aborting", args.ticker)
        return 1

    macro = None
    if not args.no_macro:
        macro = fetch_macro(
            start=args.start if args.start else cfg.data.start_date,
            end=args.end,
        )

    # ---------- features --------------------------------------------- #
    df = compute_all_features(ohlcv, macro_df=macro)
    if df.empty:
        logger.error("Feature frame empty after dropna — aborting")
        return 1

    # ---------- target ----------------------------------------------- #
    # Reuse the trainer only to build the target (no training here).
    trainer = LGBMTrainer(cfg_dict)
    df = trainer.create_target(df)
    df = df.dropna(subset=["target"])

    feature_cols = get_feature_columns(df)
    if not feature_cols:
        logger.error("No feature columns found — aborting")
        return 1

    X = df[feature_cols]
    y = df["target"]
    dates = df.index

    # ---------- tuning ----------------------------------------------- #
    tuning_cfg = TuningConfig(
        n_trials=args.trials,
        timeout_minutes=args.timeout,
        storage=args.storage,
    )
    tuner = LGBMTuner(X=X, y=y, dates=dates, config=cfg_dict, tuning_config=tuning_cfg)
    result = tuner.run()

    best_params = result["best_params"]
    best_value = result["best_value"]
    logger.info("Best value: %.4f", best_value)
    logger.info("Best params: %s", json.dumps(best_params, indent=2, default=float))

    # ---------- persist best params ---------------------------------- #
    out_path = Path(args.output) if args.output else MODEL_DIR / f"best_params_{args.ticker}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "ticker": args.ticker,
                "best_value": float(best_value),
                "best_params": best_params,
                "n_trials": args.trials,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            fh,
            indent=2,
            default=float,
        )
    logger.info("Best params saved to %s", out_path)

    # ---------- optional refit + backtest --------------------------- #
    if args.refit:
        logger.info("Refitting model with best params and running a backtest...")
        merged_params = suggest_params_from_study(
            result["study"], base_params=cfg_dict["model"]["params"]
        )
        refit_cfg = dict(cfg_dict)
        refit_cfg["model"] = dict(cfg_dict.get("model", {}))
        refit_cfg["model"]["params"] = merged_params
        refit_trainer = LGBMTrainer(refit_cfg)
        refit_trainer.train(X, y, dates)
        if not refit_trainer.models:
            logger.warning("Refit produced no folds — skipping backtest")
        else:
            from backtest.engine import BacktestEngine

            preds = refit_trainer.predict(X.fillna(0.0))
            score_df = df.copy()
            score_df["raw_pred"] = preds
            score_df["score"] = (
                1.0 / (1.0 + np.exp(-np.clip(preds, -50.0, 50.0)))
            ) * 100.0
            engine = BacktestEngine(refit_cfg)
            bt = engine.run(
                score_df["close"], score_df["score"], timestamps=score_df.index
            )
            metrics = engine.metrics(bt)
            logger.info("Refit backtest metrics:\n%s", json.dumps(metrics, indent=2, default=float))

    return 0


if __name__ == "__main__":
    sys.exit(main())