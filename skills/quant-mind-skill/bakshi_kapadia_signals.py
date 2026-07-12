#!/usr/bin/env python3
"""
Bakshi & Kapadia (2003) — Volatility Risk Premium Signals.

Delta-hedged gains and the negative market volatility risk premium.

Calcola:
  1. VRP magnitude stimato dal livello corrente di IV
  2. Expected delta-hedged P&L per diversi strikes (ATM/OTM/ITM)
  3. Vega exposure analysis: qual'e' lo strike ottimale per short options
  4. Fair premium adjustment: quanto del premio e' VRP (profittevole) vs rischio reale
  5. Optimal strike suggestion per vendita premium

Usage:
  python3 bakshi_kapadia_signals.py SPY
  python3 bakshi_kapadia_signals.py SPY --expiry 2026-08-21
  python3 bakshi_kapadia_signals.py SPY --json

Output: JSON con VRP analysis, expected P&L per strike, suggerimenti.
"""

import argparse
import json
import sys
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from scipy.stats import norm


# ── Bakshi & Kapadia (2003) — Parametri empirici ────────────────────
# Da Table 4, Figure 2 del paper:
#   Volatilità bassa  (8.05%)  → VRP = −3.63% del valore dell'opzione
#   Volatilità media  (12.04%) → VRP = −11.18%
#   Volatilità alta   (15.86%) → VRP = −19.60%
#   Estrapolazione:   (20%)    → ~−28%
# Fit lineare dai dati empirici del paper (Table 4, Figure 2):
#   σ=8%  → VRP=+3.63% del premio (seller incassa)
#   σ=12% → VRP=+11.18%
#   σ=16% → VRP=+19.60%
# VRP% ≈ 1.996 × σ − 12.34  (σ in %, R² ~0.99)
# Il VRP diventa positivo (profittevole per il seller) quando σ > ~6.2%
_VRP_SLOPE = 1.996
_VRP_INTERCEPT = -12.34
# Dati dal paper: ATM S&P 500 call: perdita media $0.43 su premio $5.25 ≈ 8.2%
_ATM_LOSS_PCT = 0.082


def black_scholes_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega di un'opzione (BS). Identico per call e put."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)  # vega per 1% change in vol


