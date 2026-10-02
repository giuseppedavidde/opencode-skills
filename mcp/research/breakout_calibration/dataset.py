"""Universe loading and OHLCV acquisition with an on-disk pickle cache.

Data source: Yahoo Finance via ``yfinance`` (auto-adjusted OHLCV).
Universe: the point-in-time S&P 500 constituent CSV shipped with the
trading MCP (``src/trading_mcp/data/historical_universe_sp500.csv``).
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf

from . import config

logger = logging.getLogger(__name__)

_OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


def load_universe_symbols(path: Path | None = None) -> list[str]:
    """Return the sorted, de-duplicated list of universe symbols.

    The CSV uses ``#`` comment lines and the columns
    ``symbol, date_added, date_removed``.
    """
    csv_path = path or config.UNIVERSE_CSV
    frame = pd.read_csv(csv_path, comment="#")
    frame.columns = [str(col).strip() for col in frame.columns]
    symbols = (
        frame["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    )
    return sorted(symbol for symbol in symbols if symbol)


def _cache_path(n_symbols: int) -> Path:
    name = (
        f"ohlcv_{config.PERIOD_START}_{config.PERIOD_END}_"
        f"n{n_symbols}_adj.pkl"
    )
    return config.DATA_CACHE_DIR / name


def _download_chunk(symbols: list[str]) -> pd.DataFrame:
    return yf.download(
        symbols,
        start=config.PERIOD_START,
        end=config.PERIOD_END,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )


def _extract_symbol(raw: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    if not isinstance(raw.columns, pd.MultiIndex):
        return None
    if symbol not in raw.columns.get_level_values(0):
        return None
    sub = raw[symbol].copy()
    available = [col for col in _OHLCV_COLUMNS if col in sub.columns]
    if len(available) < len(_OHLCV_COLUMNS):
        return None
    sub = sub.loc[:, list(_OHLCV_COLUMNS)].dropna(how="any")
    if sub.empty:
        return None
    sub.index = pd.to_datetime(sub.index).tz_localize(None)
    return sub.sort_index()


def download_ohlcv(
    symbols: Iterable[str],
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Download auto-adjusted daily OHLCV for ``symbols``.

    Returns a mapping ``symbol -> DataFrame`` with columns
    ``Open, High, Low, Close, Volume`` and a naive ``DatetimeIndex``.
    Results are cached in ``data_cache/`` as a pickle.
    """
    symbol_list = [str(sym).upper() for sym in symbols]
    cache_path = _cache_path(len(symbol_list))
    if use_cache and cache_path.exists():
        logger.info("Loading OHLCV cache %s", cache_path.name)
        with cache_path.open("rb") as handle:
            cached: dict[str, pd.DataFrame] = pickle.load(handle)
        return cached

    config.DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for start in range(0, len(symbol_list), config.DOWNLOAD_CHUNK):
        chunk = symbol_list[start : start + config.DOWNLOAD_CHUNK]
        logger.info(
            "Downloading %d symbols (%d-%d)", len(chunk), start, start + len(chunk)
        )
        raw = _download_chunk(chunk)
        for symbol in chunk:
            frame = _extract_symbol(raw, symbol)
            if frame is not None and len(frame) >= config.MIN_HISTORY_DAYS:
                result[symbol] = frame

    logger.info("Loaded %d/%d symbols", len(result), len(symbol_list))
    with cache_path.open("wb") as handle:
        pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return result


def load_benchmark(use_cache: bool = True) -> pd.DataFrame:
    """Download the benchmark (SPY) separately, cached in the same dir."""
    cache_file = config.DATA_CACHE_DIR / f"benchmark_{config.BENCHMARK_SYMBOL}.pkl"
    if use_cache and cache_file.exists():
        with cache_file.open("rb") as handle:
            return pickle.load(handle)
    config.DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw = _download_chunk([config.BENCHMARK_SYMBOL])
    frame = _extract_symbol(raw, config.BENCHMARK_SYMBOL)
    if frame is None:
        raise RuntimeError(f"Could not download benchmark {config.BENCHMARK_SYMBOL}")
    with cache_file.open("wb") as handle:
        pickle.dump(frame, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return frame
