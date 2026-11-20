"""Result cache for trading MCP tools: "compile once, execute cheap".

Stores the FINAL answers of expensive analyses. Rules:

- The key is ``(tool, ticker, canonical params, session)``. ``session`` is the
  last complete trading session of the ticker's exchange (US for batch
  keys), so a new daily bar always rotates the key (DATA-10).
- ``verbose`` is not part of the key (it only filters the answer).
  ``fetch_news`` IS part of the key: an answer computed without news never
  answers a call that asked for news (DATA-18).
- Degraded or failed answers are never stored (``degraded``, ``error`` or
  ``error_kind`` set).
- A hit returns a deep copy with ``cached=True``, ``cache_age_s`` and
  ``cached_at``; ``computed_at`` and ``as_of`` stay those of the original
  computation.
- TTLs are per tool; ``"SESSION"`` means "until the next daily bar of the
  ticker's exchange is final".
- Persistence: one JSON file in the private cache directory
  (``TRADING_RESULT_CACHE_DIR`` or ``$XDG_CACHE_HOME/trading_mcp``), written
  atomically by a debounced timer that is re-armed after every flush.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data import market_calendar as mcal
from trading_mcp.data.cache_paths import atomic_write_json, cache_root, read_json, secure_dir
from trading_mcp.timeutil import iso, from_epoch

logger = logging.getLogger(__name__)


def _resolve_cache_dir() -> Path | None:
    """``TRADING_RESULT_CACHE_DIR`` or the private application cache root."""
    env_dir = os.environ.get("TRADING_RESULT_CACHE_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser()
    return cache_root()


CACHE_DIR: Path | None = _resolve_cache_dir()
CACHE_FILE: Path | None = CACHE_DIR / "result_cache.json" if CACHE_DIR is not None else None
MAX_ENTRIES = 500

# Debounced write batching: one fsync per burst of ``set`` calls.
_SAVE_DEBOUNCE_SECONDS = 2.0

SESSION_TTL = "SESSION"
_MIN_SESSION_TTL = 60
_MAX_SESSION_TTL = 24 * 3600

TTL_CONFIG: dict[str, int | str] = {
    "analyze_stock": 15 * 60,          # daily-bar analysis plus a live quote
    "analyze_options": 60,             # spot and marks must stay within 60 s
    "fetch_options_chain": 5 * 60,     # intraday chain
    "gex_analysis": 5 * 60,            # derived from the intraday chain
    "bali_signals": 5 * 60,            # uses intraday option IV
    "tsmom_signals": SESSION_TTL,      # complete daily bars only
    "breakout_context": 15 * 60,       # daily bars plus an intraday GEX overlay
    "suggest_options_strategy": 4 * 3600,
    "scan_market": 30 * 60,            # expensive; degraded scans are never stored
}

_META_KEYS = ("cached", "cache_age_s", "cached_at")


def _eod_seconds() -> int:
    """Seconds to the next 00:00 UTC (legacy helper, kept for callers)."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, int((midnight - now).total_seconds()))


def _session_exchange(ticker: str) -> str:
    return "US" if not ticker or ticker.upper() == "BATCH" else ticker


def _session_key(ticker: str) -> str:
    """Last complete session of the ticker's exchange (ISO date)."""
    return mcal.last_complete_session_date(_session_exchange(ticker)).isoformat()


def _session_seconds(ticker: str) -> int:
    """Seconds until the next daily bar of the ticker's exchange is final."""
    exchange = _session_exchange(ticker)
    nxt = mcal.next_bar_complete_after(exchange)
    seconds = int((nxt - datetime.now(timezone.utc)).total_seconds())
    return max(_MIN_SESSION_TTL, min(_MAX_SESSION_TTL, seconds))


def _resolve_ttl(tool: str, ticker: str = "BATCH") -> int:
    """TTL in seconds for ``tool``; ``SESSION`` (or legacy ``EOD``) follows the exchange."""
    ttl = TTL_CONFIG.get(tool, 3600)
    if ttl in (SESSION_TTL, "EOD"):
        return _session_seconds(ticker)
    return int(ttl)


