#!/usr/bin/env python3
"""End-to-end LightGBM pipeline runner.

Steps:
  1. Load YAML config.
  2. Fetch OHLCV + macro data for the requested ticker.
  3. Compute all features.
  4. Build the triple-barrier target.
  5. Train LightGBM with walk-forward purged CV.
  6. Run a backtest on the in-sample ensemble predictions.
  7. Print metrics and feature importance.
  8. Persist the model to ``models/saved/{ticker}_lgbm_{date}.pkl``.

Usage::

    python scripts/run_pipeline.py --ticker AAPL --start 2022-01-01 \\
        --end 2024-01-01
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

import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))

from backtest.engine import BacktestEngine  # noqa: E402
from data.fetcher import fetch_macro, fetch_ohlcv  # noqa: E402
from features.pipeline import compute_all_features, get_feature_columns  # noqa: E402
from models.lgbm_trainer import LGBMTrainer  # noqa: E402
from signals.generator import generate_signal  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("run_pipeline")

DEFAULT_CONFIG = ROOT / "config" / "config.yaml"
MODEL_DIR = ROOT / "models" / "saved"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LightGBM trading pipeline")
    p.add_argument("--ticker", required=True, help="Ticker symbol (e.g. AAPL)")
    p.add_argument("--start", default=None, help="ISO start date")
    p.add_argument("--end", default=None, help="ISO end date")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
    p.add_argument("--no-macro", action="store_true", help="Skip macro features")
    p.add_argument(
        "--best-params",
        default=None,
        help="Path to JSON with best params from tune_model.py",
    )
    p.add_argument("--save-dir", default=str(MODEL_DIR), help="Where to save models")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    # ---------- data -------------------------------------------------- #
    logger.info("Fetching OHLCV for %s (start=%s end=%s)", args.ticker, args.start, args.end)
    ohlcv = fetch_ohlcv(args.ticker, start=args.start, end=args.end)
    if ohlcv.empty:
        logger.error("No OHLCV data for %s — aborting", args.ticker)
        return 1

    macro = None
    if not args.no_macro:
        macro = fetch_macro(start=cfg.data.start_date if not args.start else args.start, end=args.end)

    # ---------- features --------------------------------------------- #
    df = compute_all_features(ohlcv, macro_df=macro)
    if df.empty:
        logger.error("Feature frame empty after dropna — aborting")
        return 1

    # ---------- target ----------------------------------------------- #
    trainer = LGBMTrainer(cfg.model_dump(by_alias=True))
    if args.best_params:
        bp_path = Path(args.best_params)
        if not bp_path.exists():
            logger.error("best-params file not found: %s — aborting", bp_path)
            return 1
        with bp_path.open("r", encoding="utf-8") as fh:
            bp = json.load(fh)
        # Accept either the full wrapper or a bare params dict
        params = bp.get("best_params", bp) if isinstance(bp, dict) else bp
        trainer.set_params(params)
        logger.info("Loaded best params from %s", bp_path)
    df = trainer.create_target(df)
    df = df.dropna(subset=["target"])

    feature_cols = get_feature_columns(df)
    if not feature_cols:
        logger.error("No feature columns found — aborting")
        return 1

    X = df[feature_cols]
    y = df["target"]
    dates = df.index

    # ---------- training --------------------------------------------- #
    trainer.train(X, y, dates)
    if not trainer.models:
        logger.error("Training produced no folds. Try a wider date range or smaller fold size.")
        return 1

    # ---------- predictions ------------------------------------------ #
    preds = trainer.predict(X.fillna(0.0))
    df = df.copy()
    df["raw_pred"] = preds
    df["score"] = _sigmoid(preds) * 100.0

    # ---------- backtest --------------------------------------------- #
    engine = BacktestEngine(cfg.model_dump(by_alias=True))
    bt = engine.run(df["close"], df["score"], timestamps=df.index)
    metrics = engine.metrics(bt)
    logger.info("Backtest metrics:\n%s", json.dumps(metrics, indent=2, default=float))

    # ---------- feature importance ----------------------------------- #
    importance = trainer.feature_importance_df()
    if not importance.empty:
        top = importance.loc["mean"].sort_values(ascending=False).head(15)
        logger.info("Top 15 features:\n%s", top.to_string())

    # ---------- signal example (last bar) --------------------------- #
    last_score = float(df["score"].iloc[-1])
    sig = generate_signal(last_score, threshold=cfg.trading.min_score_threshold)
    logger.info("Latest bar signal for %s: %s (score=%.2f)", args.ticker, sig["direction"], last_score)

    # ---------- persistence ------------------------------------------ #
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = save_dir / f"{args.ticker}_lgbm_{stamp}.pkl"
    trainer.save(out_path)
    logger.info("Model saved to %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())