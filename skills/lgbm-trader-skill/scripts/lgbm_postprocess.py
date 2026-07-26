#!/usr/bin/env python3
"""LGBM post-processing: skill-based score adjustments.

Calcola 8 adjustment basati sulle skill di trading per correggere/aumentare
la confidenza dello score LGBM grezzo.

Uso:
    source /tmp/opencode/.venv/bin/activate
    python3 lgbm_postprocess.py --ticker GME --lgbm-score 67 --json
    python3 lgbm_postprocess.py --ticker LHX --lgbm-score 65
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class Adjustment:
    """Singolo adjustment calcolato da una skill."""
    skill: str
    delta: int       # -15 a +15
    confidence: str   # alta / media / bassa
    reason: str       # spiegazione breve
    data_available: bool = True


@dataclass
class PostProcessResult:
    """Risultato completo del post-processing."""
    ticker: str
    lgbm_raw_score: float
    adjusted_score: float
    total_adjustment: int
    adjustments: dict[str, dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


# ─── Helper ───────────────────────────────────────────────────────

def _safe_get(info: dict, key: str, default: Any = None) -> Any:
    """Prende un campo da info yfinance senza crash."""
    val = info.get(key, default)
    return val if val is not None and val != "" and val != "N/A" else default


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ─── 1. Wyckoff ───────────────────────────────────────────────────

def compute_wyckoff(hist: pd.DataFrame) -> Adjustment:
    """
    Cerca pattern Wyckoff basis:
    - Spring: nuovo minimo seguito da chiusura dentro il range + volume in aumento
    - SOS: barra rialzista su volume > media dopo un declino
    - Preliminary support / selling climax
    """
    if hist.empty or len(hist) < 50:
        return Adjustment("wyckoff-2-0", 0, "bassa",
                          "Dati insufficienti (< 50gg)")

    close = hist["Close"]
    low = hist["Low"]
    high = hist["High"]
    volume = hist["Volume"]
    avg_vol = volume.rolling(50).mean()
    vol_ratio = (volume / avg_vol).iloc[-1] if avg_vol.iloc[-1] > 0 else 1.0

    # Prezzo vs MA 20 e 50
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(hist) >= 50 else close.iloc[-1]
    price = close.iloc[-1]
    below_ma = price < ma20 and price < ma50

    # Spring detection: guarda ultimi 10gg
    lookback = hist.tail(20)
    recent_low = lookback["Low"].min()
    recent_idx = lookback["Low"].idxmin()
    row_idx = lookback.index.get_loc(recent_idx)
    
    spring_found = False
    if row_idx < len(lookback) - 3:
        # Il minimo è stato seguito da chiusure in salita
        after = lookback.iloc[row_idx:]
        if after["Close"].iloc[-1] > after["Close"].iloc[0] * 1.02:
            vol_at_low = lookback.iloc[row_idx]["Volume"]
            if vol_at_low > avg_vol.iloc[lookback.index.get_loc(recent_idx)] * 1.3:
                spring_found = True

    # SOS detection: barra rialzista forte su volume dopo un declino
    last_5 = hist.tail(5)
    decline = (close.iloc[-10] - close.iloc[-1]) / close.iloc[-10] > 0.05 if len(hist) >= 10 else False
    strong_up = last_5["Close"].iloc[-1] > last_5["Close"].iloc[0] * 1.03
    strong_vol = last_5["Volume"].iloc[-1] > avg_vol.iloc[-1] * 1.5

    # Scoring
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
    return Adjustment("wyckoff-2-0", delta, conf, reason)


# ─── 2. Volume Price Analysis ─────────────────────────────────────

def compute_vpa(hist: pd.DataFrame) -> Adjustment:
    """
    VPA: analisi volume su up/down days.
    Selling exhaustion = volume cala sui down day, up day su volume > media.
    Accumulation = volume sale sui up day, prezzi chiudono in range ristretto.
    """
    if hist.empty or len(hist) < 20:
        return Adjustment("volume-price-analysis", 0, "bassa",
                          "Dati insufficienti")

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

    # Selling exhaustion: volume down days < media, ultimo giorno up su vol
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

    # Ultimo giorno: up + volume alto?
    last = df.iloc[-1]
    if last["up"] and last["Volume"] > avg_vol * 1.5:
        delta += 3
        parts.append("ultimo giorno up su volume alto")
        conf = "alta"

    # Range contraction su basso volume (absorption)
    last_3 = df.tail(3)
    if last_3["range"].mean() < df["range"].quantile(0.3) and last_3["Volume"].mean() < avg_vol * 0.7:
        delta += 3
        parts.append("range contraction + basso vol (absorption)")

    reason = ", ".join(parts) if parts else "Nessun pattern VPA rilevato"
    return Adjustment("volume-price-analysis", delta, conf, reason)


# ─── 3. Volume Profile (semplificato) ─────────────────────────────

def compute_volume_profile(hist: pd.DataFrame) -> Adjustment:
    """
    Volume Profile semplificato: VWAP, posizione prezzo vs VWAP + deviazioni.
    Prezzo fuori da ±1σ = mean reversion setup.
    """
    if hist.empty or len(hist) < 20:
        return Adjustment("volume-profile", 0, "bassa", "Dati insufficienti")

    df = hist.tail(60).copy()
    price = df["Close"].iloc[-1]
    
    # VWAP cumulato
    df["vwap"] = (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()
    vwap = df["vwap"].iloc[-1]
    
    # Deviazione da VWAP
    df["dev"] = (df["Close"] - df["vwap"]) / df["vwap"]
    std_dev = df["dev"].std()
    current_dev = (price - vwap) / vwap

    delta = 0
    parts = []
    conf = "bassa"

    if current_dev < -1.0 * std_dev and current_dev > -2.5 * std_dev:
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

    # POC shift: confronta volume profile di prima metà vs seconda metà della finestra
    half = len(df) // 2
    first_half = df.iloc[:half]
    second_half = df.iloc[half:]
    
    if len(second_half) > 5:
        poc_first = _find_poc_price(first_half)
        poc_second = _find_poc_price(second_half)
        if poc_first is not None and poc_second is not None:
            poc_shift = (poc_second - poc_first) / poc_first
            if abs(poc_shift) > 0.02:  # shift > 2%
                direction = "su" if poc_shift > 0 else "giù"
                delta += (5 if poc_shift > 0 else -5)
                parts.append(f"POC shift {direction} del {abs(poc_shift)*100:.1f}%")
                conf = "alta"

    reason = ", ".join(parts) if parts else "Prezzo dentro range VWAP normale"
    return Adjustment("volume-profile", delta, conf, reason)


def _find_poc_price(df: pd.DataFrame) -> float | None:
    """Trova il prezzo con massimo volume (POC)."""
    if df.empty:
        return None
    bins = 20
    try:
        df["price_bin"] = pd.cut(df["Close"], bins=bins)
        poc = df.groupby("price_bin", observed=True)["Volume"].sum().idxmax()
        return poc.mid if hasattr(poc, 'mid') else poc.left
    except Exception:
        return None


# ─── 4. Trades About to Happen ────────────────────────────────────

def compute_tth(hist: pd.DataFrame) -> Adjustment:
    """
    TTH (Weis): stopping volume, cluster, narrow range dopo wide range.
    - Stopping volume = long lower wick su volume alto (rifiuto del prezzo)
    - Narrow range dopo wide range = absorption
    - Cluster di barre a basso range su volume = accumulazione
    """
    if hist.empty or len(hist) < 20:
        return Adjustment("trades-about-to-happen", 0, "bassa",
                          "Dati insufficienti")

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

    # Stopping volume: long lower wick + volume > 1.5x media
    last_3 = df.tail(3)
    for i in range(len(last_3)):
        row = last_3.iloc[i]
        if row["wick_ratio"] > 0.5 and row["Volume"] > avg_vol * 1.5 and row["Close"] > row["Low"]:
            delta += 6
            parts.append(f"stopping volume: long lower wick + vol alto ({row.name.date()})")
            conf = "alta"
            break

    # Narrow range dopo wide range (absorption)
    last_5 = df.tail(5)
    if len(last_5) >= 5:
        avg_range_5 = last_5["range"].mean()
        if avg_range_5 < avg_range * 0.6:
            # Range si sta contraendo
            vol_declining = last_5["Volume"].is_monotonic_decreasing if hasattr(last_5["Volume"], 'is_monotonic_decreasing') else False
            delta += 3
            parts.append("absorption: narrow range persistente")

    # Cluster: ultimi 5gg range < 70% media e prezzi laterali
    if last_5["range"].mean() < avg_range * 0.7:
        price_range = (last_5["Close"].max() - last_5["Close"].min()) / last_5["Close"].mean()
        if price_range < 0.03:  # range < 3%
            delta += 4
            parts.append("cluster: range stretto + prezzo laterale = accumulazione")
            conf = "alta" if delta > 5 else "media"

    reason = ", ".join(parts) if parts else "Nessun pattern TTH rilevato"
    return Adjustment("trades-about-to-happen", delta, conf, reason)


# ─── 5. Contrarian ────────────────────────────────────────────────

def compute_contrarian(info: dict, hist: pd.DataFrame) -> Adjustment:
    """
    Trading Against the Crowd: cerca sentiment estremo.
    - Short float alto = bearish estremo = contrarian bullish
    - VIX alto = panic = opportunità buy
    """
    delta = 0
    parts = []
    conf = "bassa"

    short_float = _safe_get(info, "shortPercentOfFloat")
    short_ratio = _safe_get(info, "shortRatio")

    if short_float is not None:
        sf = short_float * 100 if short_float < 1 else short_float
        if sf > 20:
            delta += 12
            parts.append(f"short float {sf:.1f}% = estremo bearish → contrarian buy")
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

    # Beta alto + downside = potenziale rimbalzo violento
    beta = _safe_get(info, "beta")
    if beta is not None and beta > 1.5:
        ret_1m = (hist["Close"].iloc[-1] / hist["Close"].iloc[-22] - 1) * 100 if len(hist) >= 22 else 0
        if ret_1m < -10:
            delta += 4
            parts.append(f"beta {beta:.1f} + drawdown {ret_1m:.0f}% = rimbalzo violento possibile")
            conf = "alta"

    reason = ", ".join(parts) if parts else "Nessun estremo di sentiment rilevato"
    return Adjustment("trading-against-the-crowd", delta, conf, reason)


# ─── 6. Options / IV Rank ─────────────────────────────────────────

def compute_options(ticker: str, stock: yf.Ticker) -> Adjustment:
    """
    Calcola IV rank da opzioni ATM del front month.
    IV rank alto (> 70) → premi cari → vendita favorita.
    IV rank basso (< 30) → premi economici → acquisto favorito.
    """
    try:
        expirations = stock.options
        if not expirations:
            return Adjustment("options-playbook", 0, "bassa",
                              "Nessuna scadenza opzioni disponibile",
                              data_available=False)

        # Usa il front month
        chain = stock.option_chain(expirations[0])
        if chain.calls.empty:
            return Adjustment("options-playbook", 0, "bassa", "Chain calls vuota")

        # Prendi strike ATM
        price = stock.history(period="5d")["Close"].iloc[-1]
        calls = chain.calls
        if "strike" not in calls.columns:
            return Adjustment("options-playbook", 0, "bassa", "Dati chain anomali")

        atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
        iv_current = atm_call["impliedVolatility"].values[0] if "impliedVolatility" in atm_call.columns else None

        if iv_current is None or iv_current == 0:
            return Adjustment("options-playbook", 0, "bassa",
                              "IV non disponibile", data_available=False)

        # Stima IV rank: guarda IV storica da yfinance (dati limitati)
        # Alternativa: usa il percentile di IV nell'ultimo anno da chain storiche
        # Per ora usiamo una proxy semplificata
        delta = 0
        parts = []
        conf = "bassa"

        iv_pct = iv_current * 100
        if iv_pct > 70:
            delta = 8
            parts.append(f"IV {iv_pct:.0f}% — alto, premi cari → short/credit spread")
            conf = "alta"
        elif iv_pct > 50:
            delta = 3
            parts.append(f"IV {iv_pct:.0f}% — moderato, strategie neutrali")
            conf = "media"
        elif iv_pct < 30:
            delta = -3
            parts.append(f"IV {iv_pct:.0f}% — basso, premi economici → long options")
            conf = "media"

        reason = ", ".join(parts)
        return Adjustment("options-playbook", delta, conf, reason)

    except Exception as e:
        return Adjustment("options-playbook", 0, "bassa",
                          f"Dati opzioni non disponibili: {e}",
                          data_available=False)


# ─── 7. Triple Barrier (Advances in Financial ML) ─────────────────

def compute_triple_barrier(hist: pd.DataFrame) -> Adjustment:
    """
    López de Prado: reward/risk ratio.
    - Top barrier: resistenza più vicina (massimo 20gg)
    - Bottom barrier: supporto più vicino (minimo 20gg)
    - Ratio = distanza top / distanza bottom
    - Se < 2 → penalizzazione. Se > 3 → bonus.
    """
    if hist.empty or len(hist) < 20:
        return Adjustment("advances-in-financial-ml", 0, "bassa",
                          "Dati insufficienti")

    price = hist["Close"].dropna().iloc[-1]
    lookback = hist.dropna().tail(30)
    
    support = lookback["Low"].min()
    resistance = lookback["High"].max()

    dist_up = (resistance - price) / price
    dist_down = (price - support) / price

    if dist_down <= 0.005:
        # Prezzo al minimo — usa ATR come bottom barrier proxy
        atr = (hist["High"] - hist["Low"]).tail(14).mean()
        dist_down = max(atr / price, 0.01)
        parts.append("prezzo al minimo: bottom barrier via ATR")

    ratio = dist_up / dist_down

    delta = 0
    parts = []
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

    # Bonus: prezzo vicino a supporto forte (minimo 30gg più vicino del 3%)
    if dist_down < 0.03 and dist_up / max(dist_down, 0.001) > 2:
        delta += 3
        parts.append("prezzo a supporto forte → asimmetria extra")

    reason = ", ".join(parts) if parts else f"Reward/risk {ratio:.2f}x — neutrale"
    return Adjustment("advances-in-financial-ml", delta, conf, reason)


# ─── 8. Factor Investing (Ang) ────────────────────────────────────

def compute_factors(info: dict, hist: pd.DataFrame) -> Adjustment:
    """
    Asset Management (Ang): quality, value, momentum, low-beta.
    Ogni fattore contribuisce ±delta.
    """
    delta = 0
    parts = []
    conf = "bassa"

    # Value
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

    # Quality
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

    # Momentum (6 mesi)
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

    # Low-beta
    beta = _safe_get(info, "beta")
    if beta is not None:
        if beta < 0.8:
            delta += 2
            parts.append(f"low-beta: {beta:.1f} (difensivo)")
        elif beta > 1.5:
            delta -= 2
            parts.append(f"beta: {beta:.1f} (alto, amplifica perdite)")

    reason = ", ".join(parts) if parts else "Nessun fattore rilevante"
    return Adjustment("asset-management-factor-investing", delta, conf, reason)


# ─── Main ─────────────────────────────────────────────────────────

def postprocess(ticker: str, lgbm_score: float = 50.0) -> PostProcessResult:
    """Esegue tutti i calcoli e restituisce il risultato."""
    warnings: list[str] = []

    # Fetch dati
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        info = stock.info
    except Exception as e:
        return PostProcessResult(
            ticker=ticker,
            lgbm_raw_score=lgbm_score,
            adjusted_score=lgbm_score,
            total_adjustment=0,
            adjustments={},
            warnings=[f"Errore fetch dati: {e}"],
        )

    if hist.empty:
        warnings.append("Nessun dato storico disponibile per questo ticker")

    # Pulisce NaN (es. ultimo giorno senza chiusura)
    hist = hist.dropna()

    if hist.empty:
        warnings.append("Dati storici vuoti dopo pulizia NaN")

    # Calcola adjustment
    adjustments = {}

    adj = compute_wyckoff(hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_vpa(hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_volume_profile(hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_tth(hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_contrarian(info, hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_options(ticker, stock)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_triple_barrier(hist)
    adjustments[adj.skill] = asdict(adj)

    adj = compute_factors(info, hist)
    adjustments[adj.skill] = asdict(adj)

    # Somma
    total_adj = sum(v["delta"] for v in adjustments.values())

    # Clip adjusted score a [0, 100]
    adjusted = max(0, min(100, lgbm_score + total_adj))

    return PostProcessResult(
        ticker=ticker,
        lgbm_raw_score=lgbm_score,
        adjusted_score=round(adjusted, 1),
        total_adjustment=total_adj,
        adjustments=adjustments,
        warnings=warnings,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LGBM post-processing: skill-based score adjustments"
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--lgbm-score", type=float, default=50.0,
                        help="Raw LGBM score (0-100)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON")
    parser.add_argument("--pretty", action="store_true",
                        help="Output JSON indentato (implica --json)")
    args = parser.parse_args()

    result = postprocess(args.ticker, args.lgbm_score)

    if args.json or args.pretty:
        indent = 2 if args.pretty else None
        print(json.dumps(asdict(result), indent=indent, default=str))
    else:
        _print_human(result)

    return 0


def _print_human(result: PostProcessResult) -> None:
    print(f"\n{'='*55}")
    print(f"  POST-PROCESSING: {result.ticker}")
    print(f"{'='*55}")
    print(f"  LGBM raw:         {result.lgbm_raw_score:>5.1f}/100")
    print(f"  Adjustment totale: {result.total_adjustment:>+5d}")
    print(f"  Adjusted score:   {result.adjusted_score:>5.1f}/100")
    print(f"{'='*55}")
    print(f"  {'Skill':<35} {'Δ':>4}  {'Conf':<6}")
    print(f"  {'─'*35} {'─'*4}  {'─'*6}")
    for skill, adj in result.adjustments.items():
        icon = "✓" if adj["data_available"] else "⚠"
        delta_str = f"{adj['delta']:+d}"
        print(f"  {icon} {skill:<33} {delta_str:>4}  {adj['confidence']:<6}")
        print(f"     {adj['reason']}")
    if result.warnings:
        print(f"\n  ⚠ Avvisi:")
        for w in result.warnings:
            print(f"     • {w}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    sys.exit(main())
