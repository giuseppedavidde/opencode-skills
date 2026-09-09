"""Centralized data provider with TTL cache.

Tutti i componenti (analyze_stock, bali, tsmom, lgbm) leggono da qui.
Il dato viene fetchato UNA SOLA VOLTA per ticker.

Ordine provider:
1. Cache (se fresco)
2. yfinance (sempre disponibile)
3. Alpha Vantage (enrichment, se chiave presente e non rate-limited)
4. FMP (fallback, se disponibile)

P2 August 2026: added ``freshness_label`` utility with tiers (live, recent,
stale, cached) and ``data_freshness`` / ``last_data_date`` fields in
outputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Disk persistence (M2: cold-start elimination) ────────────────────
# Hist/info sono persistiti su disco con TTL per evitare ri-fetch al riavvio
# del server. Si usa pickle (stdlib, zero dipendenze native) invece di parquet
# perche' pyarrow/fastparquet non sono installati nel venv condiviso.
_DATA_CACHE_DIR = Path(
    os.environ.get(
        "TRADING_DATA_CACHE_DIR",
        str(Path.home() / ".cache" / "trading_mcp" / "data"),
    )
)

# TTL su disco per periodo/interval: i daily bar non cambiano intraday → 6h;
# i bar intraday → 1h (allineato al TTL in-memory di default).
_DISK_TTL: dict[str, float] = {
    "daily": 6 * 3600,
    "intraday": 3600,
}


def _disk_ttl_for(interval: str) -> float:
    """Resolve disk TTL for a bar interval."""
    return _DISK_TTL["daily"] if interval == "1d" else _DISK_TTL["intraday"]


def _disk_path(kind: str, key: str) -> Path:
    """Build a deterministic, filesystem-safe path for a cache key."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return _DATA_CACHE_DIR / f"{kind}_{digest}.pkl"


def _disk_meta_path(kind: str, key: str) -> Path:
    """Sidecar metadata file storing the fetch timestamp for TTL checks."""
    digest = hashlib.sha1(f"{kind}:{key}".encode("utf-8")).hexdigest()[:24]
    return _DATA_CACHE_DIR / f"{digest}.meta.json"


def _disk_load(kind: str, key: str, ttl: float) -> Any | None:
    """Load a persisted payload from disk if still within TTL."""
    data_path = _disk_path(kind, key)
    meta_path = _disk_meta_path(kind, key)
    if not data_path.exists() or not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        if time.time() - float(meta.get("ts", 0.0)) > ttl:
            return None
        with open(data_path, "rb") as fh:
            return pickle.load(fh)
    except (OSError, ValueError, EOFError, pickle.PickleError):
        return None


def _disk_save(kind: str, key: str, data: Any) -> None:
    """Persist a payload to disk with a sidecar timestamp."""
    try:
        _DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data_path = _disk_path(kind, key)
        meta_path = _disk_meta_path(kind, key)
        with open(data_path, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time()}, fh)
    except (OSError, pickle.PickleError) as exc:
        logger.warning("Disk cache save failed for %s: %s: %s", kind, type(exc).__name__, exc)


# ── Data freshness utility ────────────────────────────────────────────

_DEFAULT_FRESHNESS_THRESHOLDS: dict[str, dict[str, float]] = {
    "stock": {"live": 300, "recent": 3600, "stale": 86400},
    "crypto": {"live": 300, "recent": 3600, "stale": 86400},
    "options": {"live": 60, "recent": 300, "stale": 3600},
    "macro": {"live": 300, "recent": 1200, "stale": 7200},
}


