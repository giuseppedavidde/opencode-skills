"""Fetcher per dati opzioni.

Usa il trading MCP per dati live e yfinance per storico limitato.
Durante l'inferenza live, ``fetch_options_chain_mcp`` puo' interrogare il
MCP trading (tool ``fetch_options_chain``); per il training storico usiamo
approssimazioni derivate dalla sola serie OHLCV, dato che yfinance non fornisce
storico opzioni congruente con la lunghezza di OHLCV.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger("data.options_fetcher")

# Cache per non richiamare MCP / yfinance a ogni barra
_options_cache: dict[str, dict] = {}
_cache_timestamp: Optional[datetime] = None

# Premium tipico IV/RV empirico (~20%) + floor di volatilita'
_IV_PREMIUM_MULT: float = 1.2
_IV_PREMIUM_ADD: float = 0.05


def fetch_options_chain_mcp(ticker: str, expiry: Optional[str] = None) -> dict:
    """Fetcha opzioni live dal trading MCP.

    Usa il tool ``fetch_options_chain`` del MCP trading. Se ``expiry`` e'
    ``None`` viene scelta la scadenza piu' vicina ai 30-60 DTE.

    Returns
    -------
    dict
        Keys: ``calls``, ``puts``, ``underlying_price``, ``iv``, ``greeks``.
        Con fallback a yfinance in caso di MCP non disponibile.
    """
    # TODO: chiamata al MCP trading. Per ora stub con fallback yfinance:
    # la signature resta stabile cosi' l'integrazione con il live e' drop-in.
    logger.warning("MCP fetch non implementato, uso yfinance fallback per %s", ticker)
    return _fetch_options_yfinance(ticker, expiry)


def _fetch_options_yfinance(ticker: str, expiry: Optional[str] = None) -> dict:
    """Fallback yfinance per dati opzioni correnti.

    yfinance NON fornisce storico opzioni, solo snapshot corrente; la funzione
    calcola comunque le metriche chiave (IV ATM, PCR, VRP approssimato).

    Returns
    -------
    dict
        Dati opzioni correnti (vuoto in caso di errore / ticker senza opzioni).
    """
    import yfinance as yf

    tk = yf.Ticker(ticker)

    try:
        expirations = tk.options
        if not expirations:
            return {}

        if expiry is None:
            target = datetime.now() + timedelta(days=45)
            expiry = min(
                expirations,
                key=lambda d: abs(
                    (datetime.strptime(d, "%Y-%m-%d") - target).days
                ),
            )

        chain = tk.option_chain(expiry)
        spot = float(tk.history(period="1d")["Close"].iloc[-1])

        calls = chain.calls
        puts = chain.puts

        atm_strike = round(spot / 5) * 5

        atm_call = calls.iloc[(calls["strike"] - atm_strike).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts["strike"] - atm_strike).abs().argsort()[:1]]

        iv_call = float(atm_call["impliedVolatility"].iloc[0]) if not atm_call.empty else 0.3
        iv_put = float(atm_put["impliedVolatility"].iloc[0]) if not atm_put.empty else 0.3
        iv_atm = (iv_call + iv_put) / 2.0

        pcr_vol = float(puts["volume"].sum() / max(calls["volume"].sum(), 1))
        pcr_oi = float(puts["openInterest"].sum() / max(calls["openInterest"].sum(), 1))

        hist = tk.history(period="3mo")
        if len(hist) > 20:
            returns = hist["Close"].pct_change().dropna()
            rv = float(returns.std() * np.sqrt(252))
        else:
            rv = iv_atm

        vrp = iv_atm - rv

        return {
            "spot": float(spot),
            "expiry": expiry,
            "iv_atm": iv_atm,
            "iv_call": iv_call,
            "iv_put": iv_put,
            "iv_skew": iv_call - iv_put,
            "pcr_volume": pcr_vol,
            "pcr_oi": pcr_oi,
            "rv_21d": rv,
            "vrp": vrp,
            "atm_strike": atm_strike,
            "n_calls": len(calls),
            "n_puts": len(puts),
            "total_volume": int(calls["volume"].sum() + puts["volume"].sum()),
            "total_oi": int(calls["openInterest"].sum() + puts["openInterest"].sum()),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to fetch options for %s: %s", ticker, e)
        return {}


def build_historical_options_features(
    ticker: str,
    ohlcv: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    include_live: bool = False,
) -> pd.DataFrame:
    """Costruisce feature opzioni storiche allineate a ``ohlcv``.

    Poiche' yfinance non fornisce storico opzioni congruente con la lunghezza
    di OHLCV, usiamo approssimazioni light (lookahead-safe) derivate dalla
    sola serie dei prezzi:

    - ``opt_iv_est``  : RV * 1.2 + 0.05 (premium tipico IV/RV)
    - ``opt_vrp``     : IV_est - RV (volatility risk premium proxy)
    - ``opt_vrp_zscore`` : z-score del VRP su finestra 63d
    - ``opt_iv_rank_252d`` / ``opt_iv_percentile_252d`` : rank mobile
    - ``opt_iv_skew_est`` : skewness dei returns 63d come proxy dello skew
    - ``opt_vol_regime`` : 0/1/2 da IV rank (low/normal/high)

    Per le date recenti si tenta di fetchare snapshot live (yfinance) e
    riempire le colonne ``opt_iv_atm``, ``opt_pcr_*``, ``opt_vrp_real``;
    queste vengono forward-fillate sulle ultime barre disponibili.

    Parameters
    ----------
    ticker:
        Simbolo (es. ``"GME"``).
    ohlcv:
        OHLCV frame con colonna ``close`` (case-insensitive, lowercase).
    start_date, end_date:
        Riferiti per compatibilita' API; non filtrano (ohlcv e' gia' filtrato).
    include_live:
        Se ``True`` tenta di arricchire l'ultima barra con snapshot live
        (yfinance). Di default ``False`` per evitare colonne sparse / con
        lookahead bias durante il training storico. Le feature live vanno
        recuperate a parte durante l'inferenza live.

    Returns
    -------

    Returns
    -------
    pandas.DataFrame
        Indice temporale uguale a ``ohlcv``, colonne con prefisso ``opt_``.
    """
    del start_date, end_date  # ohlcv e' gia' filtrato dal chiamante

    if ohlcv is None or ohlcv.empty:
        logger.warning("Empty OHLCV frame, no options features")
        return pd.DataFrame()

    df = ohlcv.copy()
    close = df["close"] if "close" in df.columns else df["Close"]

    returns = close.pct_change()
    rv_21d = returns.rolling(21).std() * np.sqrt(252)

    iv_est = rv_21d * _IV_PREMIUM_MULT + _IV_PREMIUM_ADD
    vrp = iv_est - rv_21d

    options_features = pd.DataFrame(index=df.index)
    options_features["opt_rv_21d"] = rv_21d
    options_features["opt_iv_est"] = iv_est
    options_features["opt_vrp"] = vrp
    options_features["opt_vrp_zscore"] = (
        vrp - vrp.rolling(63).mean()
    ) / vrp.rolling(63).std().replace(0.0, np.nan)
    options_features["opt_iv_rank_252d"] = iv_est.rolling(252).rank(pct=True)
    options_features["opt_iv_percentile_252d"] = options_features["opt_iv_rank_252d"]
    options_features["opt_iv_skew_est"] = returns.rolling(63).skew()

    ir = options_features["opt_iv_rank_252d"]
    options_features["opt_vol_regime"] = np.where(
        ir < 0.25, 0, np.where(ir < 0.75, 1, 2)
    )

    # Snapshot live (opzionale) per le ultime barre
    if include_live:
        try:
            live_data = _fetch_options_yfinance(ticker)
            if live_data:
                last_date = df.index[-1]
                options_features.loc[last_date, "opt_iv_atm"] = live_data["iv_atm"]
                options_features.loc[last_date, "opt_pcr_vol"] = live_data["pcr_volume"]
                options_features.loc[last_date, "opt_pcr_oi"] = live_data["pcr_oi"]
                options_features.loc[last_date, "opt_iv_skew"] = live_data["iv_skew"]
                options_features.loc[last_date, "opt_vrp_real"] = live_data["vrp"]
                options_features[["opt_iv_atm",
                                  "opt_pcr_vol",
                                  "opt_pcr_oi",
                                  "opt_iv_skew",
                                  "opt_vrp_real",
                                  ]] = options_features[
                    ["opt_iv_atm",
                     "opt_pcr_vol",
                     "opt_pcr_oi",
                     "opt_iv_skew",
                     "opt_vrp_real",
                     ]
                ].ffill()
        except Exception as e:  # noqa: BLE001
            logger.warning("Live options fetch skipped: %s", e)

    logger.info(
        "Options features built: %d columns, %d rows",
        len(options_features.columns),
        len(options_features),
    )
    return options_features