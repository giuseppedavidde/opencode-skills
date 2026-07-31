"""Meta-labeling analysis: TrendlineBreakout quality scoring with ML filtering."""

from __future__ import annotations

import logging
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

logger = logging.getLogger(__name__)


def generate_features(hist: pd.DataFrame, lookback: int = 30) -> dict:  # pylint: disable=too-many-locals
    """Genera le feature di meta-labeling per l'ultima barra."""
    if len(hist) < lookback + 1:
        return {
            "features": {
                "resist_s": 0.0,
                "tl_err": 0.0,
                "vol": 1.0,
                "max_dist": 0.0,
                "adx": 0.0,
            },
            "breakout": False,
            "atr": 0.0,
        }

    high = hist["High"].values
    low = hist["Low"].values
    close = hist["Close"].values
    volume = hist["Volume"].values

    # ATR rolling 20
    tr = np.maximum(
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    )
    atr_arr = np.concatenate([[np.nan], tr])
    atr_series = pd.Series(atr_arr).rolling(20).mean()
    atr_val = float(atr_series.iloc[-1])
    if np.isnan(atr_val) or atr_val <= 0:
        atr_val = float(np.nanmean(atr_arr[-20:])) if len(atr_arr) >= 20 else 0.01

    # Trendline fit on log-close window
    log_close = np.log(close)
    window = log_close[-lookback:]
    x = np.arange(len(window))
    coefs = np.polyfit(x, window, 1)
    line_vals = coefs[0] * x + coefs[1]
    resist_slope = coefs[0]

    # Feature 1: resist_s_normalized
    resist_s_normalized = resist_slope / atr_val if atr_val > 0 else 0.0

    # Feature 2: tl_error
    err = float(np.mean(line_vals - window))
    tl_err = err / atr_val if atr_val > 0 else 0.0

    # Feature 3: vol_ratio
    vol_20 = float(np.mean(volume[-20:]))
    last_vol = float(volume[-1])
    vol_ratio = last_vol / vol_20 if vol_20 > 0 else 1.0

    # Feature 4: max_dist
    diff = line_vals - window
    max_dist = float(np.max(diff)) / atr_val if atr_val > 0 else 0.0

    # Feature 5: ADX
    w_high = high[-lookback:]
    w_low = low[-lookback:]
    high_diff = np.diff(w_high)
    low_diff = np.diff(w_low)
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)

    tr_window = tr[-lookback + 1 :] if len(tr) >= lookback else tr
    atr_window = pd.Series(tr_window).rolling(14).mean().values
    plus_di = 100 * pd.Series(plus_dm).rolling(14).mean() / (atr_window + 1e-10)
    minus_di = 100 * pd.Series(minus_dm).rolling(14).mean() / (atr_window + 1e-10)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx_val = float(dx.mean())

    # Breakout detection
    current_resist = coefs[1] + (lookback - 1) * coefs[0]
    current_close_log = float(log_close[-1])
    breakout = current_close_log > current_resist

    return {
        "features": {
            "resist_s": round(resist_s_normalized, 4),
            "tl_err": round(tl_err, 4),
            "vol": round(vol_ratio, 4),
            "max_dist": round(max_dist, 4),
            "adx": round(adx_val, 2),
        },
        "breakout": breakout,
        "atr": round(atr_val, 4),
    }


class MetaLabelModel:
    """Meta-labeling model: RandomForest che filtra i segnali."""

    MODEL_DIR = Path("/home/giuseppe/.config/opencode/models")

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.model_path = self.MODEL_DIR / f"metalabel_{ticker}.pkl"
        self.model: RandomForestClassifier | None = None
        self._load_model()

    def train(self, features_df: pd.DataFrame, labels: pd.Series) -> None:
        """Addestra il modello su dati storici."""
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.model = RandomForestClassifier(
            n_estimators=500,
            max_depth=3,
            random_state=69420,
            class_weight="balanced",
        )
        self.model.fit(features_df.values, labels.values)
        with open(self.model_path, "wb") as f:
            pickle.dump(self.model, f)

    def predict(self, features: dict) -> tuple[float, float]:
        """Restituisce (prob_win: 0-1, prob_score: 0-100)."""
        if self.model is None:
            return 0.5, 50.0
        x = np.array(
            [[features[k] for k in ["resist_s", "tl_err", "vol", "max_dist", "adx"]]]
        )
        prob = float(self.model.predict_proba(x)[0, 1])
        return prob, round(prob * 100)

    def _load_model(self) -> None:
        """Carica il modello da disco se esiste."""
        if self.model_path.exists():
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)

    def needs_retrain(self, force: bool = False) -> bool:
        """True se il modello non esiste o e' scaduto (>7 giorni)."""
        if force or not self.model_path.exists():
            return True
        age = time.time() - self.model_path.stat().st_mtime
        return age > 7 * 86400


