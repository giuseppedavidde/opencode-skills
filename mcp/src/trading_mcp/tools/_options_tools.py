"""MCP tool registration: options tools.

Options chain, multi-leg position analysis, GEX, Bali & Hovakimian (2009)
volatility spreads, Bakshi & Kapadia (2003) VRP and the strategy suggestion.
Every tool reads market data through the centralized DataProvider.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from fastmcp import FastMCP

from trading_mcp.analysis.gex import analyze_gex
from trading_mcp.analysis.options_calc import analyze_options_position
from trading_mcp.data import market_calendar as mcal
from trading_mcp.data.options_chain import fetch_options_chain as _fetch_options_chain
from trading_mcp.data.prices import returns as total_returns
from trading_mcp.data.provider import data_provider
from trading_mcp.data.result_cache import result_cache
from trading_mcp.data.risk_free import get_risk_free_rate
from trading_mcp.responses import (
    typed,
    VRP_CALIBRATION_SOURCE,
    AnalyzeOptionsResponse,
    BakshiResult,
    BakshiStrikeAnalysis,
    BakshiVRP,
    BaliResult,
    GexAnalysisResponse,
    OptionsChainResponse,
    StrategySuggestionResponse,
    error_payload,
)
from trading_mcp.timeutil import utc_iso

logger = logging.getLogger(__name__)

# Bakshi & Kapadia (2003) — empirical params from Table 4, Figure 2.
# WARNING: These are CALIBRATED on S&P 500 only.
_VRP_SLOPE = 1.996
_VRP_INTERCEPT = -12.34
_VRP_CALIBRATION_SOURCE = VRP_CALIBRATION_SOURCE


# ── Helper functions ─────────────────────────────────────────────────

def _best_expiry_from_provider(ticker: str, min_dte: int = 30, max_dte: int = 90) -> str | None:
    """Trova la scadenza opzioni migliore usando DataProvider."""
    expirations = data_provider.get_options_expirations(ticker)
    if not expirations:
        return None

    today = mcal.exchange_today(ticker)
    best: str | None = None
    best_dte = 999

    for exp in expirations:
        dte = (date.fromisoformat(exp) - today).days
        if min_dte <= dte <= max_dte and dte < best_dte:
            best = exp
            best_dte = dte

    # Fallback: >= 14 DTE
    if best is None:
        best_dte = 999
        for exp in expirations:
            dte = (date.fromisoformat(exp) - today).days
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

    today = mcal.exchange_today(ticker)
    best: str | None = None
    best_dte = 999

    for exp in expirations:
        dte = (date.fromisoformat(exp) - today).days
        if min_dte <= dte <= max_dte and dte < best_dte:
            best = exp
            best_dte = dte

    # Fallback: >= 7 DTE
    if best is None:
        best_dte = 999
        for exp in expirations:
            dte = (date.fromisoformat(exp) - today).days
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
    daily_returns = total_returns(hist)
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



def register_options_tools(mcp_server: FastMCP, _skills_dir: str) -> None:
    """Register the options tools with the MCP server."""

    @mcp_server.tool()
    @typed(OptionsChainResponse)
    def fetch_options_chain(
        ticker: str, expiry: str, strike_window: int | None = 10
    ) -> OptionsChainResponse:
        """Fetch options chain with Greeks and IV metrics.

        Args:
            ticker: Stock ticker symbol.
            expiry: Target expiry date (YYYY-MM-DD). REQUIRED — the tool rejects calls
                    without it. If the exact date is unavailable, snaps to the nearest
                    available expiry.
            strike_window: Number of strikes to keep around ATM on each side
                    (default 10 → ±10 strikes, ~70-90% smaller payload). Pass None
                    or -1 to return the full chain.

        Returns:
            Dictionary with calls/puts lists including Greeks, and IV metrics.
        """
        if not expiry or str(expiry).lower() in ("null", "none", ""):
            return error_payload(
                "expiry is REQUIRED. Pass expiry='YYYY-MM-DD'.",
                data_source="options",
                ticker=ticker,
            )

        window = strike_window if strike_window is None or strike_window > 0 else None
        cache_params: dict[str, Any] = {"expiry": str(expiry), "strike_window": window}
        cached = result_cache.get("fetch_options_chain", ticker, cache_params)
        if cached is not None:
            return cached

        result = _fetch_options_chain(ticker, expiry, strike_window=window)
        result_cache.set("fetch_options_chain", ticker, cache_params, result)
        return result

    @mcp_server.tool()
    @typed(AnalyzeOptionsResponse)
    def analyze_options(
        ticker: str,
        legs: list[dict[str, Any]],
        expiry: str,
    ) -> AnalyzeOptionsResponse:
        """Analyze a multi-leg options position.

        Computes Greeks per leg and total, payoff scenarios at 100 price levels,
        break-even points, probabilities (ITM/OTM, profit), and strategy classification
        using the Options Playbook framework.

        Supports multi-expiry positions (calendar spreads, diagonal spreads): each
        leg dict may carry an optional ``expiry`` key (YYYY-MM-DD). Per-leg expiry
        takes precedence over the global ``expiry`` parameter.

        Args:
            ticker: Stock ticker symbol.
            legs: List of leg dicts with type, strike, qty, entry_premium.
                  Each leg can optionally include "expiry" (YYYY-MM-DD) for
                  multi-expiry positions (calendar spreads, diagonals).
            expiry: Global target expiry (YYYY-MM-DD). Used for legs without
                    per-leg expiry. REQUIRED — the tool rejects calls without it.
        """
        if not expiry or str(expiry).lower() in ("null", "none", ""):
            return error_payload(
                "expiry is REQUIRED. Pass expiry='YYYY-MM-DD'.",
                data_source="options",
                ticker=ticker,
            )

        cache_params: dict[str, Any] = {"legs": legs, "expiry": str(expiry)}
        cached = result_cache.get("analyze_options", ticker, cache_params)
        if cached is not None:
            return cached

        result = analyze_options_position(ticker, legs, expiry)
        result_cache.set("analyze_options", ticker, cache_params, result)
        return result

    @mcp_server.tool()
    @typed(GexAnalysisResponse)
    def gex_analysis(
        ticker: str,
        expiry: str | None = None,
        max_expiries: int = 12,
        top_n: int = 15,
        max_dte: int = 120,
    ) -> GexAnalysisResponse:
        """Compute Gamma Exposure (GEX) for a ticker's option chain.

        Calculates dealer gamma exposure per strike (call GEX positive,
        put GEX negative; GEX = gamma * OI * 100 * S^2 * 0.01, i.e. dollars
        per 1% underlying move), the total net GEX, the strike-by-strike
        profile, the zero-gamma / Gamma Flip level, the Call Wall and Put
        Wall, and the prevailing gamma regime (long-gamma = mean-reverting /
        pinning, short-gamma = volatility-amplifying).

        Args:
            ticker: Stock ticker symbol (e.g. 'SPY').
            expiry: Optional 'YYYY-MM-DD' expiry. When None, chains up to
                ``max_expiries`` listed expirations are aggregated.
            max_expiries: Maximum number of expirations aggregated (default 12).
            top_n: Number of strikes kept in the returned profile (default 15).
            max_dte: Maximum days to expiry; 0DTE and longer-dated expirations
                are excluded (default 120, matching the reference).

        Returns:
            GexResult payload with net GEX, gamma flip, walls, regime and
            the top-|GEX| strikes.
        """
        cache_params: dict[str, Any] = {
            "expiry": expiry,
            "max_expiries": max_expiries,
            "top_n": top_n,
            "max_dte": max_dte,
        }
        cached = result_cache.get("gex_analysis", ticker, cache_params)
        if cached is not None:
            return cached

        result = analyze_gex(
            ticker,
            expiry=expiry,
            max_expiries=max_expiries,
            top_n=top_n,
            max_dte=max_dte,
        )
        result_cache.set("gex_analysis", ticker, cache_params, result)
        return result


    # ── 1. Bali & Hovakimian (2009) Volatility Spread Signals ────

    @mcp_server.tool()
    @typed(BaliResult)
    def bali_signals(ticker: str, period: str = "1y") -> BaliResult:
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
                rv=None,
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()

        # 2. Spot from the quote layer (data time in spot_as_of).
        quote = data_provider.get_quote(ticker)
        if quote.price is None:
            return BaliResult(
                ticker=ticker,
                available=False,
                error_is_blocking=True,
                error=f"Spot non disponibile: {quote.error or 'nessuna quotazione'}",
                rv=round(rv, 4),
                available_bars=avail_bars,
                required_bars=_MIN_BALI_BARS,
                direction="unavailable",
            ).model_dump()
        spot = float(quote.price)
        spot_stamp = {"spot_as_of": quote.as_of, "spot_source": quote.source,
                      "spot_age_s": quote.age_s, "spot_freshness": quote.freshness}

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
                    spot=round(spot, 2), **spot_stamp,
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
                    spot=round(spot, 2), **spot_stamp,
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
                spot=round(spot, 2), **spot_stamp,
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
                spot=round(spot, 2), **spot_stamp,
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
            **spot_stamp,
            available_bars=avail_bars,
            required_bars=_MIN_BALI_BARS,
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


    # ── 3. Bakshi & Kapadia (2003) VRP Analysis ──────────────────

    @mcp_server.tool()
    @typed(BakshiResult)
    def bakshi_signals(
        ticker: str, expiry: str | None = None
    ) -> BakshiResult:
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

        # Spot from the quote layer; the bars above hold complete sessions only.
        quote = data_provider.get_quote(ticker)
        if quote.price is None:
            return BakshiResult(
                ticker=ticker,
                error=f"Spot non disponibile: {quote.error or 'nessuna quotazione'}",
                available_bars=avail_bars,
                required_bars=_MIN_BAKSHI_BARS,
            ).model_dump()
        spot = float(quote.price)
        spot_stamp = {"spot_as_of": quote.as_of, "spot_source": quote.source,
                      "spot_age_s": quote.age_s, "spot_freshness": quote.freshness}

        # 2. Scadenza opzioni da DataProvider
        exp_date = expiry or _best_expiry_bakshi(ticker)

        # 3. Opzioni chain via DataProvider
        try:
            if not exp_date:
                return BakshiResult(
                    ticker=ticker, spot=round(spot, 2), **spot_stamp,
                    error="Nessuna scadenza opzioni disponibile",
                ).model_dump()
            opt = data_provider.get_options_chain(ticker, exp_date)
            if opt is None:
                return BakshiResult(
                    ticker=ticker, spot=round(spot, 2), **spot_stamp,
                    error="Catena opzioni non disponibile",
                ).model_dump()
            calls = opt.calls
            puts = opt.puts
        except Exception as e:
            return BakshiResult(
                ticker=ticker, spot=round(spot, 2), **spot_stamp, error=f"Opzioni non disponibili: {e}"
            ).model_dump()

        if calls.empty or puts.empty:
            return BakshiResult(
                ticker=ticker, spot=round(spot, 2), **spot_stamp, error="Catena opzioni vuota"
            ).model_dump()

        # 4. IV ATM
        idx_call = int((calls["strike"] - spot).abs().idxmin())
        idx_put = int((puts["strike"] - spot).abs().idxmin())
        atm_iv = float(calls.loc[idx_call, "impliedVolatility"])
        atm_put_iv = float(puts.loc[idx_put, "impliedVolatility"])
        avg_iv = (atm_iv + atm_put_iv) / 2

        # 5. DTE
        # Calendar days in exchange time (fractional expiry: market_calendar.time_to_expiry).
        dte = max((date.fromisoformat(exp_date) - mcal.exchange_today(ticker)).days, 1)
        T_years = dte / 365.0
        rate_snapshot = get_risk_free_rate()
        r = rate_snapshot.value

        # 6. VRP empirico del titolo: IV ATM contro RV a 30 giorni.
        #    La regressione Bakshi (1988-1995, S&P 500) resta un riferimento
        #    secondario, non il valore primario del titolo.
        ret_30 = total_returns(hist).tail(30)
        rv_30d = float(ret_30.std() * np.sqrt(252)) if len(ret_30) >= 10 else float("nan")
        iv_pct_val = avg_iv * 100
        vrp_ref_pct = max(0.0, min(35.0, _VRP_SLOPE * iv_pct_val + _VRP_INTERCEPT))
        if rv_30d == rv_30d and rv_30d > 0:
            vrp_pct = max(-35.0, min(35.0, (avg_iv - rv_30d) / max(avg_iv, 1e-6) * 100.0))
            vrp_source = "ticker: (IV_ATM - RV_30d) / IV_ATM"
        else:
            rv_30d = None
            vrp_pct = vrp_ref_pct
            vrp_source = "fallback: Bakshi S&P 500 regression"
        vrp_decimal = vrp_pct / 100.0

        if iv_pct_val < 10:
            regime = "LOW_VOL"
        elif iv_pct_val < 16:
            regime = "NORMAL_VOL"
        else:
            regime = "HIGH_VOL"

        if vrp_pct > 0:
            vrp_sentence = (
                f"VRP positivo ~{vrp_pct:.1f}% del premio: la vendita di opzioni "
                f"raccoglie un premio superiore alla volatilita' realizzata."
            )
        else:
            vrp_sentence = (
                f"VRP non positivo ({vrp_pct:.1f}%): l'IV non supera la RV, "
                f"quindi il premio e' scarso e comprare volatilita' e' relativamente "
                f"conveniente."
            )
        desc = (
            f"Volatilita' {'bassa' if regime == 'LOW_VOL' else 'normale' if regime == 'NORMAL_VOL' else 'alta'} "
            f"({iv_pct_val:.0f}%). {vrp_sentence} Fonte VRP: {vrp_source}."
        )

        vrp_model = BakshiVRP(
            vrp_annualized=round(vrp_decimal, 4),
            vrp_pct_of_premium=round(vrp_pct, 1),
            regime=regime,
            description=desc,
            vrp_source=vrp_source,
            rv_30d=round(rv_30d, 4) if rv_30d is not None else None,
            vrp_reference_pct=round(vrp_ref_pct, 1),
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
            # Per-strike IV from the chain: the smile must price each strike,
            # not a single flat ATM sigma across the whole wing.
            row_iv = calls.loc[calls["strike"] == K, "impliedVolatility"]
            iv_strike = avg_iv
            if not row_iv.empty:
                candidate = float(row_iv.iloc[0])
                if candidate > 0.0:
                    iv_strike = candidate
            vega = _black_scholes_vega(spot, K, T_years, r, iv_strike)
            premium = _black_scholes_price(spot, K, T_years, r, iv_strike, "call")
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
            **spot_stamp,
            available_bars=avail_bars,
            required_bars=_MIN_BAKSHI_BARS,
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

    @mcp_server.tool()
    @typed(StrategySuggestionResponse)
    def suggest_options_strategy(
        ticker: str,
        composite_score: float,
        verdict: str,
        iv_rank: float | None = None,
        risk_tolerance: str = "medium",
    ) -> StrategySuggestionResponse:
        """Suggest an options strategy based on stock analysis verdict.

        Combines the verdict from analyze_stock with IV regime assessment
        to recommend a specific options strategy from the Options Playbook.

        Args:
            ticker: Stock ticker symbol.
            composite_score: Score from analyze_stock (0-100).
            verdict: Verdict from analyze_stock ('Long-Term Investment',
                     'Short-Term Speculation (Bullish)', 'Avoid / Wait').
            iv_rank: IV rank (0-100). Auto-fetched if None.
            risk_tolerance: 'low', 'medium', or 'high'.

        Returns:
            StrategySuggestion with strategy name, structure, and rationale.
        """
        cache_params: dict[str, Any] = {
            "composite_score": composite_score,
            "verdict": verdict,
            "iv_rank": iv_rank,
            "risk_tolerance": risk_tolerance,
        }
        cached = result_cache.get("suggest_options_strategy", ticker, cache_params)
        if cached is not None:
            return cached

        if verdict == "Avoid / Wait":
            return {
                "ticker": ticker,
                "strategy_name": "No Entry",
                "strategy_description": "Verdict is Avoid/Wait. No options strategy recommended.",
                "rationale": ["Composite score below threshold for entry."],
                "warnings": ["Wait for better setup or higher score."],
            }

        direction = "bullish"
        if composite_score < 60:
            direction = "neutral"

        if iv_rank is None:
            try:
                from trading_mcp.data.options_chain import fetch_options_chain
                chain = fetch_options_chain(ticker)
                # iv_rank is None unless computable from a historical IV series;
                # never substitute a misleading in-chain range position here.
                iv_rank = chain.get("iv_metrics", {}).get("iv_rank")
            except Exception:
                iv_rank = None

        if iv_rank is None:
            iv_regime = "unknown"
        elif iv_rank > 70:
            iv_regime = "high"
        elif iv_rank < 30:
            iv_regime = "low"
        else:
            iv_regime = "normal"

        strategy_name = "Bull Call Spread"
        strategy_desc = "Buy ATM Call + Sell OTM Call. Defined risk, moderate bullish."
        legs = []

        if composite_score >= 75 and iv_regime in ("high", "normal") and risk_tolerance in ("medium", "high"):
            strategy_name = "Synthetic Long 2:1"
            strategy_desc = "Sell 2x OTM Put + Buy 1x ATM Call. Aggressive bullish, uses rich put premiums."
        elif composite_score >= 70 and direction == "bullish":
            strategy_name = "LEAPS Call"
            strategy_desc = "Buy deep ITM Call with DTE 300+. Low time decay, high delta."
        elif direction == "bullish":
            strategy_name = "Bull Call Spread"
            strategy_desc = "Buy ATM Call + Sell OTM Call. Defined risk, moderate bullish."
        elif direction == "neutral" and iv_regime == "high":
            strategy_name = "Iron Condor"
            strategy_desc = "Sell OTM Put spread + Call spread. Range-bound with high IV."
        elif direction == "neutral":
            strategy_name = "Cash-Secured Put"
            strategy_desc = "Sell ATM/OTM Put. Collect premium, ready to own stock at discount."

        rationale = [
            f"Score {composite_score} with verdict '{verdict}' → {direction} outlook",
            (
                f"IV rank {iv_rank:.0f} ({iv_regime})"
                if iv_rank is not None
                else f"IV regime: {iv_regime} (historical IV rank unavailable)"
            ),
            f"Risk tolerance: {risk_tolerance}",
        ]

        suggest_result = {
            "ticker": ticker,
            "timestamp": utc_iso(),
            "strategy_name": strategy_name,
            "strategy_description": strategy_desc,
            "legs": legs,
            "rationale": rationale,
            "max_profit": "See Greeks in analyze_options for detailed payoff",
            "max_loss": None,
            "breakeven": None,
            "risk_reward_ratio": None,
            "warnings": [
                "Run analyze_options with actual strikes for precise Greeks and payoff.",
                "Verify IV regime and DTE before entry.",
            ],
        }
        result_cache.set("suggest_options_strategy", ticker, cache_params, suggest_result)
        return suggest_result