class ResultCacheEntry(BaseModel):
    """One cached answer (JSON-serializable payload)."""

    key: str
    ts_created: float
    ttl_seconds: int
    payload: Any
    last_access: float = Field(default_factory=time.time)
    tool: str | None = None
    ticker: str | None = None
    session: str | None = None


def _canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Canonical params: no ``verbose``, no ``None`` values, sorted keys, JSON values."""
    out: dict[str, Any] = {}
    for key in sorted(params.keys()):
        if key == "verbose":
            continue
        val = params[key]
        if val is None:
            continue
        out[key] = _json_safe(val)
    return out


def _json_safe(val: Any) -> Any:
    """Convert a value into a JSON-serializable one."""
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    if isinstance(val, (list, tuple, dict)):
        return json.loads(json.dumps(val, default=str, sort_keys=True))
    return str(val)


def _make_key(tool: str, ticker: str, params: dict[str, Any], session: str | None = None) -> str:
    """SHA-256 key of ``(tool, ticker, params, session)``."""
    canonical = {
        "tool": tool,
        "ticker": ticker.upper().strip(),
        "params": _canonicalize_params(params),
        "session": session if session is not None else _session_key(ticker),
    }
    raw = json.dumps(canonical, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_cacheable(payload: Any) -> bool:
    """False for degraded or failed answers (they must be recomputed)."""
    if not isinstance(payload, dict):
        return payload is not None
    if payload.get("degraded") is True:
        return False
    if payload.get("error") or payload.get("error_kind"):
        return False
    return True


class ResultCache:
    """Persistent LRU cache with atomic, debounced writes; thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, ResultCacheEntry] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._save_timer: threading.Timer | None = None
        self._dirty: bool = False
        self._load()

    # ── persistence ───────────────────────────────────────────────

    @staticmethod
    def _directory() -> Path | None:
        if CACHE_DIR is None:
            return None
        return secure_dir(Path(CACHE_DIR))

    def _load(self) -> None:
        """Load the cache file; a corrupt or foreign file gives an empty cache."""
        if self._directory() is None or CACHE_FILE is None:
            return
        raw = read_json(Path(CACHE_FILE))
        if not isinstance(raw, dict):
            return
        now = time.time()
        for key, data in raw.items():
            try:
                entry = ResultCacheEntry.model_validate(data)
            except (ValueError, TypeError):
                continue
            if now - entry.ts_created <= entry.ttl_seconds:
                self._entries[key] = entry

    def _save(self) -> None:
        """Write the dirty cache atomically; re-arm the debounce timer."""
        with self._lock:
            self._save_timer = None
            if not self._dirty:
                return
            data = {key: entry.model_dump() for key, entry in self._entries.items()}
            self._dirty = False
        if self._directory() is None or CACHE_FILE is None:
            return
        if not atomic_write_json(Path(CACHE_FILE), data, default=str):
            with self._lock:
                self._dirty = True

    def _schedule_save(self) -> None:
        """Arm one debounced save for a burst of writes."""
        with self._lock:
            self._dirty = True
            if self._save_timer is not None:
                return
            timer = threading.Timer(_SAVE_DEBOUNCE_SECONDS, self._save)
            timer.daemon = True
            self._save_timer = timer
            timer.start()

    def _flush_pending(self) -> None:
        """Synchronous flush (clear_all, shutdown, tests)."""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
        self._save()

    # ── eviction ──────────────────────────────────────────────────

    def _evict_lru(self) -> None:
        """Drop the least recently used entries above MAX_ENTRIES."""
        if len(self._entries) <= MAX_ENTRIES:
            return
        ordered = sorted(self._entries.items(), key=lambda item: item[1].last_access)
        for key, _ in ordered[: len(self._entries) - MAX_ENTRIES]:
            del self._entries[key]

    def _evict_expired(self) -> None:
        """Drop expired entries from memory."""
        now = time.time()
        for key in [k for k, e in self._entries.items() if now - e.ts_created > e.ttl_seconds]:
            del self._entries[key]

    # ── statistics ────────────────────────────────────────────────

    def _record(self, tool: str, field_name: str) -> None:
        stats = self._stats.setdefault(tool, {"hits": 0, "misses": 0, "refused": 0})
        stats[field_name] = stats.get(field_name, 0) + 1

    # ── public API ────────────────────────────────────────────────

    def get(self, tool: str, ticker: str, params: dict[str, Any]) -> Any | None:
        """Return a copy of a live answer with cache metadata, or ``None``."""
        key = _make_key(tool, ticker, params)
        with self._lock:
            entry = self._entries.get(key)
            now = time.time()
            if entry is None or now - entry.ts_created > entry.ttl_seconds:
                if entry is not None:
                    del self._entries[key]
                self._evict_expired()
                self._record(tool, "misses")
                logger.debug("result-cache MISS tool=%s ticker=%s", tool, ticker.upper())
                return None
            entry.last_access = now
            self._record(tool, "hits")
            payload = copy.deepcopy(entry.payload)
            created = entry.ts_created
        logger.debug("result-cache HIT tool=%s ticker=%s", tool, ticker.upper())
        if isinstance(payload, dict):
            payload.update(
                cached=True,
                cache_age_s=round(now - created, 3),
                cached_at=iso(from_epoch(created)),
            )
        return payload

    def set(
        self,
        tool: str,
        ticker: str,
        params: dict[str, Any],
        payload: Any,
        ttl_override: int | None = None,
    ) -> bool:
        """Store an answer; returns False when the answer is not cacheable."""
        if not is_cacheable(payload):
            with self._lock:
                self._record(tool, "refused")
            return False
        session = _session_key(ticker)
        key = _make_key(tool, ticker, params, session)
        ttl = ttl_override if ttl_override is not None else _resolve_ttl(tool, ticker)
        stored = copy.deepcopy(payload)
        if isinstance(stored, dict):
            for meta_key in _META_KEYS:
                stored.pop(meta_key, None)
        now = time.time()
        entry = ResultCacheEntry(
            key=key, ts_created=now, ttl_seconds=int(ttl), payload=stored, last_access=now,
            tool=tool, ticker=ticker.upper().strip(), session=session,
        )
        with self._lock:
            self._evict_expired()
            self._entries[key] = entry
            self._evict_lru()
        self._schedule_save()
        return True

    def invalidate(self, tool: str | None = None, ticker: str | None = None) -> int:
        """Drop entries of one tool and/or ticker; returns how many."""
        symbol = ticker.upper().strip() if ticker else None
        with self._lock:
            doomed = [
                key for key, entry in self._entries.items()
                if (tool is None or entry.tool == tool) and (symbol is None or entry.ticker == symbol)
            ]
            for key in doomed:
                del self._entries[key]
        if doomed:
            self._schedule_save()
        return len(doomed)

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Hit, miss and refusal counters per tool."""
        with self._lock:
            result: dict[str, dict[str, Any]] = {}
            for tool, stats in self._stats.items():
                total = stats.get("hits", 0) + stats.get("misses", 0)
                result[tool] = {
                    "hits": stats.get("hits", 0),
                    "misses": stats.get("misses", 0),
                    "refused": stats.get("refused", 0),
                    "hit_rate": round(stats.get("hits", 0) / total * 100, 1) if total else 0.0,
                }
            return result

    def clear_all(self) -> None:
        """Empty the cache in memory and on disk."""
        with self._lock:
            self._entries.clear()
            self._stats.clear()
            self._dirty = False
        self._flush_pending()
        if CACHE_FILE is not None and Path(CACHE_FILE).exists():
            try:
                Path(CACHE_FILE).unlink()
            except OSError:
                pass


# ── Singleton ─────────────────────────────────────────────────────────
result_cache = ResultCache()
