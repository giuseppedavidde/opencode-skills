#!/usr/bin/env python3
"""
Moskowitz, Ooi & Pedersen (2012) — Time Series Momentum Signal.

Calcola il TS-MOM signal per un ticker:
  sign(return_{t-12:t-1})  con volatility scaling a target 40% annuo.

Usage:
  python3 tsmom_signals.py AAPL
  python3 tsmom_signals.py SPY --lookback 12 --holding 1
  python3 tsmom_signals.py SPY --json

Output: JSON con score TS-MOM 0-100, direzione, Sharpe stimato.
"""

import argparse
import json
import sys
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta


def compute_tsmom(ticker: str, lookback_months: int = 12,
                  skip_last_days: int = 21, verbose: bool = False):
    """Calcola Time Series Momentum score per un ticker.

    Segue la metodologia MOP (2012):
      - Rendimento cumulato degli ultimi 'lookback_months' mesi
        (escludendo gli ultimi 'skip_last_days' giorni = ~1 mese)
      - Signal = +1 se rendimento > 0, -1 se < 0
      - Volatility scaling: posizione = signal × (target_vol / σ_EWMA)
      - Score 0-100 convertito

    Args:
        ticker: Ticker symbol
        lookback_months: mesi di lookback (default 12, range 3-12)
        skip_last_days: giorni da saltare (default 21 ≈ 1 mese)
        verbose: output verboso

    Returns:
        dict con score, segnale, rendimenti, vol
    """
    if verbose:
        print(f"📡 TS-MOM: {ticker} (lookback={lookback_months}m, skip={skip_last_days}d)")

    # Scarica dati (abbastanza per lookback + margine)
    period_needed = f"{lookback_months + 3}mo"
    stock = yf.Ticker(ticker)
    hist = stock.history(period=period_needed)
    if hist.empty or len(hist) < 60:
        return {"ticker": ticker, "error": f"Dati insufficienti: {len(hist)} giorni"}

    close = hist["Close"]
    # Calcola rendimenti giornalieri
    returns = close.pct_change().dropna()

    # Lookback period: escludi ultimi skip_last_days giorni
    total_days = len(returns)
    start_idx = max(0, total_days - lookback_months * 21 - skip_last_days)
    end_idx = max(0, total_days - skip_last_days)

    if start_idx >= end_idx:
        return {"ticker": ticker, "error": f"Dati insufficienti dopo skip: start={start_idx}, end={end_idx}"}

    lookback_returns = returns.iloc[start_idx:end_idx]
    recent_returns = returns.iloc[-min(126, len(returns)):]  # ~6 mesi per vol

    if len(lookback_returns) < 20:
        return {"ticker": ticker, "error": f"Lookback troppo corto: {len(lookback_returns)} giorni"}

    # —— TS-MOM signal (MOP 2012) ——
    # Cumulative return over lookback period
    cum_return = (1 + lookback_returns).prod() - 1
    signal = 1 if cum_return > 0 else -1

    # —— Volatility scaling (MOP 2012: target 40% annuo, EWMA vol) ——
    # EWMA volatilità con center-of-mass = 60 giorni
    span = 60
    ewma_vol = recent_returns.ewm(span=span).std().iloc[-1] * np.sqrt(252)
    target_vol = 0.40
    vol_scaling = target_vol / max(ewma_vol, 0.05)  # floor 5%
    position_size = signal * vol_scaling

    # —— Score 0-100 ——
    # Magnitudine del rendimento cumulato (quanto e' forte il momentum)
    # range tipico: -0.5 a +0.5
    raw_strength = np.clip(cum_return, -0.50, 0.50)
    mom_score = round((raw_strength + 0.50) / 1.0 * 100, 1)

    # Direction
    if mom_score >= 65:
        direction = "bullish"
    elif mom_score <= 35:
        direction = "bearish"
    else:
        direction = "neutral"

    # —— Statistiche aggiuntive ——
    # Sharpe ratio del TS-MOM per questo ticker (solo lookback)
    sharpe_lookback = lookback_returns.mean() / max(lookback_returns.std(), 1e-6) * np.sqrt(252)

    # Percentuale di mesi positivi nel lookback
    monthly_rets = close.resample('ME').last().pct_change().dropna()
    monthly_lookback = monthly_rets.iloc[-lookback_months:]
    pct_positive = (monthly_lookback > 0).mean() * 100 if len(monthly_lookback) > 0 else 50

    if verbose:
        print(f"   Prezzo: ${close.iloc[-1]:.2f}")
        print(f"   Lookback period: {len(lookback_returns)} giorni")
        print(f"   Cum return ({lookback_months}m): {cum_return:.1%}")
        print(f"   Signal: {'+1 LONG' if signal > 0 else '-1 SHORT'}")
        print(f"   EWMA Vol: {ewma_vol:.1%}")
        print(f"   Vol scaling: {vol_scaling:.2f}x (target {target_vol:.0%})")
        print(f"   Position size: {position_size:.2f}")
        print(f"   TS-MOM Score: {mom_score}/100 ({direction})")

    return {
        "ticker": ticker,
        "price": round(float(close.iloc[-1]), 2),
        "lookback_months": lookback_months,
        "cum_return_lookback": round(float(cum_return), 4),
        "signal": signal,
        "ewma_vol": round(float(ewma_vol), 4),
        "vol_scaling": round(float(vol_scaling), 4),
        "position_size": round(float(position_size), 4),
        "mom_score": mom_score,
        "direction": direction,
        "pct_positive_months": round(float(pct_positive), 1),
        "sharpe_lookback": round(float(sharpe_lookback), 4),
        "target_vol": target_vol,
        "paper_reference": {
            "title": "Time series momentum",
            "authors": ["Tobias J. Moskowitz", "Yao Hua Ooi", "Lasse Heje Pedersen"],
            "year": 2012,
            "journal": "Journal of Financial Economics",
            "signal_formula": "sign(return_{t-12:t-1}) con volatility scaling a target 40%",
            "key_finding": "Sharpe ratio > 1.0 su portafoglio diversificato cross-asset, universale in 58 futures su 4 asset class",
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Moskowitz, Ooi & Pedersen (2012) — Time Series Momentum Signal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--lookback", type=int, default=12, help="Lookback months (default: 12)")
    parser.add_argument("--skip-days", type=int, default=21, help="Days to skip (default: 21)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    try:
        result = compute_tsmom(args.ticker, lookback_months=args.lookback,
                               skip_last_days=args.skip_days, verbose=not args.json)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if "error" in result:
                print(f"❌ {result['error']}")
                sys.exit(1)
            print(f"\n{'='*55}")
            print(f"  Time Series Momentum — {args.ticker}")
            print(f"{'='*55}")
            print(f"  Prezzo: ${result['price']:.2f}")
            print(f"  Lookback: {result['lookback_months']}m (skip {args.skip_days}d)")
            print(f"  Cum return: {result['cum_return_lookback']:.1%}")
            print(f"  Signal: {'🟢 LONG' if result['signal'] > 0 else '🔴 SHORT'}")
            print(f"  EWMA Vol: {result['ewma_vol']:.1%}")
            print(f"  Position size: {result['position_size']:.2f}x")
            print(f"  TS-MOM Score: {result['mom_score']}/100 ({result['direction']})")
            print(f"  % mesi positivi: {result['pct_positive_months']:.0f}%")
            print(f"  Sharpe (lookback): {result['sharpe_lookback']:.2f}")
            print(f"{'='*55}")
    except Exception as e:
        print(f"❌ Errore: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
