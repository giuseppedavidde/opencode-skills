#!/usr/bin/env python3
"""
Bali & Hovakimian (2009) Volatility Spread Signals.

Calcola 2 segnali cross-sectional dal paper:
  1. RVol–IVol spread (Volatility Risk Premium)
  2. CVol–PVol spread (Jump Risk)

Usage:
  python3 bali_signals.py AAPL
  python3 bali_signals.py SPY --expiry 2026-07-17
  python3 bali_signals.py AAPL --period 6mo  # per RV su finestra più corta

Output: JSON con scores 0-100 per ogni segnale + spread grezzi.
"""

import argparse
import json
import sys
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta


def realized_vol(ticker: str, period: str = "1y") -> float:
    """Calcola RV annua da rendimenti giornalieri (dev std × √252)."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period)
    if hist.empty or len(hist) < 10:
        raise ValueError(f"Dati insufficienti per {ticker}: {len(hist)} giorni")
    daily_returns = hist["Close"].pct_change().dropna()
    rv = float(daily_returns.std() * np.sqrt(252))
    return rv


def implied_vol_atm(options_chain) -> tuple[float | None, float | None, float | None]:
    """Estrae IV ATM (call + put) dalla catena opzioni più vicina all'ATM.

    Returns:
        (atm_call_iv, atm_put_iv, atm_straddle_iv)
    """
    if options_chain is None or options_chain.empty:
        return None, None, None

    # Prende il primo expiry disponibile
    expiry_dates = options_chain.index.get_level_values(0).unique()
    if len(expiry_dates) == 0:
        return None, None, None

    # Usa la scadenza più vicina (>= 7 DTE per evitare distorsioni da gamma)
    # altrimenti la prima disponibile
    today = datetime.now()
    best_expiry = None
    for exp in expiry_dates:
        if isinstance(exp, str):
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
        else:
            exp_date = exp.to_pydatetime() if hasattr(exp, 'to_pydatetime') else exp
        dte = (exp_date - today).days
        if dte >= 7:
            best_expiry = exp
            break
    if best_expiry is None:
        best_expiry = expiry_dates[0]

    # Filtra per expiry
    chain = options_chain.loc[best_expiry]

    # Trova strike ATM (più vicino al prezzo corrente del sottostante)
    # Prendiamo il prezzo spot da yfinance
    spot = None
    calls = chain.xs("calls", level=1) if "calls" in chain.index.get_level_values(1) else chain
    puts = chain.xs("puts", level=1) if "puts" in chain.index.get_level_values(1) else chain

    if "calls" in chain.index.get_level_values(1):
        calls = chain.xs("calls", level=1)
        puts = chain.xs("puts", level=1)
    else:
        # assume già separati
        pass

    # Se non ci sono abbastanza dati, ritorna None
    if calls.empty and puts.empty:
        return None, None, None

    return calls, puts


def _best_expiry(ticker: str, min_dte: int = 30, max_dte: int = 90) -> str | None:
    """Trova la scadenza opzioni migliore: 30-90 DTE (evita la settimanale)."""
    stock = yf.Ticker(ticker)
    try:
        exps = stock.options
    except Exception:
        return None
    if not exps:
        return None

    today = datetime.now()
    best = None
    best_dte = 999
    for exp in exps:
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        dte = (exp_date - today).days
        if min_dte <= dte <= max_dte and dte < best_dte:
            best = exp
            best_dte = dte
    # Fallback: la prima scadenza >= 14 DTE
    if best is None:
        for exp in exps:
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
            dte = (exp_date - today).days
            if dte >= 14 and dte < best_dte:
                best = exp
                best_dte = dte
    # Ultimate fallback: la prima disponibile
    if best is None:
        best = exps[0]
    return best


def compute_signals(ticker: str, period: str = "1y", verbose: bool = False):
    """Calcola i 2 segnali Bali per un ticker.

    Returns:
        dict con:
        - rv: realized volatility annua
        - atm_call_iv: IV ATM call
        - atm_put_iv: IV ATM put
        - rvol_ivol_spread: RV - IV_straddle (positivo = RV > IV)
        - cvol_pvol_spread: Call_IV - Put_IV (positivo = call più care)
        - rvol_ivol_score: 0-100 (100 = massimo segnale negativo = short)
        - cvol_pvol_score: 0-100 (100 = massimo segnale positivo = long)
        - composite_bali_score: 0-100 combinato
        - direction: "bullish", "bearish", "neutral"
    """
    if verbose:
        print(f"📡 Fetching {ticker}...")

    # RV
    rv = realized_vol(ticker, period)
    if verbose:
        print(f"   RV30: {rv:.1%}")

    # Opzioni — scegli expiry 30-90 DTE
    stock = yf.Ticker(ticker)
    expiry = _best_expiry(ticker, min_dte=30, max_dte=90)
    if verbose:
        print(f"   Scadenza scelta: {expiry}")

    try:
        if expiry:
            opt = stock.option_chain(expiry)
        else:
            opt = stock.option_chain()
        calls = opt.calls
        puts = opt.puts
        close_prices = stock.history(period="5d")["Close"].dropna()
        spot = float(close_prices.iloc[-1]) if not close_prices.empty else None
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Opzioni non disponibili: {e}")
        return {
            "ticker": ticker,
            "error": f"Opzioni non disponibili: {e}",
            "rv": round(rv, 4),
            "atm_call_iv": None,
            "atm_put_iv": None,
            "rvol_ivol_spread": None,
            "cvol_pvol_spread": None,
            "rvol_ivol_score": 50,
            "cvol_pvol_score": 50,
            "composite_bali_score": 50,
            "direction": "neutral",
        }

    if calls.empty or puts.empty:
        return {
            "ticker": ticker,
            "error": "Catena opzioni vuota",
            "rv": round(rv, 4),
            "atm_call_iv": None,
            "atm_put_iv": None,
            "rvol_ivol_spread": None,
            "cvol_pvol_spread": None,
            "rvol_ivol_score": 50,
            "cvol_pvol_score": 50,
            "composite_bali_score": 50,
            "direction": "neutral",
        }

    # Trova strike ATM
    idx_call = (calls["strike"] - spot).abs().idxmin()
    idx_put = (puts["strike"] - spot).abs().idxmin()
    atm_call_iv = float(calls.loc[idx_call, "impliedVolatility"])
    atm_put_iv = float(puts.loc[idx_put, "impliedVolatility"])
    atm_straddle_iv = (atm_call_iv + atm_put_iv) / 2

    if verbose:
        print(f"   Spot: ${spot:.2f}")
        print(f"   ATM Call IV: {atm_call_iv:.1%}")
        print(f"   ATM Put IV:  {atm_put_iv:.1%}")
        print(f"   ATM Straddle IV: {atm_straddle_iv:.1%}")

    # Spreads
    rvol_ivol = rv - atm_straddle_iv   # positivo = RV > IV = volatility risk premium negativo
    cvol_pvol = atm_call_iv - atm_put_iv  # positivo = call più care = attese rialziste

    if verbose:
        print(f"\n   RVol–IVol spread: {rvol_ivol:.1%}  (RV - ATM straddle IV)")
        print(f"   CVol–PVol spread: {cvol_pvol:.1%}  (Call IV - Put IV)")

    # ── Scoring ──────────────────────────────────────────────────────
    # RVol–IVol: negativo = segnale bullish (RV < IV → vol risk premium positivo)
    #   score 0-100, 100 = massimo segnale bearish (RV >> IV)
    #   Tipico range: -0.20 a +0.20
    rvol_raw = np.clip(rvol_ivol, -0.20, 0.20)
    rvol_ivol_score = round((rvol_raw + 0.20) / 0.40 * 100, 1)

    # CVol–PVol: positivo = segnale bullish (call più care di put)
    #   score 0-100, 100 = massimo segnale bullish
    #   Tipico range: -0.05 a +0.10
    cvol_raw = np.clip(cvol_pvol, -0.05, 0.10)
    cvol_pvol_score = round((cvol_raw + 0.05) / 0.15 * 100, 1)

    # Composite Bali (media pesata: 60% RVol-IVol, 40% CVol-PVol)
    # RVol-IVol score è invertito: score alto = RV > IV = bearish
    # Quindi per il composite allineiamo: 
    #   rvol_bullish = 100 - rvol_ivol_score (alta RV rispetto a IV = bearish)
    rvol_bullish = 100 - rvol_ivol_score
    composite_bali_score = round(rvol_bullish * 0.60 + cvol_pvol_score * 0.40, 1)

    # Direction
    if composite_bali_score >= 65:
        direction = "bullish"
    elif composite_bali_score <= 35:
        direction = "bearish"
    else:
        direction = "neutral"

    if verbose:
        print(f"\n   RVol–IVol score: {rvol_ivol_score}/100 (100 = bearish)")
        print(f"   CVol–PVol score: {cvol_pvol_score}/100 (100 = bullish)")
        print(f"   Composite Bali:  {composite_bali_score}/100")
        print(f"   Direction:       {direction}")

    return {
        "ticker": ticker,
        "spot": round(spot, 2),
        "rv": round(rv, 4),
        "atm_call_iv": round(atm_call_iv, 4),
        "atm_put_iv": round(atm_put_iv, 4),
        "atm_straddle_iv": round(atm_straddle_iv, 4),
        "rvol_ivol_spread": round(rvol_ivol, 4),
        "cvol_pvol_spread": round(cvol_pvol, 4),
        "rvol_ivol_score": rvol_ivol_score,
        "cvol_pvol_score": cvol_pvol_score,
        "composite_bali_score": composite_bali_score,
        "direction": direction,
        "paper_reference": {
            "title": "Volatility Spreads and Expected Stock Returns",
            "authors": ["Turan G. Bali", "Armen Hovakimian"],
            "year": 2009,
            "doi": "10.1287/mnsc.1090.1063",
            "findings": {
                "rvol_ivol": "RVol–IVol spread: premium negativo −0.63%/−0.73% mese (volatility risk premium). Long quando RV < IV (vol premium positivo).",
                "cvol_pvol": "CVol–PVol spread: premium positivo +1.05%/+1.49% mese (jump risk). Long quando Call IV > Put IV."
            }
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Bali & Hovakimian (2009) Volatility Spread Signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Ticker symbol (e.g. AAPL, SPY)")
    parser.add_argument("--period", default="1y", help="Period for RV calc (default: 1y)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    try:
        result = compute_signals(args.ticker, period=args.period, verbose=not args.json)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n{'='*55}")
            print(f"  Bali & Hovakimian (2009) — {args.ticker}")
            print(f"{'='*55}")
            if "error" in result and result["error"]:
                print(f"  ⚠️  {result['error']}")
            print(f"\n  📊 Realized Vol (RV):        {result['rv']:.1%}")
            print(f"  📈 ATM Call IV:              {result['atm_call_iv']:.1%}" if result['atm_call_iv'] else "  📈 ATM Call IV:           N/D")
            print(f"  📉 ATM Put IV:               {result['atm_put_iv']:.1%}" if result['atm_put_iv'] else "  📉 ATM Put IV:            N/D")
            if result['rvol_ivol_spread'] is not None:
                print(f"\n  🔴 RVol–IVol spread:         {result['rvol_ivol_spread']:.1%}")
                print(f"     Score: {result['rvol_ivol_score']}/100 (100 = bearish, RV >> IV)")
            if result['cvol_pvol_spread'] is not None:
                print(f"  🟢 CVol–PVol spread:         {result['cvol_pvol_spread']:.1%}")
                print(f"     Score: {result['cvol_pvol_score']}/100 (100 = bullish, Call IV >> Put IV)")
            print(f"\n  🎯 Composite Bali:          {result['composite_bali_score']}/100")
            print(f"  🚩 Direction:               {result['direction']}")
            print(f"{'='*55}")
    except Exception as e:
        print(f"❌ Errore: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
