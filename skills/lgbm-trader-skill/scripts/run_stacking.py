#!/usr/bin/env python3
"""Run stacking ensemble pipeline end-to-end.

Steps:
    1. Load YAML config.
    2. Fetch OHLCV + macro + options data.
    3. Compute all features.
    4. Build the triple-barrier target.
    5. Train the stacking ensemble (4 base models + meta-model).
    6. Backtest the ensemble.
    7. Train a single "full" model as baseline and compare Sharpe.
    8. Print metrics + feature importance.
    9. Persist the ensemble.

Usage::

    python scripts/run_stacking.py --ticker GME --start 2020-01-01
    python scripts/run_stacking.py --ticker AAPL --start 2020-01-01 --no-macro
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.engine import BacktestEngine  # noqa: E402
from data.fetcher import fetch_macro, fetch_ohlcv  # noqa: E402
from data.options_fetcher import build_historical_options_features  # noqa: E402
from features.pipeline import compute_all_features, get_feature_columns  # noqa: E402
from models.lgbm_trainer import LGBMTrainer  # noqa: E402
from models.stacking import StackingEnsemble  # noqa: E402
from signals.generator import generate_signal  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("run_stacking")

DEFAULT_CONFIG = ROOT / "config" / "config.yaml"
MODEL_DIR = ROOT / "models" / "saved"


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stacking ensemble pipeline")
    p.add_argument("--ticker", required=True, help="Ticker symbol (e.g. GME)")
    p.add_argument("--start", default=None, help="ISO start date")
    p.add_argument("--end", default=None, help="ISO end date")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
    p.add_argument("--no-macro", action="store_true", help="Skip macro features")
    p.add_argument("--no-options", action="store_true", help="Skip options features")
    p.add_argument("--save-dir", default=str(MODEL_DIR), help="Where to save models")
    p.add_argument(
        "--predict",
        action="store_true",
        help="Run live prediction after training (calls scripts/predict_live.py)",
    )
    p.add_argument(
        "--oof-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Backtest only on out-of-fold bars (default True). "
            "Use --no-oof-only to enable legacy behaviour on the full frame."
        ),
    )
    return p.parse_args()


def _backtest_scores(
    cfg_dict: dict,
    df: pd.DataFrame,
    score: pd.Series,
    oof_mask: pd.Series | None = None,
) -> dict:
    """Run backtest on a 0-100 score series and return its metrics.

    When ``oof_mask`` (boolean Series aligned to ``df.index``) is provided,
    only bars where it is ``True`` are fed to the engine. Otherwise every
    bar is used (legacy behaviour).
    """
    engine = BacktestEngine(cfg_dict)
    if oof_mask is not None:
        mask = oof_mask.reindex(df.index).fillna(False).astype(bool)
        df_bt = df.loc[mask]
        score_bt = score.reindex(df_bt.index)
        timestamps = df_bt.index
    else:
        df_bt = df
        score_bt = score
        timestamps = df.index
    bt = engine.run(df_bt["close"], score_bt, timestamps=timestamps)
    return engine.metrics(bt)


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    cfg_dict = cfg.model_dump(by_alias=True)

    # ---------- data -------------------------------------------------- #
    logger.info("Fetching OHLCV for %s (start=%s end=%s)", args.ticker, args.start, args.end)
    ohlcv = fetch_ohlcv(args.ticker, start=args.start, end=args.end)
    if ohlcv.empty:
        logger.error("No OHLCV data for %s", args.ticker)
        return 1

    macro: pd.DataFrame | None = None
    if not args.no_macro:
        macro = fetch_macro(
            start=cfg.data.start_date if not args.start else args.start,
            end=args.end,
        )

    options_df: pd.DataFrame | None = None
    if not args.no_options:
        try:
            options_df = build_historical_options_features(
                args.ticker,
                ohlcv,
                start_date=args.start,
                end_date=args.end,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Options features skipped: %s", exc)

    # ---------- features --------------------------------------------- #
    df = compute_all_features(
        ohlcv,
        macro_df=macro,
        options_df=options_df,
        ticker=args.ticker,
    )
    if df.empty:
        logger.error("Feature frame empty after dropna")
        return 1

    # ---------- target ----------------------------------------------- #
    trainer_base = LGBMTrainer(cfg_dict)
    df = trainer_base.create_target(df)
    df = df.dropna(subset=["target"])

    feature_cols = get_feature_columns(df)
    if not feature_cols:
        logger.error("No feature columns found")
        return 1

    # ---------- stacking training ------------------------------------ #
    ensemble = StackingEnsemble(cfg_dict)
    result = ensemble.train(df, feature_cols, df.index, cfg_dict)
    logger.info("Stacking metrics:\n%s", json.dumps(result.metrics, indent=2, default=str))

    # ---------- predictions + backtest ------------------------------- #
    preds = ensemble.predict(df)
    df = df.copy()
    for col in preds.columns:
        if col in df.columns:
            df = df.drop(columns=[col])
    df = df.join(preds)

    if "score" in df.columns and df["score"].notna().sum() > 0:
        bt_score = df["score"].fillna(50.0)
    else:
        pred_cols = [c for c in df.columns if c.startswith("pred_")]
        bt_score = df[pred_cols].mean(axis=1)
        bt_score = _sigmoid(bt_score.fillna(0.0).to_numpy()) * 100.0
        bt_score = pd.Series(bt_score, index=df.index)

    oof_mask = ensemble.oof_mask(df) if args.oof_only else None
    if args.oof_only:
        n_oof = int(oof_mask.sum()) if oof_mask is not None else 0
        logger.info("OOF-only mode: %d / %d bars used for ensemble backtest", n_oof, len(df))

    ensemble_metrics = _backtest_scores(cfg_dict, df, bt_score, oof_mask=oof_mask)
    logger.info("Ensemble backtest metrics:\n%s", json.dumps(ensemble_metrics, indent=2, default=float))

    # Ensemble metrics on the WHOLE frame too — for in-sample reference.
    if args.oof_only:
        full_ensemble_metrics = _backtest_scores(cfg_dict, df, bt_score, oof_mask=None)
        ens_sharpe = float(ensemble_metrics.get("sharpe", 0.0) or 0.0)
        full_sharpe = float(full_ensemble_metrics.get("sharpe", 0.0) or 0.0)
        logger.info("In-sample (full-frame) Sharpe: %.3f", full_sharpe)
        logger.info("OOF Sharpe: %.3f", ens_sharpe)
        max_dd = float(ensemble_metrics.get("max_drawdown", 0.0) or 0.0)
        logger.info("OOF Max DD: %.2f%%", max_dd * 100.0)

    # ---------- baseline single full-model for comparison ------------- #
    try:
        baseline_trainer = LGBMTrainer(cfg_dict)
        baseline_trainer.train(df[feature_cols], df["target"], df.index)
        if baseline_trainer.models:
            base_oof = baseline_trainer.predict_oof(df[feature_cols])
            base_oof_score = _sigmoid(base_oof.fillna(0.0).to_numpy()) * 100.0
            base_oof_score = pd.Series(base_oof_score, index=df.index)
            base_oof_score.loc[base_oof.isna()] = np.nan
            base_mask = base_oof_score.notna() if args.oof_only else None
            base_metrics = _backtest_scores(cfg_dict, df, base_oof_score, oof_mask=base_mask)
            logger.info(
                "Baseline (single full model, OOF) backtest metrics:\n%s",
                json.dumps(base_metrics, indent=2, default=float),
            )
            ens_sharpe = float(ensemble_metrics.get("sharpe", 0.0) or 0.0)
            base_sharpe = float(base_metrics.get("sharpe", 0.0) or 0.0)
            logger.info(
                "Sharpe comparison: ensemble=%.3f vs baseline=%.3f (delta=%.3f)",
                ens_sharpe,
                base_sharpe,
                ens_sharpe - base_sharpe,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Baseline comparison skipped: %s", exc)

    # ---------- feature importance ----------------------------------- #
    imp = ensemble.feature_importance_df()
    if not imp.empty:
        for col in imp.columns:
            top = imp[col].dropna().sort_values(ascending=False).head(10)
            logger.info("Top 10 features for '%s':\n%s", col, top.to_string())

    # ---------- signal (last bar) ------------------------------------ #
    last_score = float(df["score"].iloc[-1]) if "score" in df.columns else 50.0
    sig = generate_signal(last_score, threshold=cfg.trading.min_score_threshold)
    logger.info(
        "Latest signal for %s: %s (score=%.2f)",
        args.ticker,
        sig["direction"],
        last_score,
    )

    # ---------- persistence ------------------------------------------ #
    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = save_dir / f"{args.ticker}_stacking_{stamp}.pkl"
    ensemble.save(out_path)
    logger.info("Ensemble saved to %s", out_path)

    # ---------- live prediction (optional) ---------------------------- #
    if args.predict:
        try:
            import importlib.util  # noqa: PLC0415

            pl_path = ROOT / "scripts" / "predict_live.py"
            spec = importlib.util.spec_from_file_location("predict_live", pl_path)
            assert spec and spec.loader
            pl_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pl_mod)
            logger.info("Running live prediction with the freshly trained ensemble...")
            live = pl_mod.predict(args.ticker, model_path=str(out_path))
            logger.info(
                "Live prediction for %s: score=%s signal=%s",
                args.ticker,
                live.get("score"),
                live.get("signal"),
            )
            print(json.dumps(live, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live prediction skipped: %s", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())