"""Quantitative signal tools: Bali, TS-MOM, Bakshi, LGBM.

Tutti i tool usano il DataProvider centralizzato per hist, info,
options_expirations E options_chain. Nessuna chiamata yfinance diretta.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from fastmcp import FastMCP

from trading_mcp.data.provider import data_provider
from trading_mcp.data.risk_free import get_risk_free_rate
from trading_mcp.data.result_cache import result_cache

logger = logging.getLogger(__name__)

# ── Pydantic output models ───────────────────────────────────────────

class BaliResult(BaseModel):
    """Output del tool bali_signals.

    P0 Aug 2026: available, available_bars, required_bars, error_is_blocking
    e composite_bali_score nullable. Default: available=False (failure path).
    """
    ticker: str
    available: bool = False
    spot: float | None = None
    rv: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None
    atm_straddle_iv: float | None = None
    rvol_ivol_spread: float | None = None
    cvol_pvol_spread: float | None = None
    rvol_ivol_score: float | None = None
    cvol_pvol_score: float | None = None
    composite_bali_score: float | None = None
    direction: str = "unavailable"
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 50
    paper_reference: dict[str, Any] = Field(default_factory=dict)

class TSMomResult(BaseModel):
    """Output del tool tsmom_signals.

    P0 Aug 2026: available, available_bars, required_bars, error_is_blocking
    e mom_score nullable. Default: available=False (failure path).
    """
    ticker: str
    available: bool = False
    price: float | None = None
    lookback_months: int = 12
    cum_return_lookback: float | None = None
    signal: int = 0
    ewma_vol: float | None = None
    vol_scaling: float | None = None
    position_size: float | None = None
    mom_score: float | None = None
    direction: str = "unavailable"
    pct_positive_months: float | None = None
    sharpe_lookback: float | None = None
    target_vol: float = 0.40
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 60
    paper_reference: dict[str, Any] = Field(default_factory=dict)

class BakshiVRP(BaseModel):
    """VRP estimate sub-model."""
    vrp_annualized: float = 0.0
    vrp_pct_of_premium: float = 0.0
    regime: str = "NORMAL_VOL"
    description: str = ""

class BakshiStrikeAnalysis(BaseModel):
    """Delta-hedged P&L per strike."""
    strike: float
    moneyness: float
    option_premium: float
    vega: float
    vega_ratio: float
    seller_profit_per_option: float
    seller_profit_per_contract: float
    buyer_loss_per_option: float
    vrp_pct_of_premium: float
    seller_profit_per_100_notional: float
    zone: str
    recommendation: str


# ── Bakshi VRP constants (MUST be defined before BakshiResult) ────────

# Bakshi & Kapadia (2003) — empirical params from Table 4, Figure 2.
# WARNING: These are CALIBRATED on S&P 500 only.
_VRP_SLOPE = 1.996
_VRP_INTERCEPT = -12.34
_VRP_CALIBRATION_SOURCE = "Bakshi & Kapadia (2003), Table 4 (S&P 500 only)"


class BakshiResult(BaseModel):
    """Output del tool bakshi_signals.

    P0 Aug 2026: added available_bars, required_bars for explicit
    short-history status.

    P1 Aug 2026: added calibration_status, calibration_source,
    calibrated flags. When no ticker-specific VRP history exists,
    calibrated=False and calibrated_vrp=None.

    P2 Aug 2026: added estimated_costs with per-contract commission
    and slippage estimates for delta-hedged positions.
    """
    ticker: str
    spot: float | None = None
    expiry: str | None = None
    dte: int = 30
    atm_iv: float | None = None
    atm_call_iv: float | None = None
    atm_put_iv: float | None = None
    vrp: BakshiVRP = Field(default_factory=BakshiVRP)
    strikes_analysis: list[BakshiStrikeAnalysis] = Field(default_factory=list)
    error: str | None = None
    available_bars: int = 0
    required_bars: int = 0
    paper_reference: dict[str, Any] = Field(default_factory=dict)
    calibration_status: str = "not_calibrated"
    calibration_source: str = _VRP_CALIBRATION_SOURCE
    calibrated: bool = False
    calibrated_vrp: float | None = None
    rate_source: str | None = None
    rate_as_of: str | None = None
    estimated_costs: dict[str, Any] | None = None

class LGBMResult(BaseModel):
    """Output del tool lgbm_predict.

    Di default non disponibile (``available=False``, ``score=None``,
    ``signal="unavailable"``). Solo i success path di ``lgbm_predict``
    impostano ``available=True`` con uno score valido.

    P0 August 2026: ``available_bars``, ``required_bars`` e ``reason``
    rendono esplicito il motivo di ``available=False`` quando la storia
    e' troppo corta per il lookback delle feature o per il modello.

    P1 August 2026: ``calibrated_probability`` e ``calibration_status``
    sono None/"not_calibrated" per default. Lo score 0-100 NON e'
    una probabilita' senza artifact di calibrazione validato OOS.
    """
    ticker: str
    available: bool = False
    score: float | None = None
    signal: str = "unavailable"
    model: str | None = None
    individual_signals: dict[str, float] = Field(default_factory=dict)
    meta_weights: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    error_is_blocking: bool = False
    available_bars: int = 0
    required_bars: int = 0
    reason: str = ""
    calibrated_probability: float | None = None
    calibration_status: str = "not_calibrated"


class PostProcessAdjustment(BaseModel):
    """Singolo adjustment calcolato da una skill."""
    skill: str
    delta: int = 0
    confidence: str = "bassa"
    reason: str = ""
    data_available: bool = True

class PostProcessResult(BaseModel):
    """Risultato completo del post-processing LGBM."""
    ticker: str
    lgbm_raw_score: float = 50.0
    adjusted_score: float = 50.0
    total_adjustment: int = 0
    adjustments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# LGBM model directory (relative to lgbm-trader-skill)
_LGBM_SKILL_DIR = Path.home() / ".config" / "opencode" / "skills" / "lgbm-trader-skill"
_LGBM_MODEL_DIR = _LGBM_SKILL_DIR / "models" / "saved"


# ── Helper functions ─────────────────────────────────────────────────

def _best_expiry_from_provider(ticker: str, min_dte: int = 30, max_dte: int = 90) -> str | None:
    """Trova la scadenza opzioni migliore usando DataProvider."""
    expirations = data_provider.get_options_expirations(ticker)
    if not expirations:
        return None

    today = datetime.now()
    best: str | None = None
    best_dte = 999

    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte and dte < best_dte:
            best = exp
            best_dte = dte

    # Fallback: >= 14 DTE
    if best is None:
        best_dte = 999
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
            dte = (exp_date - today).days
            if dte >= 14 and dte < best_dte:
                best = exp
                best_dte = dte

    # Ultimate fallback
    if best is None and expirations:
        best = expirations[0]

    return best


def _best_expiry_bakshi(ticker: str, min_dte: int = 14, max_dte: int = 90) -> str | None:
    """Trova la scadenza per Bakshi (14-90 DTE) usando DataProvider."""
    expirations = data_provider.get_options_expirations(ticker)
    if not expirations:
        return None

    today = datetime.now()
    best: str | None = None
    best_dte = 999

    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte and dte < best_dte:
            best = exp
            best_dte = dte

    # Fallback: >= 7 DTE
    if best is None:
        best_dte = 999
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
            dte = (exp_date - today).days
            if dte >= 7 and dte < best_dte:
                best = exp
                best_dte = dte

    if best is None and expirations:
        best = expirations[0]

    return best


def _realized_vol_from_provider(ticker: str, period: str = "1y") -> float:
    """Calcola RV annua dai rendimenti giornalieri usando DataProvider."""
    hist = data_provider.get_hist(ticker, period=period)
    if hist.empty or len(hist) < 10:
        raise ValueError(f"Dati insufficienti per {ticker}: {len(hist)} giorni")
    daily_returns = hist["Close"].pct_change().dropna()
    rv = float(daily_returns.std() * np.sqrt(252))
    return rv


def _black_scholes_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega di un'opzione (BS). Identico per call e put."""
    from scipy.stats import norm
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)