def freshness_label(
    last_ts: float | None,
    now: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Classifies data freshness based on age.

    Args:
        last_ts: Unix timestamp of the last data point (or tz-aware
            datetime). If None → 'cached'.
        now: Current timestamp (defaults to ``time.time()``).
        thresholds: Dict with ``live``, ``recent``, ``stale`` keys
            in seconds. Defaults to stock thresholds.

    Returns:
        One of: ``'live'``, ``'recent'``, ``'stale'``, ``'cached'``.
    """
    if last_ts is None:
        return "cached"

    if now is None:
        now = time.time()

    if isinstance(last_ts, str):
        try:
            from datetime import datetime as _dt
            last_dt = _dt.fromisoformat(last_ts.replace("Z", "+00:00"))
            last_ts = last_dt.timestamp()
        except (ValueError, TypeError):
            return "cached"

    if thresholds is None:
        thresholds = _DEFAULT_FRESHNESS_THRESHOLDS["stock"]

    age = now - last_ts
    if age < thresholds["live"]:
        return "live"
    if age < thresholds["recent"]:
        return "recent"
    if age < thresholds["stale"]:
        return "stale"
    return "cached"


def get_last_data_date(hist: pd.DataFrame | None) -> str | None:
    """Extracts the date of the last bar from OHLCV history.

    Args:
        hist: DataFrame with DatetimeIndex.

    Returns:
        ISO date string or None if no data.
    """
    if hist is None or hist.empty:
        return None
    try:
        last = hist.index[-1]
        if hasattr(last, "date"):
            return str(last.date())
        return str(last)[:10]
    except (IndexError, AttributeError):
        return None


@dataclass
class CacheEntry:
    """TTL cache entry with staleness tracking."""
    data: Any
    timestamp: float
    ttl: float
    stale: bool = False

    @property
    def age_seconds(self) -> float:
        """Seconds since cache entry was created."""
        return time.time() - self.timestamp

    @property
    def is_fresh(self) -> bool:
        """True if data is within TTL and not marked stale."""
        return not self.stale and self.age_seconds < self.ttl

    @property
    def has_data(self) -> bool:
        """True if cache entry has usable data (not None, DataFrame not empty)."""
        if self.data is None:
            return False
        if isinstance(self.data, pd.DataFrame):
            return not self.data.empty
        return True


@dataclass
class TickerCache:
    """Per-ticker cache holding hist, info, options, and optional stale copies.

    ``hist`` e' indicizzato per ``(period, interval)``: un fetch ``1y`` non deve
    avvelenare un successivo ``5d`` (fix A1).
    """

    hist: dict[tuple[str, str], CacheEntry] = field(default_factory=dict)
    info: CacheEntry | None = None
    options_expirations: CacheEntry | None = None
    options_chains: dict[str, CacheEntry] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class DataProvider:
    """Centralized data provider with TTL cache.

    All components read from this single source. Data is fetched once
    per ticker and cached with configurable TTLs.

    Provider order:
    1. Cache (if fresh)
    2. yfinance (always available)
    3. Alpha Vantage (enrichment, if key present and not rate-limited)
    4. FMP (fallback, if available)

    If a yfinance fetch fails, serves stale cache data instead of failing.
    """

    DEFAULT_TTL: dict[str, float] = {
        "hist": 3600,          # 1 hour for OHLCV prices
        "info": 21600,         # 6 hours for fundamentals
        "options": 3600,       # 1 hour for options expirations
        "options_chain": 60,   # 1 minute for option chains (intraday)
    }

    def __init__(self, ttl_overrides: dict[str, float] | None = None) -> None:
        self._cache: dict[str, TickerCache] = {}
        self._global_lock = threading.RLock()
        self._ttl = dict(self.DEFAULT_TTL)
        if ttl_overrides:
            self._ttl.update(ttl_overrides)

    # ── Public API ─────────────────────────────────────────────────────

    def get_ticker(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> tuple[yf.Ticker, dict[str, Any], pd.DataFrame]:
        """Fetch ticker data with TTL cache.

        Drop-in replacement for the scanner's _fetch_with_retry.
        Returns (Ticker, info, hist) — same interface as the old code.

        Args:
            symbol: Stock ticker (e.g. 'AAPL', 'ENI.MI').
            period: Data period for OHLCV.
            interval: Bar interval.

        Returns:
            Tuple of (yfinance.Ticker, info dict, hist DataFrame).
            On failure with no cache, returns (None, {}, empty DataFrame).
        """
        t = yf.Ticker(symbol)
        info = self.get_info(symbol)
        hist = self.get_hist(symbol, period=period, interval=interval)
        return t, info, hist

    def get_hist(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetch OHLCV history with TTL cache (memory + disk).

        Cache key includes ``(period, interval)`` so a ``1y`` fetch never
        poisons a subsequent ``5d`` fetch (fix A1).
        """
        tc = self._ensure_ticker_cache(symbol)
        cache_key = (period, interval)

        with tc.lock:
            entry = tc.hist.get(cache_key)
            if entry is not None and entry.is_fresh:
                logger.debug("Cache HIT: hist for %s (%.0fs old)",
                             symbol, entry.age_seconds)
                return entry.data

        # Disk persistence (M2): cold-start → avoid re-fetch when TTL-fresh.
        disk_key = f"hist:{symbol}:{period}:{interval}"
        hist = _disk_load("hist", disk_key, _disk_ttl_for(interval))
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            logger.debug("Disk HIT: hist for %s %s/%s", symbol, period, interval)
            with tc.lock:
                tc.hist[cache_key] = CacheEntry(
                    data=hist,
                    timestamp=time.time(),
                    ttl=self._ttl["hist"],
                )
            return hist

        # Fetch outside lock to avoid deadlock during yfinance call
        hist = self._fetch_hist(symbol, period, interval)

        # If fetch failed (empty), try stale cache
        if (hist is None or hist.empty) and entry is not None and entry.has_data:
            with tc.lock:
                if entry.data is not None:
                    entry.stale = True
                    logger.debug("Serving STALE hist for %s after fetch failure", symbol)
                    return entry.data

        with tc.lock:
            tc.hist[cache_key] = CacheEntry(
                data=hist,
                timestamp=time.time(),
                ttl=self._ttl["hist"],
            )

        if hist is not None and not hist.empty:
            _disk_save("hist", disk_key, hist)

        return hist

    def get_info(self, symbol: str) -> dict[str, Any]:
        """Fetch fundamental info with 6-hour TTL cache (memory + disk)."""
        tc = self._ensure_ticker_cache(symbol)

        with tc.lock:
            entry = tc.info
            if entry is not None and entry.is_fresh:
                logger.debug("Cache HIT: info for %s (%.0fs old)",
                             symbol, entry.age_seconds)
                return entry.data.copy() if entry.data else {}

        # Disk persistence (M2).
        disk_key = f"info:{symbol}"
        info = _disk_load("info", disk_key, self._ttl["info"])
        if isinstance(info, dict) and info:
            with tc.lock:
                tc.info = CacheEntry(
                    data=info,
                    timestamp=time.time(),
                    ttl=self._ttl["info"],
                )
            return info.copy()

        info = self._fetch_info(symbol)

        # If fetch failed (empty), try stale cache
        if (not info) and entry is not None and entry.has_data:
            with tc.lock:
                if entry.data:
                    entry.stale = True
                    logger.debug("Serving STALE info for %s after fetch failure", symbol)
                    return entry.data.copy()

        with tc.lock:
            tc.info = CacheEntry(
                data=info,
                timestamp=time.time(),
                ttl=self._ttl["info"],
            )

        if info:
            _disk_save("info", disk_key, info)

        return info

    def get_options_expirations(self, symbol: str) -> list[str]:
        """Fetch options expirations with 1-hour TTL cache."""
        tc = self._ensure_ticker_cache(symbol)

        with tc.lock:
            entry = tc.options_expirations
            if entry is not None and entry.is_fresh:
                logger.debug("Cache HIT: options for %s (%.0fs old)",
                             symbol, entry.age_seconds)
                return entry.data.copy() if entry.data else []

        expirations = self._fetch_options_expirations(symbol)

        # If fetch failed (empty), try stale cache
        if (not expirations) and entry is not None and entry.has_data and entry.data:
            with tc.lock:
                if entry.data:
                    entry.stale = True
                    logger.debug("Serving STALE options for %s after fetch failure", symbol)
                    return entry.data.copy()

        with tc.lock:
            tc.options_expirations = CacheEntry(
                data=expirations,
                timestamp=time.time(),
                ttl=self._ttl["options"],
            )

        return expirations

    def get_options_chain(
        self, symbol: str, expiry: str
    ) -> tuple[pd.DataFrame, pd.DataFrame] | None:
        """Fetch raw options chain (calls, puts) for a specific expiry.

        Returns the option_chain result (namedtuple with .calls and .puts).
        Cached with 60-second TTL for intraday freshness.
        """
        tc = self._ensure_ticker_cache(symbol)

        with tc.lock:
            if expiry in tc.options_chains and tc.options_chains[expiry].is_fresh:
                entry = tc.options_chains[expiry]
                logger.debug("Cache HIT: chain %s/%s (%.0fs old)",
                             symbol, expiry, entry.age_seconds)
                return entry.data

        chain = None
        try:
            t = yf.Ticker(symbol)
            chain = t.option_chain(expiry)
            logger.debug("Fetched chain for %s/%s", symbol, expiry)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch chain for %s/%s: %s: %s",
                           symbol, expiry, type(e).__name__, e)
            with tc.lock:
                if expiry in tc.options_chains and tc.options_chains[expiry].has_data:
                    tc.options_chains[expiry].stale = True
                    logger.debug("Serving STALE chain for %s/%s", symbol, expiry)
                    return tc.options_chains[expiry].data
            return None

        with tc.lock:
            tc.options_chains[expiry] = CacheEntry(
                data=chain,
                timestamp=time.time(),
                ttl=self._ttl["options_chain"],
            )

        return chain

    def get_macro_context(self) -> dict[str, Any]:
        """Fetch macro indicators: VIX, DXY, BTC price via yfinance.

        Returns raw values without regime detection.
        The caller applies regime classification on top.
        """
        vix_val = None
        dxy_val = None
        dxy_prev = None
        btc_price = None

        try:
            hist = self.get_hist("^VIX", period="5d")
            if not hist.empty:
                vix_val = round(float(hist["Close"].iloc[-1]), 2)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch VIX", exc_info=True)

        try:
            hist = self.get_hist("DX-Y.NYB", period="1mo")
            if not hist.empty and len(hist) >= 5:
                dxy_val = round(float(hist["Close"].iloc[-1]), 2)
                dxy_prev = float(hist["Close"].iloc[-min(len(hist), 22)])
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch DXY", exc_info=True)

        try:
            hist = self.get_hist("BTC-USD", period="5d")
            if not hist.empty:
                btc_price = round(float(hist["Close"].iloc[-1]), 0)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch BTC", exc_info=True)

        return {
            "vix": vix_val,
            "dxy": dxy_val,
            "dxy_prev": dxy_prev,
            "btc_dominance": btc_price,
        }

    def get_crypto_hist(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Fetch crypto OHLCV history via yfinance.

        Convenience wrapper around get_hist for crypto tickers.
        Args:
            symbol: Crypto symbol in yfinance format (e.g. 'BTC-USD').
            period: Data period.
        """
        return self.get_hist(symbol, period=period)

    def clear(self, ticker: str | None = None) -> None:
        """Clear cache for a specific ticker or all tickers.

        Args:
            ticker: Ticker to clear. If None, clears entire cache.
        """
        with self._global_lock:
            if ticker is None:
                self._cache.clear()
                logger.info("Cleared entire DataProvider cache")
            else:
                self._cache.pop(ticker, None)
                logger.debug("Cleared cache for %s", ticker)

    def cache_stats(self) -> dict[str, Any]:
        """Return cache statistics for monitoring."""
        total_entries = 0
        fresh_entries = 0
        stale_entries = 0

        with self._global_lock:
            for tc in self._cache.values():
                for hist_entry in tc.hist.values():
                    if hist_entry.has_data:
                        total_entries += 1
                        if hist_entry.is_fresh:
                            fresh_entries += 1
                        elif hist_entry.stale:
                            stale_entries += 1
                for attr in ("info", "options_expirations"):
                    entry = getattr(tc, attr, None)
                    if entry is not None and entry.has_data:
                        total_entries += 1
                        if entry.is_fresh:
                            fresh_entries += 1
                        elif entry.stale:
                            stale_entries += 1
                for chain_entry in tc.options_chains.values():
                    if chain_entry.has_data:
                        total_entries += 1
                        if chain_entry.is_fresh:
                            fresh_entries += 1
                        elif chain_entry.stale:
                            stale_entries += 1

        return {
            "tickers_cached": len(self._cache),
            "total_entries": total_entries,
            "fresh_entries": fresh_entries,
            "stale_entries": stale_entries,
        }

    def get_data_freshness(
        self, symbol: str, data_type: str = "stock"
    ) -> dict[str, str | None]:
        """Get freshness label and last data date for a ticker.

        Args:
            symbol: Stock ticker (e.g. 'AAPL').
            data_type: 'stock', 'crypto', 'options', or 'macro'.

        Returns:
            dict with ``freshness`` label and ``last_data_date``.
        """
        tc = self._cache.get(symbol)
        thresholds = _DEFAULT_FRESHNESS_THRESHOLDS.get(
            data_type, _DEFAULT_FRESHNESS_THRESHOLDS["stock"]
        )

        last_data_date: str | None = None
        last_ts: float | None = None

        if tc is not None and tc.hist:
            for hist_entry in tc.hist.values():
                if not hist_entry.has_data:
                    continue
                hist_data = hist_entry.data
                if isinstance(hist_data, pd.DataFrame) and not hist_data.empty:
                    last_data_date = get_last_data_date(hist_data)
                    if last_ts is None or hist_entry.timestamp > last_ts:
                        last_ts = hist_entry.timestamp

        label = freshness_label(last_ts, thresholds=thresholds)
        return {
            "freshness": label,
            "last_data_date": last_data_date,
        }

    # ── Internal helpers ───────────────────────────────────────────────

    def _ensure_ticker_cache(self, symbol: str) -> TickerCache:
        """Get or create per-ticker cache entry."""
        with self._global_lock:
            if symbol not in self._cache:
                self._cache[symbol] = TickerCache()
            return self._cache[symbol]

    def _fetch_hist(
        self, symbol: str, period: str, interval: str
    ) -> pd.DataFrame:
        """Fetch OHLCV history from yfinance."""
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period=period, interval=interval)
            if hist is not None and not hist.empty:
                logger.debug("Fetched hist for %s: %d rows", symbol, len(hist))
                return hist
            return pd.DataFrame()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch hist for %s: %s: %s",
                           symbol, type(e).__name__, e)
            return pd.DataFrame()

    def _fetch_info(self, symbol: str) -> dict[str, Any]:
        """Fetch fundamental info from yfinance, with FMP fallback."""
        # 1. yfinance (primary)
        try:
            t = yf.Ticker(symbol)
            info = t.info
            if info:
                logger.debug("Fetched info for %s: %d fields", symbol, len(info))
                return info
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("yfinance info failed for %s: %s: %s",
                           symbol, type(e).__name__, e)

        # 2. FMP (fallback)
        try:
            from trading_mcp.data.fmp_fetcher import fetch_fmp_fundamentals
            fmp = fetch_fmp_fundamentals(symbol)
            if fmp:
                logger.debug("Fetched info from FMP for %s: %d fields",
                             symbol, len(fmp))
                return fmp
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("FMP info fallback failed for %s: %s: %s",
                           symbol, type(e).__name__, e)

        return {}

    def _fetch_options_expirations(self, symbol: str) -> list[str]:
        """Fetch options expiration dates from yfinance."""
        try:
            t = yf.Ticker(symbol)
            expirations = list(t.options)
            logger.debug("Fetched %d expirations for %s", len(expirations), symbol)
            return expirations
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to fetch options for %s: %s: %s",
                           symbol, type(e).__name__, e)
            return []


# ── Module-level singleton ────────────────────────────────────────────

data_provider = DataProvider()
