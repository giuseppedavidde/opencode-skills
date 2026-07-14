"""Fractionally Differentiated Features (Lopez de Prado, AFML Ch.5).

I prezzi sono non stazionari I(1); i returns sono stazionari I(0) ma
perdono TUTTA la memoria. La differenziazione frazionaria I(d) con
``0 < d < 1`` produce una serie che preserva MEMORIA (informazione)
mantenendo la STAZIONARIETA'.

Formula::

    FD(X, d)_t = sum_{k=0}^{K} omega_k * X_{t-k}

    omega_0 = 1
    omega_k = -omega_{k-1} * (d - k + 1) / k

I pesi ``omega_k`` convergono a 0 per ``k -> inf``: tronchiamo la serie
quando diventano trascurabili (``|omega_k| < threshold``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from numpy.linalg import LinAlgError

from utils.logger import get_logger

logger = get_logger("features.fractional_diff")


FEATURE_DESCRIPTIONS: dict[str, str] = {
    "fd_close_d03": "Fractionally differentiated close (d=0.3)",
    "fd_close_d05": "Fractionally differentiated close (d=0.5)",
    "fd_close_d07": "Fractionally differentiated close (d=0.7)",
    "fd_volume_d03": "Fractionally differentiated volume (d=0.3)",
    "fd_volume_d05": "Fractionally differentiated volume (d=0.5)",
    "fd_volume_d07": "Fractionally differentiated volume (d=0.7)",
    "fd_optimal_d": "Optimal d value (minimum d for stationarity, ADF p<0.05)",
}


def _d_tag(d: float) -> str:
    """Restituisce il tag a due cifre per il valore di ``d`` (es. ``"05"``)."""
    return f"{int(round(d * 10)):02d}"


def _get_weights(d: float, threshold: float = 1e-5, max_len: int = 10000) -> np.ndarray:
    """Calcola i pesi ``omega_k`` per la differentiated series.

    Parameters
    ----------
    d:
        Differentiation parameter ``(0 < d < 1)``.
    threshold:
        Peso minimo in valore assoluto per troncare la serie di pesi.
    max_len:
        Lunghezza massima della serie di pesi (salvaguardia numerica).

    Returns
    -------
    numpy.ndarray
        Array di pesi ``[omega_0, omega_1, ..., omega_K]``.
    """
    weights: list[float] = [1.0]  # omega_0 = 1
    k = 1
    while k < max_len:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
    return np.asarray(weights, dtype=float)


def _compute_fd_series(series: pd.Series, d: float, threshold: float = 1e-5) -> pd.Series:
    """Calcola la fractionally differentiated series.

    Parameters
    ----------
    series:
        Serie temporale (prezzi o volume).
    d:
        Differenziazione frazionaria ``(0 < d < 1)``.
    threshold:
        Soglia per troncare i pesi.

    Returns
    -------
    pandas.Series
        Serie differenziata, allineata all'input. I primi ``K-1`` valori
        sono ``NaN`` per il lookback richiesto dai pesi.
    """
    weights = _get_weights(d, threshold)
    window = len(weights)
    fd_series = series.rolling(window=window, min_periods=window).apply(
        lambda x: float(np.dot(x[::-1], weights)),
        raw=True,
    )
    if series.name is not None:
        fd_series.name = f"fd_{series.name}_d{_d_tag(d)}"
    return fd_series


def _compute_optimal_d(
    series: pd.Series,
    d_min: float = 0.01,
    d_max: float = 0.99,
    step: float = 0.05,
    threshold: float = 1e-5,
    p_threshold: float = 0.05,
) -> float:
    """Trova il minimo ``d`` che rende la serie stazionaria (ADF p-value < ``p_threshold``).

    Parameters
    ----------
    series:
        Serie temporale.
    d_min:
        Minimo valore di ``d`` da testare.
    d_max:
        Massimo valore di ``d`` da testare (fallback se nessun ``d`` passa il test).
    step:
        Step di ricerca su ``d``.
    threshold:
        Soglia pesi per la FD.
    p_threshold:
        Soglia p-value del test ADF per accettare la stazionarieta'.

    Returns
    -------
    float
        Valore di ``d`` ottimale. Se nessun ``d`` produce stazionarieta'
        torna a ``d_max``.
    """
    d_values = np.arange(d_min, d_max + step, step)
    # Arrotonda a 2 decimali per evitare drift floating-point.
    d_values = np.round(d_values, 2)
    optimal_d = float(round(d_max, 2))  # default: massima differenziazione

    for d in d_values:
        fd = _compute_fd_series(series, float(d), threshold)
        fd_clean = fd.dropna()
        if len(fd_clean) < 10:
            continue
        try:
            adf_result = adfuller(
                fd_clean.to_numpy(),
                maxlag=min(20, max(0, len(fd_clean) // 3)),
                autolag=None,
            )
            p_value = adf_result[1]
        except (ValueError, LinAlgError, np.linalg.LinAlgError) as e:  # noqa: BLE001
            logger.debug("ADF test failed for d=%.2f on %s: %s", d, series.name, e)
            continue
        if p_value < p_threshold:
            optimal_d = float(d)
            break

    logger.info("Optimal d for %s: %.2f (ADF p<%.2f)", series.name, optimal_d, p_threshold)
    return optimal_d


def add_fractional_diff_features(
    df: pd.DataFrame,
    close_col: str = "close",
    volume_col: str = "volume",
    d_values: list[float] | None = None,
    compute_optimal: bool = True,
    min_rows_for_optimal: int = 100,
    threshold: float = 1e-5,
) -> pd.DataFrame:
    """Aggiunge feature fractionally differentiate al DataFrame.

    Parameters
    ----------
    df:
        DataFrame con colonne ``close`` e ``volume``.
    close_col:
        Nome della colonna prezzo.
    volume_col:
        Nome della colonna volume.
    d_values:
        Lista di ``d`` da calcolare (default ``[0.3, 0.5, 0.7]``).
    compute_optimal:
        Se ``True`` calcola anche ``d`` ottimale via test ADF e lo salva
        come colonna costante ``fd_optimal_d``.
    min_rows_for_optimal:
        Numero minimo di righe per tentare la ricerca di ``d`` ottimale.
    threshold:
        Soglia per troncare i pesi ``omega_k`` (Lopez de Prado default 1e-5).

    Returns
    -------
    pandas.DataFrame
        DataFrame con feature aggiunte (prefisso ``fd_``).
    """
    out = df.copy()

    if d_values is None:
        d_values = [0.3, 0.5, 0.7]

    if close_col not in out.columns:
        logger.warning("Column '%s' missing — skipping FD features", close_col)
        return out

    close = out[close_col]
    has_volume = volume_col in out.columns
    volume = out[volume_col] if has_volume else None

    weights_cache: dict[float, np.ndarray] = {}
    skipped: list[str] = []
    for d in d_values:
        tag = _d_tag(d)
        if d not in weights_cache:
            weights_cache[d] = _get_weights(d, threshold)
        n_weights = len(weights_cache[d])

        # Se il numero di pesi >= lunghezza della serie, l'intera FD sara' NaN:
        # il d e' infeasibile su una serie cosi' corta — saltiamo la feature.
        if n_weights >= len(close):
            skipped.append(f"fd_close_d{tag}")
            logger.warning(
                "Skipping fd_close_d%s: needs %d weights but series has %d rows",
                tag, n_weights, len(close),
            )
            continue
        out[f"fd_close_d{tag}"] = _compute_fd_series(close, d)
        if has_volume and volume is not None and n_weights < len(volume):
            out[f"fd_volume_d{tag}"] = _compute_fd_series(volume, d)
        elif has_volume:
            skipped.append(f"fd_volume_d{tag}")

    if skipped:
        logger.info("FD features skipped (infeasible d): %s", ", ".join(skipped))

    if compute_optimal and len(close) >= min_rows_for_optimal:
        opt_d = _compute_optimal_d(close)
        out["fd_optimal_d"] = float(opt_d)
    else:
        logger.info(
            "Skipping optimal d search (rows=%d < %d)",
            len(close),
            min_rows_for_optimal,
        )

    return out


def get_fractional_diff_feature_columns(df: pd.DataFrame) -> list[str]:
    """Restituisce le colonne FD presenti in ``df``."""
    return [c for c in df.columns if c.startswith("fd_")]