def _black_scholes_price(  # pylint: disable=too-many-positional-arguments
    S: float, K: float, T: float, r: float, sigma: float, opt_type: str = "call"
) -> float:
    """Prezzo BS."""
    from scipy.stats import norm
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if opt_type == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


# ── Postprocess helpers ───────────────────────────────────────────────

_SKILLS = [
    "wyckoff-2-0",
    "volume-price-analysis",
    "volume-profile",
    "trades-about-to-happen",
    "trading-against-the-crowd",
    "options-playbook",
    "advances-in-financial-ml",
    "asset-management-factor-investing",
]


def _safe_get(info: dict, key: str, default: Any = None) -> Any:
    val = info.get(key, default)
    return val if val is not None and val != "" and val != "N/A" else default


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _find_poc_price(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    bins = 20
    try:
        df_copy = df.copy()
        df_copy["price_bin"] = pd.cut(df_copy["Close"], bins=bins)
        poc = df_copy.groupby("price_bin", observed=True)["Volume"].sum().idxmax()
        return poc.mid if hasattr(poc, "mid") else poc.left
    except Exception:  # pylint: disable=broad-exception-caught
        return None


# ── 8 compute functions ───────────────────────────────────────────────

def _compute_wyckoff(hist: pd.DataFrame) -> PostProcessAdjustment:
    if hist.empty or len(hist) < 50:
        return PostProcessAdjustment(
            skill="wyckoff-2-0", delta=0, confidence="bassa",
            reason="Dati insufficienti (< 50gg)")
    close = hist["Close"]
    low = hist["Low"]
    high = hist["High"]
    volume = hist["Volume"]
    avg_vol = volume.rolling(50).mean()
    vol_ratio = (volume / avg_vol).iloc[-1] if avg_vol.iloc[-1] > 0 else 1.0
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(hist) >= 50 else close.iloc[-1]
    price = close.iloc[-1]
    below_ma = price < ma20 and price < ma50
    lookback = hist.tail(20)
    recent_low = lookback["Low"].min()
    recent_idx = lookback["Low"].idxmin()
    row_idx = lookback.index.get_loc(recent_idx)
    spring_found = False
    if row_idx < len(lookback) - 3:
        after = lookback.iloc[row_idx:]
        if after["Close"].iloc[-1] > after["Close"].iloc[0] * 1.02:
            vol_at_low = lookback.iloc[row_idx]["Volume"]
            if vol_at_low > avg_vol.iloc[lookback.index.get_loc(recent_idx)] * 1.3:
                spring_found = True
    last_5 = hist.tail(5)
    decline = (close.iloc[-10] - close.iloc[-1]) / close.iloc[-10] > 0.05 if len(hist) >= 10 else False
    strong_up = last_5["Close"].iloc[-1] > last_5["Close"].iloc[0] * 1.03
    strong_vol = last_5["Volume"].iloc[-1] > avg_vol.iloc[-1] * 1.5
    delta = 0
    parts = []
    conf = "bassa"
    if spring_found:
        delta += 10
        parts.append("spring su supporto")
        conf = "alta"
    if below_ma:
        delta -= 5
        parts.append("sotto MA (distribuzione)")
    if decline and strong_up and strong_vol:
        delta += 8
        parts.append("SOS bar post-declino")
        conf = "alta" if delta > 5 else "media"
    if vol_ratio < 0.7 and below_ma:
        delta += 3
        parts.append("volume in calo = selling exhaustion")
    reason = ", ".join(parts) if parts else "Nessun pattern Wyckoff rilevato"
    return PostProcessAdjustment(
        skill="wyckoff-2-0", delta=delta, confidence=conf, reason=reason)


def _compute_vpa(hist: pd.DataFrame) -> PostProcessAdjustment:
    if hist.empty or len(hist) < 20:
        return PostProcessAdjustment(
            skill="volume-price-analysis", delta=0, confidence="bassa",
            reason="Dati insufficienti")
    df = hist.tail(30).copy()
    df["return"] = df["Close"].pct_change()
    df["up"] = df["return"] > 0
    df["range"] = df["High"] - df["Low"]
    avg_vol = df["Volume"].mean()
    up_days = df[df["up"]]
    down_days = df[~df["up"]]
    delta = 0
    parts = []
    conf = "bassa"
    if len(down_days) > 0:
        down_vol_avg = down_days["Volume"].mean()
        if down_vol_avg < avg_vol * 0.8:
            delta += 3
            parts.append("volume in calo su down day (selling exhaustion)")
            conf = "media"
    if len(up_days) > 0:
        up_vol_avg = up_days["Volume"].mean()
        if up_vol_avg > avg_vol * 1.3 and up_days["range"].mean() < df["range"].mean():
            delta += 4
            parts.append("up day su volume alto, range stretto = accumulazione")
            conf = "alta"
    last = df.iloc[-1]
    if last["up"] and last["Volume"] > avg_vol * 1.5:
        delta += 3
        parts.append("ultimo giorno up su volume alto")
        conf = "alta"
    last_3 = df.tail(3)
    if last_3["range"].mean() < df["range"].quantile(0.3) and last_3["Volume"].mean() < avg_vol * 0.7:
        delta += 3
        parts.append("range contraction + basso vol (absorption)")
    reason = ", ".join(parts) if parts else "Nessun pattern VPA rilevato"
    return PostProcessAdjustment(
        skill="volume-price-analysis", delta=delta, confidence=conf, reason=reason)


def _compute_volume_profile(hist: pd.DataFrame) -> PostProcessAdjustment:
    if hist.empty or len(hist) < 20:
        return PostProcessAdjustment(
            skill="volume-profile", delta=0, confidence="bassa",
            reason="Dati insufficienti")
    df = hist.tail(60).copy()
    price = df["Close"].iloc[-1]
    df["vwap"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()
    vwap = df["vwap"].iloc[-1]
    df["dev"] = (df["Close"] - df["vwap"]) / df["vwap"]
    std_dev = df["dev"].std()
    current_dev = (price - vwap) / vwap
    delta = 0
    parts = []
    conf = "bassa"
    if -1.0 * std_dev > current_dev > -2.5 * std_dev:
        delta += 5
        parts.append(f"prezzo sotto VWAP di {abs(current_dev)*100:.1f}% = mean reversion")
        conf = "alta"
    elif current_dev < -2.5 * std_dev:
        delta += 8
        parts.append(f"prezzo ESTREMO sotto VWAP ({abs(current_dev)*100:.1f}%) = forte mean reversion")
        conf = "alta"
    elif current_dev > std_dev:
        delta -= 4
        parts.append(f"prezzo sopra VWAP ({current_dev*100:.1f}%) = estensione, cautela")
        conf = "media"
    half = len(df) // 2
    first_half = df.iloc[:half]
    second_half = df.iloc[half:]
    if len(second_half) > 5:
        poc_first = _find_poc_price(first_half)
        poc_second = _find_poc_price(second_half)
        if poc_first is not None and poc_second is not None:
            poc_shift = (poc_second - poc_first) / poc_first
            if abs(poc_shift) > 0.02:
                direction = "su" if poc_shift > 0 else "giu'"
                delta += (5 if poc_shift > 0 else -5)
                parts.append(f"POC shift {direction} del {abs(poc_shift)*100:.1f}%")
                conf = "alta"
    reason = ", ".join(parts) if parts else "Prezzo dentro range VWAP normale"
    return PostProcessAdjustment(
        skill="volume-profile", delta=delta, confidence=conf, reason=reason)


def _compute_tth(hist: pd.DataFrame) -> PostProcessAdjustment:
    if hist.empty or len(hist) < 20:
        return PostProcessAdjustment(
            skill="trades-about-to-happen", delta=0, confidence="bassa",
            reason="Dati insufficienti")
    df = hist.tail(30).copy()
    df["range"] = df["High"] - df["Low"]
    df["lower_wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]
    df["upper_wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
    df["wick_ratio"] = df["lower_wick"] / df["range"].replace(0, np.nan)
    df["body"] = abs(df["Close"] - df["Open"])
    df["body_pct"] = df["body"] / df["range"].replace(0, np.nan)
    avg_vol = df["Volume"].mean()
    avg_range = df["range"].mean()
    delta = 0
    parts = []
    conf = "bassa"
    last_3 = df.tail(3)
    for i in range(len(last_3)):
        row = last_3.iloc[i]
        if row["wick_ratio"] > 0.5 and row["Volume"] > avg_vol * 1.5 and row["Close"] > row["Low"]:
            delta += 6
            parts.append(f"stopping volume: long lower wick + vol alto ({row.name.date()})")
            conf = "alta"
            break
    last_5 = df.tail(5)
    if len(last_5) >= 5:
        avg_range_5 = last_5["range"].mean()
        if avg_range_5 < avg_range * 0.6:
            delta += 3
            parts.append("absorption: narrow range persistente")
    if last_5["range"].mean() < avg_range * 0.7:
        price_range = (last_5["Close"].max() - last_5["Close"].min()) / last_5["Close"].mean()
        if price_range < 0.03:
            delta += 4
            parts.append("cluster: range stretto + prezzo laterale = accumulazione")
            conf = "alta" if delta > 5 else "media"
    reason = ", ".join(parts) if parts else "Nessun pattern TTH rilevato"
    return PostProcessAdjustment(
        skill="trades-about-to-happen", delta=delta, confidence=conf, reason=reason)


def _compute_contrarian(info: dict, hist: pd.DataFrame) -> PostProcessAdjustment:
    delta = 0
    parts = []
    conf = "bassa"
    short_float = _safe_get(info, "shortPercentOfFloat")
    short_ratio = _safe_get(info, "shortRatio")
    if short_float is not None:
        sf = short_float * 100 if short_float < 1 else short_float
        if sf > 20:
            delta += 12
            parts.append(f"short float {sf:.1f}% = estremo bearish -> contrarian buy")
            conf = "alta"
        elif sf > 10:
            delta += 8
            parts.append(f"short float {sf:.1f}% = alto, potenziale squeeze")
            conf = "alta"
        elif sf > 5:
            delta += 3
            parts.append(f"short float {sf:.1f}% = moderato")
            conf = "media"
    if short_ratio is not None and short_ratio > 5:
        delta += 3
        parts.append(f"short ratio {short_ratio:.1f} giorni per coprire")
    beta = _safe_get(info, "beta")
    if beta is not None and beta > 1.5:
        ret_1m = (hist["Close"].iloc[-1] / hist["Close"].iloc[-22] - 1) * 100 if len(hist) >= 22 else 0
        if ret_1m < -10:
            delta += 4
            parts.append(f"beta {beta:.1f} + drawdown {ret_1m:.0f}% = rimbalzo violento possibile")
            conf = "alta"
    reason = ", ".join(parts) if parts else "Nessun estremo di sentiment rilevato"
    return PostProcessAdjustment(
        skill="trading-against-the-crowd", delta=delta, confidence=conf, reason=reason)


def _compute_options(ticker: str) -> PostProcessAdjustment:
    try:
        expirations = data_provider.get_options_expirations(ticker)
        if not expirations:
            return PostProcessAdjustment(
                skill="options-playbook", delta=0, confidence="bassa",
                reason="Nessuna scadenza opzioni disponibile", data_available=False)
        chain = data_provider.get_options_chain(ticker, expirations[0])
        if chain is None or chain.calls.empty:
            return PostProcessAdjustment(
                skill="options-playbook", delta=0, confidence="bassa",
                reason="Chain calls vuota")
        hist = data_provider.get_hist(ticker, period="5d")
        if hist.empty:
            return PostProcessAdjustment(
                skill="options-playbook", delta=0, confidence="bassa",
                reason="Prezzo non disponibile")
        price = hist["Close"].dropna().iloc[-1]
        calls = chain.calls
        if "strike" not in calls.columns or "impliedVolatility" not in calls.columns:
            return PostProcessAdjustment(
                skill="options-playbook", delta=0, confidence="bassa",
                reason="Dati chain anomali")
        atm_idx = int((calls["strike"] - price).abs().idxmin())
        iv_current = float(calls.loc[atm_idx, "impliedVolatility"])
        if iv_current <= 0:
            return PostProcessAdjustment(
                skill="options-playbook", delta=0, confidence="bassa",
                reason="IV non disponibile", data_available=False)
        delta = 0
        parts = []
        conf = "bassa"
        iv_pct = iv_current * 100
        if iv_pct > 70:
            delta = 8
            parts.append(f"IV {iv_pct:.0f}% — alto, premi cari -> short/credit spread")
            conf = "alta"
        elif iv_pct > 50:
            delta = 3
            parts.append(f"IV {iv_pct:.0f}% — moderato, strategie neutrali")
            conf = "media"
        elif iv_pct < 30:
            delta = -3
            parts.append(f"IV {iv_pct:.0f}% — basso, premi economici -> long options")
            conf = "media"
        reason = ", ".join(parts)
        return PostProcessAdjustment(
            skill="options-playbook", delta=delta, confidence=conf, reason=reason)
    except Exception as e:  # pylint: disable=broad-exception-caught
        return PostProcessAdjustment(
            skill="options-playbook", delta=0, confidence="bassa",
            reason=f"Dati opzioni non disponibili: {e}", data_available=False)


def _compute_triple_barrier(hist: pd.DataFrame) -> PostProcessAdjustment:
    if hist.empty or len(hist) < 20:
        return PostProcessAdjustment(
            skill="advances-in-financial-ml", delta=0, confidence="bassa",
            reason="Dati insufficienti")
    price = hist["Close"].dropna().iloc[-1]
    lookback = hist.dropna().tail(30)
    support = lookback["Low"].min()
    resistance = lookback["High"].max()
    dist_up = (resistance - price) / price
    dist_down = (price - support) / price
    parts = []
    if dist_down <= 0.005:
        atr = (hist["High"] - hist["Low"]).tail(14).mean()
        dist_down = max(atr / price, 0.01)
        parts.append("prezzo al minimo: bottom barrier via ATR")
    ratio = dist_up / dist_down
    delta = 0
    conf = "bassa"
    if ratio < 1.5:
        delta = -8
        parts.append(f"reward/risk {ratio:.2f}x — sfavorevole, downside > upside")
        conf = "alta"
    elif ratio < 2.0:
        delta = -4
        parts.append(f"reward/risk {ratio:.2f}x — borderline, non supera 2x")
        conf = "alta"
    elif ratio > 3.0:
        delta = 8
        parts.append(f"reward/risk {ratio:.2f}x — fortemente asimmetrico a favore")
        conf = "alta"
    elif ratio > 2.5:
        delta = 3
        parts.append(f"reward/risk {ratio:.2f}x — buono")
        conf = "media"
    if dist_down < 0.03 and dist_up / max(dist_down, 0.001) > 2:
        delta += 3
        parts.append("prezzo a supporto forte -> asimmetria extra")
    reason = ", ".join(parts) if parts else f"Reward/risk {ratio:.2f}x — neutrale"
    return PostProcessAdjustment(
        skill="advances-in-financial-ml", delta=delta, confidence=conf, reason=reason)


def _compute_factors(info: dict, hist: pd.DataFrame) -> PostProcessAdjustment:
    delta = 0
    parts = []
    conf = "bassa"
    pb = _safe_get(info, "priceToBook")
    pe = _safe_get(info, "trailingPE")
    if pb is not None:
        if pb < 1.5:
            delta += 5
            parts.append(f"value: P/B {pb:.1f} (sotto 1.5 = favorevole)")
            conf = "alta"
        elif pb > 4:
            delta -= 3
            parts.append(f"value: P/B {pb:.1f} (sopra 4 = richiede crescita)")
            conf = "media"
    de = _safe_get(info, "debtToEquity")
    roe = _safe_get(info, "returnOnEquity")
    profit_margin = _safe_get(info, "profitMargins")
    if de is not None:
        if de < 50:
            delta += 3
            parts.append(f"quality: D/E {de:.0f}% (basso)")
            conf = "media"
        elif de > 150:
            delta -= 5
            parts.append(f"quality: D/E {de:.0f}% (alto = rischioso)")
            conf = "alta"
        else:
            delta -= 2
            parts.append(f"quality: D/E {de:.0f}% (moderato)")
    if roe is not None:
        if roe > 0.15:
            delta += 3
            parts.append(f"quality: ROE {roe*100:.0f}% (forte)")
            conf = "media"
    if profit_margin is not None:
        if profit_margin > 0.15:
            delta += 2
            parts.append(f"quality: margine {profit_margin*100:.0f}% (buono)")
    if len(hist) >= 126:
        mom_6m = (hist["Close"].iloc[-1] / hist["Close"].iloc[-126] - 1) * 100
        if mom_6m > 20:
            delta += 4
            parts.append(f"momentum: +{mom_6m:.0f}% in 6m (forte)")
            conf = "alta" if delta > 5 else "media"
        elif mom_6m < -20:
            delta -= 4
            parts.append(f"momentum: {mom_6m:.0f}% in 6m (debole)")
            conf = "alta"
    beta = _safe_get(info, "beta")
    if beta is not None:
        if beta < 0.8:
            delta += 2
            parts.append(f"low-beta: {beta:.1f} (difensivo)")
        elif beta > 1.5:
            delta -= 2
            parts.append(f"beta: {beta:.1f} (alto, amplifica perdite)")
    reason = ", ".join(parts) if parts else "Nessun fattore rilevante"
    return PostProcessAdjustment(
        skill="asset-management-factor-investing", delta=delta, confidence=conf, reason=reason)


# ── Postprocess orchestrator ──────────────────────────────────────────

def _postprocess(ticker: str, lgbm_score: float = 50.0) -> PostProcessResult:
    warnings: list[str] = []
    hist = data_provider.get_hist(ticker, period="6mo")
    info = data_provider.get_info(ticker)
    if hist.empty:
        warnings.append("Nessun dato storico disponibile per questo ticker")
    hist = hist.dropna()
    if hist.empty:
        warnings.append("Dati storici vuoti dopo pulizia NaN")
    adjustments: dict[str, dict[str, Any]] = {}
    for adj_func in [
        ("wyckoff-2-0", _compute_wyckoff, (hist,)),
        ("volume-price-analysis", _compute_vpa, (hist,)),
        ("volume-profile", _compute_volume_profile, (hist,)),
        ("trades-about-to-happen", _compute_tth, (hist,)),
        ("trading-against-the-crowd", _compute_contrarian, (info, hist)),
        ("options-playbook", _compute_options, (ticker,)),
        ("advances-in-financial-ml", _compute_triple_barrier, (hist,)),
        ("asset-management-factor-investing", _compute_factors, (info, hist)),
    ]:
        _, func, args = adj_func
        adj = func(*args) if callable(func) else func
        adjustments[adj.skill] = adj.model_dump()
    total_adj = sum(v["delta"] for v in adjustments.values())
    adjusted = max(0.0, min(100.0, lgbm_score + total_adj))
    return PostProcessResult(
        ticker=ticker,
        lgbm_raw_score=lgbm_score,
        adjusted_score=round(adjusted, 1),
        total_adjustment=total_adj,
        adjustments=adjustments,
        warnings=warnings,
    )


# ── Tool registration ────────────────────────────────────────────────

def register_quant_tools(mcp_server: FastMCP, _skills_dir: str) -> None:
    """Registra i tool quantitativi (Bali, TS-MOM, Bakshi, LGBM) sull'MCP."""

    # ── 1. Bali & Hovakimian (2009) Volatility Spread Signals ────

    @mcp_server.tool()
    def bali_signals(ticker: str, period: str = "1y") -> dict[str, Any]:
        """Bali & Hovakimian (2009) volatility spread signals.

        Calcola 2 segnali cross-sectional dal paper:
          1. RVol–IVol spread (Volatility Risk Premium)
          2. CVol–PVol spread (Jump Risk)

        USA IL DATAPROVIDER invece di chiamare yfinance direttamente
        (cache hit garantito se analyze_stock e' stato chiamato prima).

        Args:
            ticker: Simbolo del titolo (es. 'AAPL', 'SPY').
            period: Periodo per il calcolo della RV (default: '1y').

        Returns:
            dict con scores 0-100 per ogni segnale + spread grezzi.
        """
        cache_params: dict[str, Any] = {"period": period}
        cached = result_cache.get("bali_signals", ticker, cache_params)
        if cached is not None:
            return cached

        # ── P0 short-history guard: almeno 50 barre per RV (non 10) ──
        _MIN_BALI_BARS = 50
        hist_rv = data_provider.get_hist(ticker, period=period)
        avail_bars = len(hist_rv.dropna()) if not hist_rv.empty else 0
        if avail_bars < _MIN_BALI_BARS:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Dati insufficienti per Bali volatility spread: "
                    f"{avail_bars} barre disponibili, richieste almeno "
                    f"{_MIN_BALI_BARS} per RV robusta."
                ),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()

        # 1. Realized Volatility da DataProvider
        try:
            rv = _realized_vol_from_provider(ticker, period)
        except ValueError as e:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=str(e),
                rv=0.0,
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()

        # 2. Spot price da DataProvider
        hist = data_provider.get_hist(ticker, period="5d")
        if hist.empty:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error="Dati OHLCV insufficienti",
                rv=round(rv, 4),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()
        clean = hist["Close"].dropna()
        if clean.empty:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error="Close prices all NaN",
                rv=round(rv, 4),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()
        spot = float(clean.iloc[-1])

        # 3. Scadenza opzioni da DataProvider
        expiry = _best_expiry_from_provider(ticker, min_dte=30, max_dte=90)
        logger.debug("Bali %s: scadenza scelta=%s", ticker, expiry)

        # 4. Opzioni chain via DataProvider
        try:
            if not expiry:
                return BaliResult(
                    ticker=ticker,
                    available=False,
                    error_is_blocking=True,
                    error="Nessuna scadenza opzioni disponibile",
                    rv=round(rv, 4),
                    spot=round(spot, 2),
                    available_bars=avail_bars,
                    required_bars=_MIN_BALI_BARS,
                    direction="unavailable",
                ).model_dump()
            opt = data_provider.get_options_chain(ticker, expiry)
            if opt is None:
                return BaliResult(
                    ticker=ticker,
                    available=False,
                    error_is_blocking=True,
                    error="Catena opzioni non disponibile",
                    rv=round(rv, 4),
                    spot=round(spot, 2),
                    available_bars=avail_bars,
                    required_bars=_MIN_BALI_BARS,
                    direction="unavailable",
                ).model_dump()
            calls = opt.calls
            puts = opt.puts
        except Exception as e:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Opzioni non disponibili: {e}",
                rv=round(rv, 4),
                spot=round(spot, 2),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()

        if calls.empty or puts.empty:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error="Catena opzioni vuota",
                rv=round(rv, 4),
                spot=round(spot, 2),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()

        # 5. Trova strike ATM
        idx_call = (calls["strike"] - spot).abs().idxmin()
        idx_put = (puts["strike"] - spot).abs().idxmin()
        atm_call_iv = float(calls.loc[idx_call, "impliedVolatility"])
        atm_put_iv = float(puts.loc[idx_put, "impliedVolatility"])
        atm_straddle_iv = (atm_call_iv + atm_put_iv) / 2

        # 6. Spreads
        rvol_ivol = rv - atm_straddle_iv
        cvol_pvol = atm_call_iv - atm_put_iv

        # 7. Scoring (stessa logica dello script originale)
        rvol_raw = float(np.clip(rvol_ivol, -0.20, 0.20))
        rvol_ivol_score = round((rvol_raw + 0.20) / 0.40 * 100, 1)

        cvol_raw = float(np.clip(cvol_pvol, -0.05, 0.10))
        cvol_pvol_score = round((cvol_raw + 0.05) / 0.15 * 100, 1)

        rvol_bullish = 100 - rvol_ivol_score
        composite_bali_score = round(rvol_bullish * 0.60 + cvol_pvol_score * 0.40, 1)

        if composite_bali_score >= 65:
            direction = "bullish"
        elif composite_bali_score <= 35:
            direction = "bearish"
        else:
            direction = "neutral"

        bali_result = BaliResult(
            ticker=ticker,
            available=True,
            spot=round(spot, 2),
            rv=round(rv, 4),
            atm_call_iv=round(atm_call_iv, 4),
            atm_put_iv=round(atm_put_iv, 4),
            atm_straddle_iv=round(atm_straddle_iv, 4),
            rvol_ivol_spread=round(rvol_ivol, 4),
            cvol_pvol_spread=round(cvol_pvol, 4),
            rvol_ivol_score=rvol_ivol_score,
            cvol_pvol_score=cvol_pvol_score,
            composite_bali_score=composite_bali_score,
            direction=direction,
            paper_reference={
                "title": "Volatility Spreads and Expected Stock Returns",
                "authors": ["Turan G. Bali", "Armen Hovakimian"],
                "year": 2009,
                "doi": "10.1287/mnsc.1090.1063",
                "findings": {
                    "rvol_ivol": (
                        "RVol–IVol spread: premium negativo −0.63%/−0.73% mese "
                        "(volatility risk premium). Long quando RV < IV."
                    ),
                    "cvol_pvol": (
                        "CVol–PVol spread: premium positivo +1.05%/+1.49% mese "
                        "(jump risk). Long quando Call IV > Put IV."
                    ),
                },
            },
        ).model_dump()

        result_cache.set("bali_signals", ticker, cache_params, bali_result)
        return bali_result


    # ── 2. Moskowitz, Ooi & Pedersen (2012) TS-MOM ───────────────

    @mcp_server.tool()
    def tsmom_signals(
        ticker: str,
        lookback_months: int = 12,
        skip_last_days: int = 21,
    ) -> dict[str, Any]:
        """Moskowitz, Ooi & Pedersen (2012) time series momentum.

        Calcola il TS-MOM signal:
          sign(return_{t-12:t-1}) con volatility scaling a target 40% annuo.

        USA IL DATAPROVIDER per i dati OHLCV.

        Args:
            ticker: Simbolo del titolo (es. 'AAPL', 'SPY').
            lookback_months: Mesi di lookback (default: 12).
            skip_last_days: Giorni da saltare (default: 21 ≈ 1 mese).

        Returns:
            dict con score TS-MOM 0-100, direzione, Sharpe stimato.
        """
        cache_params: dict[str, Any] = {
            "lookback_months": lookback_months,
            "skip_last_days": skip_last_days,
        }
        cached = result_cache.get("tsmom_signals", ticker, cache_params)
        if cached is not None:
            return cached

        # Fetch dati via DataProvider (cache hit se analyze_stock chiamato prima)
        _MIN_TSMOM_BARS = 60
        period_needed = f"{lookback_months + 3}mo"
        hist = data_provider.get_hist(ticker, period=period_needed)
        avail_tsmom = len(hist) if not hist.empty else 0

        if hist.empty or avail_tsmom < _MIN_TSMOM_BARS:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Dati insufficienti per TS-MOM: {avail_tsmom} barre "
                    f"disponibili, richieste almeno {_MIN_TSMOM_BARS}."
                ),
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        close = hist["Close"]
        returns = close.pct_change().dropna()

        # Lookback period: escludi ultimi skip_last_days giorni
        total_days = len(returns)
        start_idx = max(0, total_days - lookback_months * 21 - skip_last_days)
        end_idx = max(0, total_days - skip_last_days)

        if start_idx >= end_idx:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Dati insufficienti dopo skip: start={start_idx}, end={end_idx}",
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        lookback_returns = returns.iloc[start_idx:end_idx]
        recent_returns = returns.iloc[-min(126, len(returns)):]

        if len(lookback_returns) < 20:
            return TSMomResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Lookback troppo corto: {len(lookback_returns)} giorni",
                available_bars=avail_tsmom,
                required_bars=_MIN_TSMOM_BARS,
                direction="unavailable",
            ).model_dump()

        # TS-MOM signal (MOP 2012)
        cum_return = float((1 + lookback_returns).prod() - 1)
        signal = 1 if cum_return > 0 else -1

        # Volatility scaling (MOP 2012: target 40% annuo, EWMA vol)
        span = 60
        ewma_vol = float(recent_returns.ewm(span=span).std().iloc[-1] * np.sqrt(252))
        target_vol = 0.40
        vol_scaling = target_vol / max(ewma_vol, 0.05)
        position_size = signal * vol_scaling

        # Score 0-100
        raw_strength = float(np.clip(cum_return, -0.50, 0.50))
        mom_score = round((raw_strength + 0.50) / 1.0 * 100, 1)

        if mom_score >= 65:
            direction = "bullish"
        elif mom_score <= 35:
            direction = "bearish"
        else:
            direction = "neutral"

        # Sharpe ratio del TS-MOM nel lookback
        sharpe_lookback = float(
            lookback_returns.mean() / max(lookback_returns.std(), 1e-6) * np.sqrt(252)
        )

        # Percentuale mesi positivi
        monthly_rets = close.resample("ME").last().pct_change().dropna()
        monthly_lookback = monthly_rets.iloc[-lookback_months:]
        pct_positive = (
            float((monthly_lookback > 0).mean() * 100)
            if len(monthly_lookback) > 0
            else 50.0
        )

        tsmom_result = TSMomResult(
            ticker=ticker,
            available=True,
            price=round(float(close.iloc[-1]), 2),
            lookback_months=lookback_months,
            cum_return_lookback=round(float(cum_return), 4),
            signal=signal,
            ewma_vol=round(ewma_vol, 4),
            vol_scaling=round(float(vol_scaling), 4),
            position_size=round(float(position_size), 4),
            mom_score=mom_score,
            direction=direction,
            pct_positive_months=round(pct_positive, 1),
            sharpe_lookback=round(sharpe_lookback, 4),
            target_vol=target_vol,
            paper_reference={
                "title": "Time series momentum",
                "authors": ["Tobias J. Moskowitz", "Yao Hua Ooi", "Lasse Heje Pedersen"],
                "year": 2012,
                "journal": "Journal of Financial Economics",
                "signal_formula": "sign(return_{t-12:t-1}) con volatility scaling a target 40%",
                "key_finding": (
                    "Sharpe ratio > 1.0 su portafoglio diversificato cross-asset, "
                    "universale in 58 futures su 4 asset class"
                ),
            },
        ).model_dump()

        result_cache.set("tsmom_signals", ticker, cache_params, tsmom_result)
        return tsmom_result


    # ── 3. Bakshi & Kapadia (2003) VRP Analysis ──────────────────

    @mcp_server.tool()
    def bakshi_signals(
        ticker: str, expiry: str | None = None
    ) -> dict[str, Any]:
        """Bakshi & Kapadia (2003) volatility risk premium analysis.

        Delta-hedged gains and the negative market volatility risk premium.
        Analizza il VRP corrente, expected P&L per vari strikes, e fornisce
        suggerimenti operativi per VRP harvesting.

        USA IL DATAPROVIDER per dati OHLCV e expirations.

        Args:
            ticker: Simbolo del titolo (es. 'SPY', 'AAPL').
            expiry: Data scadenza opzioni (YYYY-MM-DD). Auto-seleziona se None.

        Returns:
            dict con VRP analysis, P&L per strike, suggerimenti operativi.
        """
        # 1. OHLCV e spot da DataProvider
        hist = data_provider.get_hist(ticker, period="1y")
        if hist.empty:
            return BakshiResult(
                ticker=ticker, error="Dati insufficienti"
            ).model_dump()

        # ── P0 short-history guard: servono almeno 63 barre per VRP ──
        _MIN_BAKSHI_BARS = 63
        clean_close = hist["Close"].dropna()
        avail_bars = len(clean_close)
        if avail_bars < _MIN_BAKSHI_BARS:
            return BakshiResult(
                ticker=ticker,
                error=(
                    f"Dati insufficienti per Bakshi VRP: {avail_bars} barre "
                    f"disponibili, richieste almeno {_MIN_BAKSHI_BARS}. "
                    f"Il calcolo del VRP richiede volatilita' realizzata "
                    f"robusta (~3 mesi di daily data)."
                ),
                available_bars=avail_bars,
                required_bars=_MIN_BAKSHI_BARS,
            ).model_dump()

        spot = float(clean_close.iloc[-1])

        # 2. Scadenza opzioni da DataProvider
        exp_date = expiry or _best_expiry_bakshi(ticker)

        # 3. Opzioni chain via DataProvider
        try:
            if not exp_date:
                return BakshiResult(
                    ticker=ticker, spot=round(spot, 2),
                    error="Nessuna scadenza opzioni disponibile",
                ).model_dump()
            opt = data_provider.get_options_chain(ticker, exp_date)
            if opt is None:
                return BakshiResult(
                    ticker=ticker, spot=round(spot, 2),
                    error="Catena opzioni non disponibile",
                ).model_dump()
            calls = opt.calls
            puts = opt.puts
        except Exception as e:
            return BakshiResult(
                ticker=ticker, spot=round(spot, 2), error=f"Opzioni non disponibili: {e}"
            ).model_dump()

        if calls.empty or puts.empty:
            return BakshiResult(
                ticker=ticker, spot=round(spot, 2), error="Catena opzioni vuota"
            ).model_dump()

        # 4. IV ATM
        idx_call = int((calls["strike"] - spot).abs().idxmin())
        idx_put = int((puts["strike"] - spot).abs().idxmin())
        atm_iv = float(calls.loc[idx_call, "impliedVolatility"])
        atm_put_iv = float(puts.loc[idx_put, "impliedVolatility"])
        avg_iv = (atm_iv + atm_put_iv) / 2

        # 5. DTE
        if exp_date:
            exp_dt = datetime.strptime(exp_date, "%Y-%m-%d")
            dte = max((exp_dt - datetime.now()).days, 1)
        else:
            dte = 30
        T_years = dte / 365.0
        rate_snapshot = get_risk_free_rate()
        r = rate_snapshot.value

        # 6. VRP stima (Bakshi empirical)
        iv_pct_val = avg_iv * 100
        vrp_pct_raw = _VRP_SLOPE * iv_pct_val + _VRP_INTERCEPT
        vrp_pct = max(0.0, min(35.0, vrp_pct_raw))
        vrp_decimal = vrp_pct / 100.0

        if iv_pct_val < 10:
            regime = "LOW_VOL"
            desc = (
                f"Volatilita' bassa ({iv_pct_val:.0f}%): "
                f"VRP ~{vrp_pct:.1f}% del premio. Vendita opzioni meno profittevole."
            )
        elif iv_pct_val < 16:
            regime = "NORMAL_VOL"
            desc = (
                f"Volatilita' normale ({iv_pct_val:.0f}%): "
                f"VRP ~{vrp_pct:.1f}% del premio. Vendita opzioni con VRP moderato."
            )
        else:
            regime = "HIGH_VOL"
            desc = (
                f"Volatilita' alta ({iv_pct_val:.0f}%): "
                f"VRP ~{vrp_pct:.1f}% del premio. "
                f"VENDITA OPZIONI FORTEMENTE AGEVOLATA dal VRP."
            )

        vrp_model = BakshiVRP(
            vrp_annualized=round(vrp_decimal, 4),
            vrp_pct_of_premium=round(vrp_pct, 1),
            regime=regime,
            description=desc,
        )

        # 7. Analisi per strike
        all_strikes = sorted(set(calls["strike"].tolist()))
        atm_strike_idx = min(
            range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - spot)
        )

        half = 4
        start_s = max(0, atm_strike_idx - half)
        end_s = min(len(all_strikes), atm_strike_idx + half + 1)
        selected_strikes = all_strikes[start_s:end_s]

        strikes_analysis: list[BakshiStrikeAnalysis] = []
        atm_vega_val = _black_scholes_vega(spot, spot, T_years, r, avg_iv)

        for K in selected_strikes:
            vega = _black_scholes_vega(spot, K, T_years, r, avg_iv)
            premium = _black_scholes_price(spot, K, T_years, r, avg_iv, "call")
            expected_seller_profit_per_option = vrp_decimal * premium
            moneyness = spot / K
            vega_ratio = vega / atm_vega_val if atm_vega_val > 0 else 0

            if vega_ratio > 0.9:
                zone = "ATM — Alta esposizione VRP"
                rec = "Short piu' profittevole ma con massimo rischio gamma."
            elif vega_ratio > 0.6:
                zone = "Near-ATM — Media esposizione VRP"
                rec = "Buon compromesso tra raccolta premium e rischio."
            else:
                zone = "OTM/ITM — Bassa esposizione VRP"
                rec = "Raccolta premium ridotta ma minore rischio di gamma/vega."

            strikes_analysis.append(
                BakshiStrikeAnalysis(
                    strike=round(K, 2),
                    moneyness=round(moneyness, 4),
                    option_premium=round(premium, 4),
                    vega=round(vega, 4),
                    vega_ratio=round(vega_ratio, 4),
                    seller_profit_per_option=round(expected_seller_profit_per_option, 4),
                    seller_profit_per_contract=round(expected_seller_profit_per_option * 100, 2),
                    buyer_loss_per_option=round(-expected_seller_profit_per_option, 4),
                    vrp_pct_of_premium=round(vrp_pct, 1),
                    seller_profit_per_100_notional=round(
                        (expected_seller_profit_per_option / K) * 100, 2
                    ),
                    zone=zone,
                    recommendation=rec,
                )
            )

        # ── P2: ticker-specific VRP calibration artifact ─────────────
        calibrated_vrp = None
        calibration_status = "not_calibrated"
        calibration_source = _VRP_CALIBRATION_SOURCE
        try:
            vrp_artifact_path = (
                Path.home() / ".config/opencode/calibrations" /
                f"vrp_{ticker}.json"
            )
            if vrp_artifact_path.exists():
                with open(vrp_artifact_path) as af:
                    vrp_art = json.load(af)
                if vrp_art.get("status") in ("calibrated", "weak_calibrated"):
                    calibrated_vrp = (
                        vrp_art.get("calibrated_vrp_proxy")
                        or vrp_art.get("calibrated_vrp")  # backward compat
                    )
                    calibration_status = vrp_art["status"]
                    calibration_source = f"ticker-specific proxy: {vrp_artifact_path}"
        except (json.JSONDecodeError, OSError):
            pass

        return BakshiResult(
            ticker=ticker,
            spot=round(spot, 2),
            expiry=exp_date,
            dte=dte,
            atm_iv=round(avg_iv, 4),
            atm_call_iv=round(atm_iv, 4),
            atm_put_iv=round(atm_put_iv, 4),
            vrp=vrp_model,
            strikes_analysis=strikes_analysis,
            paper_reference={
                "title": "Delta-Hedged Gains and the Negative Market Volatility Risk Premium",
                "authors": ["Gurdip Bakshi", "Nikunj Kapadia"],
                "year": 2003,
                "journal": "The Review of Financial Studies",
                "doi": "10.1093/rfs/hhg002",
                "key_empirical": {
                    "atm_loss": (
                        "ATM S&P 500 call options lose ~$0.43 per option "
                        "(~8.2% of premium)"
                    ),
                    "negativity_rate": "68% of delta-hedged observations are negative",
                    "vol_dependence": (
                        "At 8% vol: −3.6% loss. At 16% vol: −19.6% loss "
                        "(of option value)"
                    ),
                },
            },
            calibration_status=calibration_status,
            calibration_source=calibration_source,
            calibrated=calibration_status in ("calibrated", "weak_calibrated"),
            calibrated_vrp=calibrated_vrp,
            rate_source=rate_snapshot.source_ticker,
            rate_as_of=rate_snapshot.as_of,
            estimated_costs={
                "commission_per_contract": 0.65,
                "slippage_bps_on_premium": 5.0,
                "per_strike_commission": round(0.65, 2),
                "note": (
                    "Costs are estimates for delta-hedged positions. "
                    "Slippage on the underlying is ~5bps per hedge "
                    "rebalance. Commissions are per option contract "
                    "(IBKR Pro tier). Actual costs depend on execution "
                    "quality and rebalancing frequency. Gross VRP is "
                    "always preserved in strikes_analysis."
                ),
            },
        ).model_dump()


    # ── 4. LGBM Stacking Ensemble Prediction ──────────────────────

    @mcp_server.tool()
    def lgbm_predict(ticker: str) -> dict[str, Any]:
        """LightGBM stacking ensemble prediction.

        Carica il modello LGBM pre-addestrato per il ticker e produce
        uno score 0-100 (stacking ensemble con meta-model).

        USA IL DATAPROVIDER per i dati OHLCV e macro (cache hit garantito
        se analyze_stock e' stato chiamato prima).

        Se non esiste un modello pre-addestrato, restituisce un errore
        esplicativo. Per addestrare un modello:
          python scripts/run_stacking.py --ticker {ticker} --start 2020-01-01

        Args:
            ticker: Simbolo del titolo (es. 'AAPL', 'GME').

        Returns:
            dict con score, signal, sub-model signals e meta-weights.
        """
        cache_params: dict[str, Any] = {}
        cached = result_cache.get("lgbm_predict", ticker, cache_params)
        if cached is not None:
            return cached

        # 1. Verifica che il package lgbm-trader-skill sia importabile
        if not _LGBM_SKILL_DIR.exists():
            return LGBMResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=(
                    "lgbm-trader-skill non trovato. Installa la skill prima di usare "
                    "questo tool: opencode skill install lgbm-trader-skill"
                ),
            ).model_dump()

        lgbm_root_str = str(_LGBM_SKILL_DIR)
        if lgbm_root_str not in sys.path:
            sys.path.insert(0, lgbm_root_str)

        try:
            from features.pipeline import compute_all_features  # type: ignore[import-untyped]
            from models.stacking import StackingEnsemble  # type: ignore[import-untyped]
            from models.lgbm_trainer import LGBMTrainer  # type: ignore[import-untyped]
        except ImportError as e:
            error_msg = str(e)
            if "lightgbm" in error_msg.lower() or "numba" in error_msg.lower():
                error_msg = (
                    f"LightGBM non disponibile in Python {sys.version_info.major}."
                    f"{sys.version_info.minor}. "
                    f"Usa: bash python3 "
                    f"~/.config/opencode/skills/lgbm-trader-skill/"
                    f"scripts/predict_or_train.py --ticker {ticker} --json"
                )
            else:
                error_msg = f"Impossibile importare lgbm-trader-skill: {e}"
            return LGBMResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=error_msg,
                model=None,
            ).model_dump()

        # 2. Cerca modello
        stacking_models = sorted(_LGBM_MODEL_DIR.glob(f"{ticker}_stacking_*.pkl"))
        single_models = sorted(_LGBM_MODEL_DIR.glob(f"{ticker}_lgbm_*.pkl"))

        model_file: Path | None = None
        model_kind: str = "none"

        if stacking_models:
            model_file = stacking_models[-1]
            model_kind = "stacking"
        elif single_models:
            model_file = single_models[-1]
            model_kind = "single"
        else:
            return LGBMResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Nessun modello trovato per {ticker}. "
                    f"Addestra con: python scripts/run_stacking.py --ticker {ticker} "
                    f"--start 2020-01-01"
                ),
            ).model_dump()

        # 3. Fetch dati live DAL DATAPROVIDER (non da yfinance)
        hist = data_provider.get_hist(ticker, period="5y")
        if hist.empty:
            return LGBMResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Nessun dato live per {ticker}",
            ).model_dump()

        # Converti nel formato atteso dalla pipeline LGBM (lowercase columns)
        ohlcv = pd.DataFrame({
            "open": hist["Open"],
            "high": hist["High"],
            "low": hist["Low"],
            "close": hist["Close"],
            "volume": hist["Volume"],
        })
        ohlcv.index = pd.to_datetime(ohlcv.index).tz_localize(None)
        ohlcv = ohlcv[~ohlcv.index.duplicated(keep="last")].sort_index()

        # 3b. Short-history check: il lookback canonico delle feature e' 252 barre.
        #     Se i dati sono insufficienti, restituiamo available=False esplicito
        #     senza tentare predizioni su dati incompleti.
        _FEATURE_LOOKBACK = 252
        _MIN_DAYS_FOR_PREDICT = 120  # minimo assoluto per qualsiasi predizione
        avail_bars = len(ohlcv)
        if avail_bars < _MIN_DAYS_FOR_PREDICT:
            return LGBMResult(
                ticker=ticker,
                model=model_file.name,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Dati insufficienti per LGBM prediction: {avail_bars} barre "
                    f"disponibili, richieste almeno {_MIN_DAYS_FOR_PREDICT} barre. "
                    f"Lookback canonico features: {_FEATURE_LOOKBACK} barre."
                ),
                available_bars=avail_bars,
                required_bars=_MIN_DAYS_FOR_PREDICT,
                reason="short_history",
            ).model_dump()
        if avail_bars < _FEATURE_LOOKBACK:
            return LGBMResult(
                ticker=ticker,
                model=model_file.name,
                available=False,
                error_is_blocking=True,
                error=(
                    f"Storia insufficiente per feature lookback: {avail_bars} barre "
                    f"disponibili, richieste {_FEATURE_LOOKBACK}. "
                    f"Non si predice su dati incompleti — lo score sarebbe spurio."
                ),
                available_bars=avail_bars,
                required_bars=_FEATURE_LOOKBACK,
                reason="short_history: feature lookback insufficiente",
            ).model_dump()

        # 4. Fetch macro (tentativo via data fetcher interno della skill)
        macro_df: pd.DataFrame | None = None
        try:
            from data.fetcher import fetch_macro  # type: ignore[import-untyped]
            macro_df = fetch_macro(start=ohlcv.index[0].strftime("%Y-%m-%d"))
        except Exception:
            logger.debug("Macro fetch fallito per %s, si procede senza", ticker)

        # 5. Calcola features
        try:
            df = compute_all_features(ohlcv, macro_df=macro_df, ticker=ticker, drop_na=False)
        except Exception as e:
            return LGBMResult(
                ticker=ticker,
                model=model_file.name,
                available=False,
                error_is_blocking=True,
                error=f"Feature computation failed: {e}",
            ).model_dump()

        if df.empty:
            return LGBMResult(
                ticker=ticker,
                model=model_file.name,
                available=False,
                error_is_blocking=True,
                error="Feature computation produced empty frame",
            ).model_dump()

        # 6. Predici
        try:
            if model_kind == "stacking":
                ensemble = StackingEnsemble.load(model_file)
                pred_result = _predict_stacking(ensemble, df)
            else:
                trainer = LGBMTrainer.load(model_file)
                pred_result = _predict_single(trainer, df)
        except Exception as e:
            logger.exception("Prediction failed for %s", ticker)
            return LGBMResult(
                ticker=ticker,
                model=model_file.name,
                available=False,
                error_is_blocking=True,
                error=f"Prediction failed: {e}",
            ).model_dump()

        lgbm_result = LGBMResult(
            ticker=ticker,
            model=model_file.name,
            available=True,
            **pred_result,
        ).model_dump()

        result_cache.set("lgbm_predict", ticker, cache_params, lgbm_result)
        return lgbm_result


    # ── 5. LGBM Post-Processing Skill Adjustments ────────────────

    @mcp_server.tool()
    def lgbm_postprocess(ticker: str, lgbm_score: float = 50.0) -> dict[str, Any]:
        """Post-processing dello score LGBM con 8 skill-adjustments.

        Applica correzioni basate sulle skill di trading per affinare
        la confidenza dello score LGBM grezzo. NON usa LightGBM — solo
        numpy, pandas, e DataProvider per i dati.

        Skill applicate:
          - wyckoff-2-0: pattern accumulazione/distribuzione
          - volume-price-analysis: selling exhaustion, absorption
          - volume-profile: VWAP deviation, POC shift
          - trades-about-to-happen: stopping volume, cluster
          - trading-against-the-crowd: short float, sentiment estremo
          - options-playbook: IV regime assessment
          - advances-in-financial-ml: triple barrier reward/risk
          - asset-management-factor-investing: value, quality, momentum

        Ogni skill contribuisce da -15 a +15 punti. Lo score finale
        e' il raw score + somma degli adjustment, clippato a [0, 100].

        Args:
            ticker: Simbolo del titolo (es. 'AAPL', 'GME').
            lgbm_score: Score LGBM grezzo 0-100 (default 50.0).

        Returns:
            dict con raw score, adjusted score, adjustment per skill.
        """
        return _postprocess(ticker, lgbm_score).model_dump()


