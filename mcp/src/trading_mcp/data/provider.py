"""Centralized data provider with TTL cache.

Tutti i componenti (analyze_stock, bali, tsmom, lgbm) leggono da qui.
Il dato viene fetchato UNA SOLA VOLTA per ticker.

Ordine provider:
1. Cache (se fresco)
2. yfinance (sempre disponibile)
3. Alpha Vantage (enrichment, se chiave presente e non rate-limited)
4. FMP (fallback, se disponibile)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


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
    """Per-ticker cache holding hist, info, options, and optional stale copies."""

    hist: CacheEntry | None = None
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
        """Fetch OHLCV history with 1-hour TTL cache."""
        tc = self._ensure_ticker_cache(symbol)

        with tc.lock:
            entry = getattr(tc, "hist", None)
            if entry is not None and entry.is_fresh:
                logger.debug("Cache HIT: hist for %s (%.0fs old)",
                             symbol, entry.age_seconds)
                return entry.data

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
            tc.hist = CacheEntry(
                data=hist,
                timestamp=time.time(),
                ttl=self._ttl["hist"],
            )

        return hist

    def get_info(self, symbol: str) -> dict[str, Any]:
        """Fetch fundamental info with 6-hour TTL cache."""
        tc = self._ensure_ticker_cache(symbol)

        with tc.lock:
            entry = tc.info
            if entry is not None and entry.is_fresh:
                logger.debug("Cache HIT: info for %s (%.0fs old)",
                             symbol, entry.age_seconds)
                return entry.data.copy() if entry.data else {}

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
                for attr in ("hist", "info", "options_expirations"):
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
