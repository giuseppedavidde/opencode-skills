#!/usr/bin/env python3
"""Predizione live per un ticker usando il modello stacking salvato.

Il trade agent chiama questo script per ottenere uno score 0-100
aggiuntivo, decorrelato dall'analisi fondamentale.

Workflow:
    1. Cerca il modello stacking piu' recente per ``ticker``.
    2. Se non c'e' stacking, fallback automatico al modello LGBM singolo.
    3. Se non c'e' nessun modello, restituisce score=50 / signal=neutral
       con un messaggio chiaro (mai crashare: il trade agent deve sempre
       ottenere una risposta).
    4. Fetcha dati live (OHLCV + macro), calcola le feature, predice.

Usage::

    python scripts/predict_live.py --ticker AAPL
    python scripts/predict_live.py --ticker GME --model models/saved/GME_stacking_20260713.pkl
    python scripts/predict_live.py --ticker SPY --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

from data.fetcher import fetch_macro  # noqa: E402
from features.pipeline import compute_all_features  # noqa: E402
from models.lgbm_trainer import LGBMTrainer  # noqa: E402
from models.stacking import StackingEnsemble  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger("predict_live")
MODEL_DIR = ROOT / "models" / "saved"


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def find_latest_model(ticker: str) -> tuple[Path | None, str]:
    """Trova il modello piu' recente per un ticker.

    Returns
    -------
    (path, kind)
        ``kind`` e' ``"stacking"`` o ``"single"``. ``(None, "none")`` se
        non c'e' nessun modello.
    """
    stacking = sorted(MODEL_DIR.glob(f"{ticker}_stacking_*.pkl"))
    if stacking:
        return stacking[-1], "stacking"

    single = sorted(MODEL_DIR.glob(f"{ticker}_lgbm_*.pkl"))
    if single:
        return single[-1], "single"

    return None, "none"


def fetch_live_data(
    ticker: str,
    period: str = "5y",
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Fetcha dati live per la predizione.

    Returns
    -------
    (ohlcv, macro)
        ``ohlcv`` e' un DataFrame con colonne minuscole
        (open/high/low/close/volume). ``macro`` e' il frame macro
        allineato o ``None`` se il fetch fallisce.
    """
    tk = yf.Ticker(ticker)
    hist = tk.history(period=period)
    if hist is None or hist.empty:
        logger.error("No data for %s", ticker)
        return pd.DataFrame(), None

    ohlcv = pd.DataFrame(
        {
            "open": hist["Open"],
            "high": hist["High"],
            "low": hist["Low"],
            "close": hist["Close"],
            "volume": hist["Volume"],
        }
    )
    ohlcv.index = pd.to_datetime(ohlcv.index).tz_localize(None)
    ohlcv = ohlcv[~ohlcv.index.duplicated(keep="last")].sort_index()

    macro: pd.DataFrame | None = None
    try:
        macro = fetch_macro(start=ohlcv.index[0].strftime("%Y-%m-%d"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Macro fetch failed: %s", exc)
        macro = None
    return ohlcv, macro


def _align_features(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Reindex ``df`` sulle feature attese dal modello, riempiendo i
    gap con 0.0 (le feature mancanti nei dati live diventano neutre)."""
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        logger.info(
            "Aggiungo %d feature mancanti nei dati live (fill=0.0): %s",
            len(missing),
            missing[:5],
        )
    out = df.reindex(columns=feature_names, fill_value=0.0)
    return out.fillna(0.0)


def _signal_from_score(score: float) -> str:
    if score >= 70:
        return "strong_long"
    if score >= 55:
        return "long"
    if score <= 30:
        return "strong_short"
    if score <= 45:
        return "short"
    return "neutral"


def _no_model_result(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "error": (
            f"No model found for {ticker}. Train one first with: "
            f"python scripts/run_stacking.py --ticker {ticker} --start 2020-01-01 "
            f"(or python scripts/run_pipeline.py --ticker {ticker})"
        ),
        "score": 50,
        "signal": "neutral",
        "model": None,
        "individual_signals": {},
        "meta_weights": {},
    }


def _predict_stacking(
    ensemble: StackingEnsemble,
    df: pd.DataFrame,
) -> dict:
    """Predizione usando StackingEnsemble. Restituisce score, signal,
    individual_signals e meta_weights."""
    # Allinea ogni feature group alle colonne attese
    aligned = df.copy()
    for _name, feats in ensemble.feature_groups.items():
        if not feats:
            continue
        aligned[feats] = _align_features(df, feats)

    preds = ensemble.predict(aligned)

    # Score: ultima riga non-NaN
    if "score" in preds.columns and preds["score"].notna().any():
        last_score = float(preds["score"].dropna().iloc[-1])
    elif "pred_final" in preds.columns and preds["pred_final"].notna().any():
        last_score = float(
            _sigmoid(pd.Series(preds["pred_final"].dropna().iloc[-1:]).to_numpy()) * 100.0
        )
    else:
        # fallback: media sigmoid dei pred_*
        pred_cols = [c for c in preds.columns if c.startswith("pred_")]
        if pred_cols:
            last_row = preds[pred_cols].iloc[-1].dropna()
            last_score = (
                float(_sigmoid(last_row.to_numpy()).mean()) * 100.0
                if not last_row.empty
                else 50.0
            )
        else:
            last_score = 50.0

    # Individual model signals (ultima riga non-NaN per ogni pred_*)
    individual: dict[str, float] = {}
    for col in preds.columns:
        if col.startswith("pred_") and preds[col].notna().any():
            val = float(preds[col].dropna().iloc[-1])
            individual[col.replace("pred_", "")] = round(val, 4)

    # Meta-model weights
    meta_imp: dict[str, int] = {}
    if (
        ensemble.meta_model is not None
        and hasattr(ensemble.meta_model, "feature_importances_")
        and ensemble.result is not None
    ):
        meta_feats = list(ensemble.result.feature_names)
        meta_imp = dict(
            zip(meta_feats, ensemble.meta_model.feature_importances_.tolist())
        )

    return {
        "score": round(last_score, 1),
        "signal": _signal_from_score(last_score),
        "individual_signals": individual,
        "meta_weights": meta_imp,
    }


def _predict_single(
    trainer: LGBMTrainer,
    df: pd.DataFrame,
) -> dict:
    """Predizione usando un singolo LGBMTrainer (fallback)."""
    feats = list(trainer.feature_names)
    X = _align_features(df, feats)
    raw = trainer.predict(X)
    if len(raw) == 0:
        score = 50.0
    else:
        score = float(_sigmoid(np.asarray(raw))[-1]) * 100.0

    return {
        "score": round(score, 1),
        "signal": _signal_from_score(score),
        "individual_signals": {"lgbm": round(float(raw[-1]), 4)} if len(raw) else {},
        "meta_weights": {},
    }


def predict(ticker: str, model_path: str | None = None) -> dict:
    """Genera predizione completa per un ticker.

    Args:
        ticker: Simbolo del ticker.
        model_path: Path al modello ``.pkl``. Se ``None``, cerca
            l'ultimo stacking salvato, con fallback al modello singolo.

    Returns:
        dict con ``ticker``, ``date``, ``price``, ``score`` (0-100),
        ``signal``, ``model``, ``individual_signals``, ``meta_weights``.
        Se non c'e' nessun modello, restituisce score=50 /
        signal=neutral con un campo ``error`` esplicativo.
    """
    if model_path:
        model_file = Path(model_path)
        if not model_file.exists():
            return {
                **_no_model_result(ticker),
                "error": f"Model path not found: {model_path}",
            }
        # determina kind dal nome file
        kind = "stacking" if "_stacking_" in model_file.name else "single"
    else:
        model_file, kind = find_latest_model(ticker)

    if model_file is None or kind == "none":
        return _no_model_result(ticker)

    # Fetch dati live
    ohlcv, macro = fetch_live_data(ticker)
    if ohlcv.empty:
        return {
            "ticker": ticker,
            "error": f"No live data for {ticker}",
            "score": 50,
            "signal": "neutral",
            "model": None,
            "individual_signals": {},
            "meta_weights": {},
        }

    df = compute_all_features(ohlcv, macro_df=macro, ticker=ticker, drop_na=False)
    if df.empty:
        return {
            "ticker": ticker,
            "error": "Feature computation produced an empty frame",
            "score": 50,
            "signal": "neutral",
            "model": model_file.name,
            "individual_signals": {},
            "meta_weights": {},
        }

    try:
        if kind == "stacking":
            ensemble = StackingEnsemble.load(model_file)
            pred = _predict_stacking(ensemble, df)
        else:
            trainer = LGBMTrainer.load(model_file)
            pred = _predict_single(trainer, df)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Prediction failed for %s", ticker)
        return {
            "ticker": ticker,
            "error": f"Prediction failed: {exc}",
            "score": 50,
            "signal": "neutral",
            "model": model_file.name,
            "individual_signals": {},
            "meta_weights": {},
        }

    current_price = float(ohlcv["close"].iloc[-1])
    last_date = ohlcv.index[-1].strftime("%Y-%m-%d")

    return {
        "ticker": ticker,
        "date": last_date,
        "price": round(current_price, 2),
        "model": model_file.name,
        **pred,
    }


def _print_human(result: dict) -> int:
    print(f"\n{'=' * 50}")
    print("  STACKING ENSEMBLE PREDICTION")
    print(f"{'=' * 50}")
    if result.get("error"):
        print(f"  ❌ ERROR: {result['error']}")
        print(f"  Score (fallback):  {result.get('score')}/100")
        print(f"  Signal:            {result.get('signal', 'neutral').upper()}")
        print(f"{'=' * 50}")
        return 1
    print(f"  Ticker:    {result['ticker']}")
    print(f"  Date:      {result.get('date', 'N/A')}")
    print(f"  Price:     ${result.get('price', 0):.2f}")
    print(f"  Score:     {result['score']}/100")
    print(f"  Signal:    {result['signal'].upper()}")
    print(f"{'=' * 50}")
    individual = result.get("individual_signals", {}) or {}
    if individual:
        print("  Individual model signals:")
        for name, val in individual.items():
            print(f"    {name:12s}: {val:>10.4f}")
        print(f"{'=' * 50}")
    meta_weights = result.get("meta_weights", {}) or {}
    if meta_weights:
        print("  Meta-model weights:")
        for name, val in meta_weights.items():
            print(f"    {name:12s}: {int(val):>4d}")
        print(f"{'=' * 50}")
    print(f"  Model: {result.get('model', 'N/A')}")
    print(f"{'=' * 50}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Live prediction using stacking ensemble")
    p.add_argument("--ticker", required=True, help="Ticker symbol")
    p.add_argument("--model", default=None, help="Path to .pkl model (optional)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    args = p.parse_args()
    
    if args.json:
        import logging
        logging.disable(logging.CRITICAL + 1)
    
    result = predict(args.ticker, args.model)
    
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        return _print_human(result)

    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())