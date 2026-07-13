"""Technical indicators (~60+ features) computed with pure pandas/numpy.

``pandas-ta`` is not used because it depends on ``numba`` which does not yet
support Python 3.14 at the time of writing. All indicators are implemented
as vectorised pandas operations and follow a strict naming convention:

- ``mom_*``   momentum
- ``trend_*`` trend
- ``vol_*``   volatility
- ``vol_volume_*`` / ``vol_obv`` / ``vol_mfi_*`` volume
- ``prc_*``   price transforms

Every public function takes a DataFrame with at least the columns
``open``, ``high``, ``low``, ``close``, ``volume`` (case-insensitive) and
returns a *copy* of the input frame with the new feature columns appended.
Functions are pure: they never mutate the input.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

_REQUIRED = ("open", "high", "low", "close", "volume")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase the canonical OHLCV columns and return a copy."""
    out = df.copy()
    rename = {c: c.lower() for c in out.columns if isinstance(c, str)}
    out = out.rename(columns=rename)
    missing = [c for c in _REQUIRED if c not in out.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")
    return out


def _wilder_smooth(series: pd.Series, window: int) -> pd.Series:
    """Wilder smoothing (EMA with alpha = 1/window)."""
    return series.ewm(alpha=1.0 / window, adjust=False).mean()


# --------------------------------------------------------------------------- #
# Momentum
# --------------------------------------------------------------------------- #
def add_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Momentum features: ROC family, RSI, Stochastic, MACD, Williams %R,
    Triangle Momentum (TSIA), Absolute Price Oscillator."""
    out = _normalize(df)
    close = out["close"]
    high = out["high"]
    low = out["low"]

    # Rate of change ------------------------------------------------------- #
    for w in (5, 10, 21, 63):
        out[f"mom_roc_{w}d"] = close.pct_change(w) * 100.0

    # RSI 14 --------------------------------------------------------------- #
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_smooth(gain, 14)
    avg_loss = _wilder_smooth(loss, 14)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out["mom_rsi_14d"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # Stochastic 14 ------------------------------------------------------- #
    ll14 = low.rolling(14).min()
    hh14 = high.rolling(14).max()
    out["mom_stochk_14d"] = (close - ll14) / (hh14 - ll14).replace(0.0, np.nan) * 100.0
    out["mom_stochd_14d"] = out["mom_stochk_14d"].rolling(3).mean()

    # MACD ----------------------------------------------------------------- #
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["mom_macd_line"] = ema12 - ema26
    out["mom_macd_signal"] = out["mom_macd_line"].ewm(span=9, adjust=False).mean()
    out["mom_macd_hist"] = out["mom_macd_line"] - out["mom_macd_signal"]

    # Williams %R --------------------------------------------------------- #
    out["mom_williams_r_14d"] = (hh14 - close) / (hh14 - ll14).replace(0.0, np.nan) * -100.0

    # Triangle momentum (TSIA) - 3/10/20 EMA triangle oscillator ----------- #
    ema3 = close.ewm(span=3, adjust=False).mean()
    ema10 = close.ewm(span=10, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    out["mom_tsia"] = (ema3 - ema10) + (ema10 - ema20)

    # Absolute Price Oscillator ------------------------------------------- #
    out["mom_apo"] = ema12 - ema26

    return out


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #
def add_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Trend features: SMAs, EMAs, ADX / DI, Trend Signal (3/10/20)."""
    out = _normalize(df)
    close = out["close"]
    high = out["high"]
    low = out["low"]

    # Moving averages ------------------------------------------------------ #
    for w in (20, 50, 200):
        out[f"trend_sma_{w}d"] = close.rolling(w).mean()
    for w in (12, 26, 50):
        out[f"trend_ema_{w}d"] = close.ewm(span=w, adjust=False).mean()

    # ADX / DMP / DMN (Wilder) -------------------------------------------- #
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = _wilder_smooth(
        pd.concat(
            [(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1),
        14,
    )
    plus_di = 100.0 * _wilder_smooth(plus_dm, 14) / atr.replace(0.0, np.nan)
    minus_di = 100.0 * _wilder_smooth(minus_dm, 14) / atr.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    out["trend_adx_14d"] = _wilder_smooth(dx, 14)
    out["trend_dmp_14d"] = plus_di
    out["trend_dmn_14d"] = minus_di

    # Trend signal (Tline 3/10/20 linear regression slope) ----------------- #
    out["trend_tline_3"] = close.rolling(3).apply(_slope, raw=True)
    out["trend_tline_10"] = close.rolling(10).apply(_slope, raw=True)
    out["trend_tline_20"] = close.rolling(20).apply(_slope, raw=True)

    return out


def _slope(arr: np.ndarray) -> float:
    n = len(arr)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = arr.astype(float)
    mask = np.isfinite(y)
    if mask.sum() < 2:
        return 0.0
    slope = np.polyfit(x[mask], y[mask], 1)[0]
    return float(slope)


# --------------------------------------------------------------------------- #
# Volatility
# --------------------------------------------------------------------------- #
def add_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """Volatility features: ATR, NATR, Bollinger Bands, stddev, Keltner,
    Chaikin Volatility."""
    out = _normalize(df)
    close = out["close"]
    high = out["high"]
    low = out["low"]

    # ATR ----------------------------------------------------------------- #
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = _wilder_smooth(tr, 14)
    out["vol_atr_14d"] = atr
    out["vol_natr_14d"] = 100.0 * atr / close.shift(1).replace(0.0, np.nan)

    # Bollinger Bands width & %B ------------------------------------------ #
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    out["vol_bbwidth_20d"] = (upper - lower) / sma20.replace(0.0, np.nan)
    out["vol_bbpct_20d"] = (close - lower) / (upper - lower).replace(0.0, np.nan)

    # Rolling stddev of returns ------------------------------------------- #
    rets = close.pct_change()
    out["vol_stddev_21d"] = rets.rolling(21).std()

    # Keltner Channels width --------------------------------------------- #
    ema20 = close.ewm(span=20, adjust=False).mean()
    kc_upper = ema20 + 2 * atr
    kc_lower = ema20 - 2 * atr
    out["vol_keltner_width_20d"] = (kc_upper - kc_lower) / ema20.replace(0.0, np.nan)

    # Chaikin Volatility (EMA of H-L, % change 10d) ----------------------- #
    hl_diff = high - low
    ema_hl = hl_diff.ewm(span=10, adjust=False).mean()
    out["vol_chaikin_10d"] = (ema_hl - ema_hl.shift(10)) / ema_hl.shift(10).replace(0.0, np.nan)

    return out


# --------------------------------------------------------------------------- #
# Volume
# --------------------------------------------------------------------------- #
def add_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Volume features: SMA21 ratio, OBV, MFI, Ease of Movement, vol std,
    dollar volume."""
    out = _normalize(df)
    close = out["close"]
    high = out["high"]
    low = out["low"]
    volume = out["volume"].astype(float)

    # Volume SMA21 ratio --------------------------------------------------- #
    vol_sma21 = volume.rolling(21).mean()
    out["vol_volume_ratio_21d"] = volume / vol_sma21.replace(0.0, np.nan)

    # OBV ----------------------------------------------------------------- #
    sign = np.sign(close.diff().fillna(0.0))
    obv = (sign * volume).cumsum()
    out["vol_obv"] = obv

    # MFI 14 ------------------------------------------------------------- #
    tp = (high + low + close) / 3.0
    mf = tp * volume
    pos = mf.where(tp > tp.shift(1), 0.0)
    neg = mf.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(14).sum()
    neg_sum = neg.rolling(14).sum()
    mfi = 100.0 - (100.0 / (1.0 + pos_sum / neg_sum.replace(0.0, np.nan)))
    out["vol_mfi_14d"] = mfi.fillna(50.0)

    # Ease of Movement ---------------------------------------------------- #
    dm = ((high + low) / 2.0 - (high.shift(1) + low.shift(1)) / 2.0)
    br = (volume / 1e6) / (high - low).replace(0.0, np.nan)
    eom = dm / br.replace(0.0, np.nan)
    out["vol_eom_14d"] = eom.rolling(14).mean()

    # Volume std (1y window normalised) ----------------------------------- #
    out["vol_volume_std_252d"] = (volume.pct_change().rolling(252).std()).fillna(0.0)

    # Dollar volume ------------------------------------------------------- #
    out["vol_dollar_volume"] = (close * volume).fillna(0.0)

    return out


# --------------------------------------------------------------------------- #
# Price transforms
# --------------------------------------------------------------------------- #
def add_price_transforms(df: pd.DataFrame) -> pd.DataFrame:
    """Price transforms: HL2, HLC3, OHLC4, daily returns, log returns,
    squared returns."""
    out = _normalize(df)
    open_ = out["open"]
    high = out["high"]
    low = out["low"]
    close = out["close"]

    out["prc_hl2"] = (high + low) / 2.0
    out["prc_hlc3"] = (high + low + close) / 3.0
    out["prc_ohlc4"] = (open_ + high + low + close) / 4.0
    out["prc_returns_1d"] = close.pct_change()
    out["prc_log_returns_1d"] = np.log(close / close.shift(1))
    out["prc_squared_returns"] = out["prc_returns_1d"] ** 2

    return out


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def add_all_technical(df: pd.DataFrame) -> pd.DataFrame:
    """Append every technical feature category to ``df``."""
    out = add_price_transforms(df)
    out = add_momentum(out)
    out = add_trend(out)
    out = add_volatility(out)
    out = add_volume(out)
    return out


FEATURE_DESCRIPTIONS: dict[str, str] = {
    "mom_roc_5d": "5-day rate of change (%)",
    "mom_roc_10d": "10-day rate of change (%)",
    "mom_roc_21d": "21-day rate of change (%)",
    "mom_roc_63d": "63-day rate of change (%)",
    "mom_rsi_14d": "14-day Relative Strength Index",
    "mom_stochk_14d": "14-day stochastic %K",
    "mom_stochd_14d": "14-day stochastic %D (3-day SMA of %K)",
    "mom_macd_line": "MACD line (EMA12 - EMA26)",
    "mom_macd_signal": "MACD signal (EMA9 of line)",
    "mom_macd_hist": "MACD histogram (line - signal)",
    "mom_williams_r_14d": "Williams %R 14",
    "mom_tsia": "Triangle momentum oscillator (3/10/20 EMAs)",
    "mom_apo": "Absolute Price Oscillator",
    "trend_sma_20d": "20-day simple moving average",
    "trend_sma_50d": "50-day SMA",
    "trend_sma_200d": "200-day SMA",
    "trend_ema_12d": "12-day EMA",
    "trend_ema_26d": "26-day EMA",
    "trend_ema_50d": "50-day EMA",
    "trend_adx_14d": "14-day ADX",
    "trend_dmp_14d": "+DI 14",
    "trend_dmn_14d": "-DI 14",
    "trend_tline_3": "3-bar linear-regression slope",
    "trend_tline_10": "10-bar linear-regression slope",
    "trend_tline_20": "20-bar linear-regression slope",
    "vol_atr_14d": "14-day ATR (Wilder)",
    "vol_natr_14d": "Normalised ATR (%)",
    "vol_bbwidth_20d": "Bollinger band width (20,2)",
    "vol_bbpct_20d": "Bollinger %B (20,2)",
    "vol_stddev_21d": "21-day rolling std of returns",
    "vol_keltner_width_20d": "Keltner channel width (20,2)",
    "vol_chaikin_10d": "Chaikin Volatility (10)",
    "vol_volume_ratio_21d": "Volume / SMA21(volume)",
    "vol_obv": "On-Balance Volume (cumulative)",
    "vol_mfi_14d": "Money Flow Index 14",
    "vol_eom_14d": "Ease of Movement 14",
    "vol_volume_std_252d": "1y rolling std of volume pct chg",
    "vol_dollar_volume": "Dollar volume traded",
    "prc_hl2": "(High + Low) / 2",
    "prc_hlc3": "(High + Low + Close) / 3",
    "prc_ohlc4": "(Open + High + Low + Close) / 4",
    "prc_returns_1d": "Daily return",
    "prc_log_returns_1d": "Daily log return",
    "prc_squared_returns": "Squared daily return",
}


def feature_columns() -> list[str]:
    """Return the ordered list of technical feature column names."""
    return list(FEATURE_DESCRIPTIONS.keys())


def _ensure_columns(df: pd.DataFrame, names: Iterable[str]) -> list[str]:
    return [n for n in names if n in df.columns]