def black_scholes_price(S: float, K: float, T: float, r: float, sigma: float, opt_type: str = "call") -> float:
    """Prezzo BS."""
    if T <= 0 or sigma <= 0:
        return max(0, (S - K) if opt_type == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def estimate_vrp(iv: float) -> dict:
    """Stima il VRP atteso dal livello di IV corrente.

    Args:
        iv: IV annualizzata (es. 0.20 per 20%)

    Returns:
        dict con vrp_pct, vrp_descrizione, regime
    """
    iv_pct = iv * 100  # 11.8 per IV=11.8%
    # VRP% (in percentuale) = 1.996 × iv_pct − 12.34
    vrp_pct_raw = _VRP_SLOPE * iv_pct + _VRP_INTERCEPT  # es. 11.2 per iv=11.8%
    vrp_pct = max(0.0, min(35.0, vrp_pct_raw))  # clamp 0-35 (%)
    # vrp = frazione del premio che e' volatility risk premium (decimale)
    vrp_decimal = vrp_pct / 100.0

    if iv_pct < 10:
        regime = "LOW_VOL"
        desc = f"Volatilità bassa ({iv_pct:.0f}%): VRP ~{vrp_pct*100:.1f}% del premio. Vendita opzioni meno profittevole."
    elif iv_pct < 16:
        regime = "NORMAL_VOL"
        desc = f"Volatilità normale ({iv_pct:.0f}%): VRP ~{vrp_pct*100:.1f}% del premio. Vendita opzioni con VRP moderato."
    else:
        regime = "HIGH_VOL"
        desc = f"Volatilità alta ({iv_pct:.0f}%): VRP ~{vrp_pct*100:.1f}% del premio. VENDITA OPZIONI FORTEMENTE AGEVOLATA dal VRP."

    return {
        "vrp_annualized": round(vrp_decimal, 4),
        "vrp_pct_of_premium": round(vrp_pct, 1),
        "regime": regime,
        "description": desc,
    }


def expected_delta_hedged_pnl(
    S: float, K: float, T: float, r: float,
    iv: float, vrp_pct: float
) -> dict:
    """Calcola expected delta-hedged P&L per uno strike (Bakshi & Kapadia).

    Il delta-hedged portfolio: long 1 option + short delta shares.
    Sotto BS, il P&L atteso = −vega × VRP.
    Bakshi mostra che il P&L medio e' negativo e proporzionale a vega.

    Args:
        S: spot price
        K: strike
        T: time to expiry (anni)
        r: risk-free rate
        iv: implied volatility
        vrp_pct: frazione del premio attribuibile a VRP

    Returns:
        dict con P&L atteso per opzione, per $100 nozionale, e qualitativo
    """
    if T <= 0:
        return {"error": "T <= 0"}

    vega = black_scholes_vega(S, K, T, r, iv)
    premium = black_scholes_price(S, K, T, r, iv, "call")

    # Expected delta-hedged P&L (Bakshi eq. parametri):
    #   E[π] = -vega × VRP  (per 1% change in vol)
    #   In unita' monetarie: profitto venditore = vrp_pct × premium
    #   (il compratore paga il VRP, il venditore lo incassa)
    expected_seller_profit_per_option = vrp_pct * premium
    expected_buyer_loss_per_option = -expected_seller_profit_per_option

    # Per $100 nozionale
    notional = K * 100  # 100 azioni per contratto
    seller_profit_per_contract = expected_seller_profit_per_option * 100
    seller_profit_per_100_notional = (expected_seller_profit_per_option / K) * 100

    # Moneyness
    moneyness = S / K

    # Vega scaling: ATM vega e' massimo
    atm_vega = black_scholes_vega(S, S, T, r, iv)
    vega_ratio = vega / atm_vega if atm_vega > 0 else 0

    # Interpretazione qualitativa
    if vega_ratio > 0.9:
        zone = "ATM — Alta esposizione VRP"
        recommendation = "Short piu' profittevole ma con massimo rischio gamma. Preferisci strangle/iceberg."
    elif vega_ratio > 0.6:
        zone = "Near-ATM — Media esposizione VRP"
        recommendation = "Buon compromesso tra raccolta premium e rischio."
    else:
        zone = "OTM/ITM — Bassa esposizione VRP"
        recommendation = "Raccolta premium ridotta ma minore rischio di gamma/vega."

    return {
        "strike": round(K, 2),
        "moneyness": round(moneyness, 4),
        "option_premium": round(premium, 4),
        "vega": round(vega, 4),
        "vega_ratio": round(vega_ratio, 4),
        "seller_profit_per_option": round(expected_seller_profit_per_option, 4),
        "seller_profit_per_contract": round(seller_profit_per_contract, 2),
        "buyer_loss_per_option": round(expected_buyer_loss_per_option, 4),
        "vrp_pct_of_premium": round(vrp_pct * 100, 1),
        "seller_profit_per_100_notional": round(seller_profit_per_100_notional, 2),
        "zone": zone,
        "recommendation": recommendation,
    }


def _best_expiry(ticker: str, min_dte: int = 14, max_dte: int = 90) -> str | None:
    """Trova la scadenza migliore (stessa logica di bali_signals.py)."""
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
    if best is None:
        # Fallback alla prima >=7 DTE
        for exp in exps:
            exp_date = datetime.strptime(exp, "%Y-%m-%d")
            dte = (exp_date - today).days
            if dte >= 7 and dte < best_dte:
                best = exp
                best_dte = dte
    if best is None:
        best = exps[0]
    return best


def compute_bakshi_signals(ticker: str, expiry: str | None = None, verbose: bool = False):
    """Calcola i segnali Bakshi & Kapadia per un ticker.

    Returns:
        dict con:
        - vrp: stima del volatility risk premium corrente
        - strikes_analysis: expected P&L per vari strikes
        - optimal_suggestions: suggerimenti operativi
        - regime: contesto di mercato
    """
    if verbose:
        print(f"📡 Fetching {ticker}...")

    stock = yf.Ticker(ticker)
    hist = stock.history(period="1y")
    if hist.empty:
        return {"ticker": ticker, "error": "Dati insufficienti"}

    spot = float(hist["Close"].iloc[-1])
    if verbose:
        print(f"   Spot: ${spot:.2f}")

    # Opzioni
    exp_date = expiry or _best_expiry(ticker)
    if verbose:
        print(f"   Scadenza: {exp_date}")

    try:
        opt = stock.option_chain(exp_date) if exp_date else stock.option_chain()
        calls = opt.calls
        puts = opt.puts
    except Exception as e:
        return {"ticker": ticker, "error": f"Opzioni non disponibili: {e}"}

    if calls.empty or puts.empty:
        return {"ticker": ticker, "error": "Catena opzioni vuota"}

    # IV ATM
    idx_call = (calls["strike"] - spot).abs().idxmin()
    idx_put = (puts["strike"] - spot).abs().idxmin()
    atm_iv = float(calls.loc[idx_call, "impliedVolatility"])
    atm_put_iv = float(puts.loc[idx_put, "impliedVolatility"])
    avg_iv = (atm_iv + atm_put_iv) / 2

    if verbose:
        print(f"   ATM Call IV: {atm_iv:.1%}")
        print(f"   ATM Put IV:  {atm_put_iv:.1%}")

    # DTE
    if exp_date:
        exp_dt = datetime.strptime(exp_date, "%Y-%m-%d")
        dte = max((exp_dt - datetime.now()).days, 1)
    else:
        dte = 30
    T = dte / 365.0
    r = 0.05  # risk-free rate approssimato

    # VRP stima
    vrp = estimate_vrp(avg_iv)
    if verbose:
        print(f"\n   VRP stimato: {vrp['vrp_pct_of_premium']:.1f}% del premio ({vrp['regime']})")
        print(f"   {vrp['description']}")

    # Analisi per strike
    strikes_analysis = []
    # Prendi strikes attorno all'ATM
    all_strikes = sorted(set(calls["strike"].tolist()))
    atm_strike_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - spot))

    # Seleziona 9 strikes: 4 OTM put, ATM, 4 OTM call
    half = 4
    start = max(0, atm_strike_idx - half)
    end = min(len(all_strikes), atm_strike_idx + half + 1)
    selected_strikes = all_strikes[start:end]

    for K in selected_strikes:
        result = expected_delta_hedged_pnl(spot, K, T, r, avg_iv, vrp["vrp_annualized"])
        if "error" not in result:
            strikes_analysis.append(result)

    if verbose:
        print(f"\n   Analisi per strike ({len(strikes_analysis)} strikes):")
        for sa in strikes_analysis:
            print(f"     K=${sa['strike']:<8} moneyness={sa['moneyness']:.2f}  "
                  f"premio=${sa['option_premium']:<8.2f}  "
                  f"profitto_seller=${sa['seller_profit_per_contract']:<8.2f}  "
                  f"{sa['zone'][:25]}")

    # Suggerimenti operativi (dal paper Bakshi & Kapadia)
    best_strike_for_short = max(strikes_analysis, key=lambda x: x["seller_profit_per_option"]) if strikes_analysis else None
    best_strike_for_buy = min(strikes_analysis, key=lambda x: x["seller_profit_per_option"]) if strikes_analysis else None

    suggestions = {
        "vrp_harvesting": {
            "title": "VRP Harvesting — Short Options",
            "rationale": "Bakshi & Kapadia dimostrano che il VRP e' negativo: vendere opzioni e' strutturalmente profittevole.",
            "optimal_strike": best_strike_for_short["strike"] if best_strike_for_short else None,
            "expected_monthly_vrp": round(vrp["vrp_pct_of_premium"] / 12, 2) if vrp["vrp_pct_of_premium"] else 0,
            "bakshi_empirical": f"A volatilita' corrente il VRP e' ~{vrp['vrp_pct_of_premium']:.1f}% del premio pagato. "
                                f"Bakshi mostra: ATM calls perdono $0.43 su $5.25 (~8.2%), "
                                f"con 68% delle osservazioni negative.",
        },
        "optimal_strike_selection": {
            "title": "Selezione Strike Ottimale",
            "rationale": "La perdita e' massima per ATM (vega massimo) e diminuisce per OTM/ITM.",
            "recommendation": "Per massimizzare raccolta VRP: vendita ATM (maggior premio assoluto). "
                              "Per minimizzare rischio: vendita OTM 15-20% (minor vega). "
                              "Per compromesso: strangle 1SD OTM.",
            "vega_profile": "ATM = max vega = max esposizione VRP = max profitto atteso = max rischio",
        },
        "timing_vol_regime": {
            "title": "Timing — VRP e Regime di Volatilita'",
            "rationale": "Bakshi: a vol bassa (8%) VRP = −3.6%, a vol alta (16%) VRP = −19.6%.",
            "current_regime": vrp["regime"],
            "recommendation": "VENDERE opzioni quando l'IV e' alta (il VRP e' piu' ricco). "
                              "COMPRARE opzioni solo quando l'IV e' storicamente bassa.",
        },
        "dispersion_trading": {
            "title": "Dispersion Trading",
            "rationale": "Bakshi mostra VRP negativo su index options. "
                         "Bali mostra VRP varia cross-sectionalmente tra stock.",
            "recommendation": "Vendi index options (SPY) per catturare il VRP dell'indice. "
                              "Compra single-stock options per hedging del jump risk. "
                              "La dispersione e' strutturalmente positiva quando index IV > stock IV medio.",
        },
        "variance_swap_analogy": {
            "title": "Variance Swap Analogy",
            "rationale": "Il delta-hedged portfolio replica un variance swap: "
                         "P&L = somma( (dS/S)^2 ) − sigma_BS^2 × T. "
                         "Se la varianza realizzata < IV, il portfolio perde → VRP negativo.",
            "implication": "Short variance swaps / short straddles sono strutturalmente profittevoli, "
                           "MA con jump risk tail (1987 crash, 2008, 2020). "
                           "Usa spread (non naked) per gestire il tail risk.",
        },
    }

    return {
        "ticker": ticker,
        "spot": round(spot, 2),
        "expiry": exp_date,
        "dte": dte,
        "atm_iv": round(avg_iv, 4),
        "atm_call_iv": round(atm_iv, 4),
        "atm_put_iv": round(atm_put_iv, 4),
        "vrp": vrp,
        "strikes_analysis": strikes_analysis,
        "suggestions": suggestions,
        "paper_reference": {
            "title": "Delta-Hedged Gains and the Negative Market Volatility Risk Premium",
            "authors": ["Gurdip Bakshi", "Nikunj Kapadia"],
            "year": 2003,
            "journal": "The Review of Financial Studies",
            "doi": "10.1093/rfs/hhg002",
            "key_empirical": {
                "atm_loss": "ATM S&P 500 call options lose ~$0.43 per option (~8.2% of premium)",
                "negativity_rate": "68% of delta-hedged observations are negative",
                "vol_dependence": "At 8% vol: −3.6% loss. At 16% vol: −19.6% loss (of option value)",
                "jump_robustness": "VRP remains significant after controlling for RN skew and kurtosis",
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Bakshi & Kapadia (2003) — Volatility Risk Premium Signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("ticker", help="Ticker symbol")
    parser.add_argument("--expiry", default=None, help="Expiry date (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    try:
        result = compute_bakshi_signals(args.ticker, expiry=args.expiry, verbose=not args.json)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            error = result.get("error")
            if error:
                print(f"❌ {error}")
                sys.exit(1)

            vrp = result["vrp"]
            sug = result["suggestions"]

            print(f"\n{'='*60}")
            print(f"  Bakshi & Kapadia (2003) — VRP Analysis: {args.ticker}")
            print(f"{'='*60}")
            print(f"  Spot: ${result['spot']:.2f} | Expiry: {result['expiry']} | {result['dte']} DTE")
            print(f"  ATM IV: {result['atm_iv']:.1%} (Call: {result['atm_call_iv']:.1%} Put: {result['atm_put_iv']:.1%})")
            print(f"\n  📊 Volatility Risk Premium:")
            print(f"     VRP: {vrp['vrp_pct_of_premium']:.1f}% del premio")
            print(f"     Regime: {vrp['regime']}")
            print(f"     {vrp['description']}")
            print(f"\n  🎯 Optimal Strike per VRP Harvesting:")
            print(f"     ATM strike: ${sug['vrp_harvesting']['optimal_strike']:.0f}" if sug['vrp_harvesting']['optimal_strike'] else "")
            print(f"     Expected VRP mensile: ~{sug['vrp_harvesting']['expected_monthly_vrp']:.2f}%")
            print(f"\n  📋 Suggerimenti operativi:")
            print(f"  1. {sug['vrp_harvesting']['title']}: {sug['vrp_harvesting']['rationale'][:100]}...")
            print(f"  2. {sug['optimal_strike_selection']['title']}: {sug['optimal_strike_selection']['recommendation'][:100]}...")
            print(f"  3. {sug['timing_vol_regime']['title']}: {sug['timing_vol_regime']['recommendation'][:120]}...")
            print(f"\n  📈 Strike Analysis (profitto seller per contratto):")
            for sa in result["strikes_analysis"][:5]:
                print(f"     ${sa['strike']:<8} moneyness={sa['moneyness']:.2f}  "
                      f"profitto_seller=${sa['seller_profit_per_contract']:<8.2f}  "
                      f"vrp={sa['vrp_pct_of_premium']:<5.1f}%  {sa['zone'][:20]}")
            print(f"\n     ATM strike: ~${result['spot']:.0f} | DTE: {result['dte']}")
            print(f"{'='*60}")
    except Exception as e:
        print(f"❌ Errore: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