# ── LGBM helper functions ─────────────────────────────────────────────

def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Sigmoid per convertire raw predictions in probabilita'."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def _signal_from_score(score: float) -> str:
    """Converte score 0-100 in segnale testuale."""
    if score >= 70:
        return "strong_long"
    if score >= 55:
        return "long"
    if score <= 30:
        return "strong_short"
    if score <= 45:
        return "short"
    return "neutral"


def _align_features(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Allinea lo schema feature al modello, fillando colonne mancanti e NaN.

    Colonne mancanti → riempite con 0.0 (lenient, come predict_live.py).
    NaN in colonne ESISTENTI → fill con 0.0 (convenzione predict_live.py:
    FD warmup, fundamental data gaps, RS trailing NaN diventano input
    neutri per LightGBM, che gestisce NaN nativamente se preferito).

    Args:
        df: DataFrame con le feature calcolate live.
        feature_names: Lista ordinata di feature attese dal modello.

    Returns:
        DataFrame allineato, tutte le colonne presenti, NaN fillati a 0.0.
    """
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        logger.info(
            "Aggiungo %d feature mancanti nei dati live (fill=0.0): %s",
            len(missing),
            missing[:5],
        )

    out = df.reindex(columns=feature_names, fill_value=0.0)
    nan_mask = out.isna()
    if nan_mask.any().any():
        nan_cols = out.columns[nan_mask.any()].tolist()
        nan_total = int(nan_mask.sum().sum())
        logger.debug(
            "Fill NaN con 0.0 in %d colonne (%d valori totali): %s",
            len(nan_cols), nan_total, nan_cols[:5]
        )
        out = out.fillna(0.0)

    return out


def _predict_stacking(ensemble: Any, df: pd.DataFrame) -> dict[str, Any]:
    """Predizione usando StackingEnsemble.

    Validazione strict dello schema feature: colonne mancanti → ValueError.
    NaN in colonne presenti → fill con 0.0 (convenzione predict_live.py:
    FD warmup, fundamental data gaps, RS trailing NaN diventano input neutri).
    La predizione usa l'ultima riga non-NaN dell'output.
    Il chiamante (lgbm_predict) converte ValueError in LGBMResult(available=False).
    """
    aligned = df.copy()
    if hasattr(ensemble, "feature_groups"):
        for _name, feats in ensemble.feature_groups.items():
            if not feats:
                continue
            aligned[feats] = _align_features(df, feats)

    preds = ensemble.predict(aligned)

    last_score = None
    if "score" in preds.columns and preds["score"].notna().any():
        last_score = float(preds["score"].dropna().iloc[-1])
    elif "pred_final" in preds.columns and preds["pred_final"].notna().any():
        last_score = float(
            _sigmoid(
                pd.Series(preds["pred_final"].dropna().iloc[-1:]).to_numpy()
            )
            * 100.0
        )
    else:
        pred_cols = [c for c in preds.columns if c.startswith("pred_")]
        if pred_cols:
            last_row = preds[pred_cols].iloc[-1].dropna()
            if not last_row.empty:
                last_score = float(_sigmoid(last_row.to_numpy()).mean()) * 100.0

    if last_score is None:
        raise ValueError(
            "Stacking ensemble non ha prodotto alcuna predizione valida "
            "(tutti i modelli base hanno fallito o restituito NaN)"
        )

    individual: dict[str, float] = {}
    for col in preds.columns:
        if col.startswith("pred_") and preds[col].notna().any():
            val = float(preds[col].dropna().iloc[-1])
            individual[col.replace("pred_", "")] = round(val, 4)

    meta_weights: dict[str, float] = {}
    if (
        hasattr(ensemble, "meta_model")
        and ensemble.meta_model is not None
        and hasattr(ensemble.meta_model, "feature_importances_")
        and hasattr(ensemble, "result")
        and ensemble.result is not None
    ):
        meta_feats = list(ensemble.result.feature_names)
        meta_weights = dict(
            zip(meta_feats, ensemble.meta_model.feature_importances_.tolist())
        )

    return {
        "score": round(last_score, 1),
        "signal": _signal_from_score(last_score),
        "individual_signals": individual,
        "meta_weights": meta_weights,
    }


def _predict_single(trainer: Any, df: pd.DataFrame) -> dict[str, Any]:
    """Predizione usando un singolo LGBMTrainer (fallback).

    Validazione strict dello schema feature. Lancia ValueError se mancano
    colonne o il modello non produce predizioni.
    """
    feats = list(trainer.feature_names)
    X = _align_features(df, feats)
    raw = trainer.predict(X)
    if len(raw) == 0:
        raise ValueError(
            "LGBMTrainer.predict ha restituito array vuoto — "
            "il modello non ha prodotto predizioni"
        )
    score = float(_sigmoid(np.asarray(raw))[-1]) * 100.0

    individual: dict[str, float] = {}
    if len(raw) > 0:
        individual["lgbm"] = round(float(raw[-1]), 4)

    return {
        "score": round(score, 1),
        "signal": _signal_from_score(score),
        "individual_signals": individual,
        "meta_weights": {},
    }