def _auto_train(ticker: str, hist: pd.DataFrame) -> None:
    """Auto-train del meta-model sul ticker specifico."""
    features_list = []
    labels_list = []

    close = hist["Close"].values
    for i in range(60, len(close) - 10):
        window_hist = hist.iloc[i - 30 : i]
        feat = generate_features(window_hist)
        if feat["breakout"]:
            future_ret = (close[i + 5] / close[i]) - 1
            label = 1 if future_ret > 0.02 else 0
            features_list.append(list(feat["features"].values()))
            labels_list.append(label)

    if len(features_list) >= 20:
        df = pd.DataFrame(
            features_list,
            columns=["resist_s", "tl_err", "vol", "max_dist", "adx"],
        )
        mml = MetaLabelModel(ticker)
        mml.train(df, pd.Series(labels_list))
        logger.info(
            "Meta-label model trained for %s: %d samples, %d wins",
            ticker,
            len(features_list),
            sum(labels_list),
        )


def compute_meta_label(hist: pd.DataFrame) -> tuple[int, str]:
    """Compute meta-label confidence score (0-100) for current setup.

    Valuta la qualita' del setup attuale basandosi su:
    - Breakout trendline: rilevato/non rilevato
    - Feature di qualita' (slope, error, volume, ADX)
    - Modello meta-label se disponibile

    Score:
    - 80+: Breakout confermato + meta-label prob > 0.6
    - 60-79: Breakout confermato, features decenti
    - 40-59: Nessun breakout chiaro, situazione neutrale
    - 20-39: Condizioni sfavorevoli
    - 0-19: Contro-trend, volume basso, ADX debole
    """
    if len(hist) < 60:
        return 50, "Insufficient history for meta-labeling"

    features = generate_features(hist)
    score = 50
    details = []

    # Breakout detection
    if features["breakout"]:
        score += 20
        details.append("Trendline breakout detected (+20)")

    # Feature-based scoring
    feat = features["features"]

    if feat["vol"] > 1.5:
        score += 15
        details.append(f"High vol {feat['vol']:.1f}x (+15)")
    elif feat["vol"] > 1.2:
        score += 5
        details.append(f"Above avg vol {feat['vol']:.1f}x (+5)")

    if feat["adx"] > 25:
        score += 10
        details.append(f"Strong trend ADX={feat['adx']:.0f} (+10)")
    elif feat["adx"] < 15:
        score -= 10
        details.append(f"Weak trend ADX={feat['adx']:.0f} (-10)")

    if feat["tl_err"] < 0.02:
        score += 10
        details.append("Clean trendline fit (+10)")

    # Meta-model prediction
    ticker = hist.attrs.get("ticker", "UNKNOWN")
    mml = MetaLabelModel(ticker)
    if mml.needs_retrain():
        try:
            _auto_train(ticker, hist)
            mml = MetaLabelModel(ticker)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Auto-train failed for %s, using neutral model", ticker,
                exc_info=True,
            )

    prob, _prob_score = mml.predict(feat)
    if prob > 0.6:
        score += 15
        details.append(f"ML confidence {prob:.0%} (+15)")
    elif prob < 0.4:
        score -= 15
        details.append(f"ML rejects ({prob:.0%}) (-15)")

    score = min(100, max(0, score))
    detail = " | ".join(details) if details else "Neutral setup (50)"
    return score, detail


def get_meta_label_setup(hist: pd.DataFrame) -> dict:
    """Helper che restituisce un dict completo con setup meta-label."""
    feat = generate_features(hist)
    ticker = hist.attrs.get("ticker", "UNKNOWN")
    mml = MetaLabelModel(ticker)
    prob, prob_score = mml.predict(feat["features"])
    return {
        "breakout": feat["breakout"],
        "features": feat["features"],
        "ml_probability": prob,
        "ml_confidence": prob_score,
        "model_trained": mml.model is not None,
        "atr": feat["atr"],
    }
