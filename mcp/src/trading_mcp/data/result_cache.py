"""Result cache for trading MCP tools — "compile once, execute cheap".

Memoizza i risultati FINALI delle analisi costose (verdict, payoff, scan
ranking). Le entry sono indicizzate per (tool, ticker, params_canonicalizzati,
trade_date). Cache persistente su file JSON in ~/.cache/trading_mcp/.

Politica di normalizzazione parametri:
  - ``verbose`` e' SEMPRE escluso dalla cache key (il contenuto core non cambia).
  - ``fetch_news`` e' normalizzato a True (l'analisi core e' invariante;
    fetch_news=False restituisce output meno ricco ma la cache da' il risultato
    piu' completo disponibile, che e' accettabile).
  - Le chiavi sono ordinate alfabeticamente; i valori sono serializzati in JSON.
  - trade_date (YYYY-MM-DD UTC) e' incluso nella chiave per rotazione giornaliera.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pydantic import BaseModel, Field

CACHE_DIR = Path.home() / ".cache" / "trading_mcp"
CACHE_FILE = CACHE_DIR / "result_cache.json"
MAX_ENTRIES = 500

# ── TTL configurabile per tool ───────────────────────────────────────
# I TTL sono definiti qui; "EOD" = secondi fino a fine giornata UTC.

TTL_CONFIG: dict[str, int | str] = {
    "analyze_stock": 4 * 3600,       # 4h — analisi completa, dati daily
    "analyze_options": 4 * 3600,      # 4h — payoff e greche non cambiano
                                       #       in poche ore per posizioni
                                       #       multi-leg standard
    "fetch_options_chain": 5 * 60,    # 5min — prezzi intraday, catena opzioni
                                       #        cambia rapidamente
    "bali_signals": "EOD",            # fino a mezzanotte — volatility spread
                                       # basato su RV daily, non cambia intraday
    "tsmom_signals": "EOD",           # fino a mezzanotte — momentum su daily,
                                       # invariante nella stessa giornata
    "suggest_options_strategy": 4 * 3600,  # 4h — strategia deriva da verdict
                                           #       e IV rank, cambio lento
    "scan_market": 30 * 60,           # 30min — costo elevato (500 ticker in
                                       #         ~45s), ma dati intraday.
                                       #         Bilanciamento freschezza/costo.
    "lgbm_predict": "EOD",            # fino a mezzanotte — score ML su feature
                                       # daily, non ricalcolabile senza modello
}


def _eod_seconds() -> int:
    """Calcola i secondi rimanenti fino alla mezzanotte UTC."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, int((midnight - now).total_seconds()))


def _resolve_ttl(tool: str) -> int:
    """Risolve il TTL per un tool. 'EOD' diventa secondi fino a mezzanotte UTC."""
    ttl = TTL_CONFIG.get(tool, 3600)
    if ttl == "EOD":
        return _eod_seconds()
    return int(ttl)


class ResultCacheEntry(BaseModel):
    """Entry nella result cache. Payload JSON-serializzabile."""
    key: str
    ts_created: float
    ttl_seconds: int
    payload: Any
    last_access: float = Field(default_factory=time.time)


def _canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Normalizza i parametri per la cache key.

    - Esclude ``verbose`` (non cambia il contenuto core).
    - Normalizza ``fetch_news`` a True.
    - Rimuove None.
    - Ordina le chiavi.
    - Serializza valori complessi in JSON.
    """
    out: dict[str, Any] = {}
    for key in sorted(params.keys()):
        if key == "verbose":
            continue
        val = params[key]
        if key == "fetch_news":
            val = True
        if val is None:
            continue
        out[key] = _json_safe(val)
    return out


def _json_safe(val: Any) -> Any:
    """Converte un valore in formato JSON-serializzabile."""
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    if isinstance(val, (list, tuple, dict)):
        return json.loads(json.dumps(val, default=str, sort_keys=True))
    return str(val)


def _make_key(tool: str, ticker: str, params: dict[str, Any]) -> str:
    """Genera una chiave SHA-256 per la cache entry."""
    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    canonical = {
        "tool": tool,
        "ticker": ticker.upper().strip(),
        "params": _canonicalize_params(params),
        "trade_date": trade_date,
    }
    raw = json.dumps(canonical, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResultCache:
    """Cache persistente con eviction LRU, scritture atomiche, thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, ResultCacheEntry] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._load()

    # ── Persistenza ───────────────────────────────────────────────

    def _load(self) -> None:
        """Carica la cache da file. Se corrotto, inizializza vuoto."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not CACHE_FILE.exists():
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("Cache file non e' un dizionario JSON")
            self._entries = {}
            for key, data in raw.items():
                try:
                    entry = ResultCacheEntry.model_validate(data)
                    if time.time() - entry.ts_created <= entry.ttl_seconds:
                        self._entries[key] = entry
                except (ValueError, TypeError):
                    continue
        except (json.JSONDecodeError, ValueError, OSError):
            # File corrotto → inizializza vuoto senza crashare
            self._entries = {}

    def _save(self) -> None:
        """Salva la cache su file con scrittura atomica (temp + rename)."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {key: entry.model_dump() for key, entry in self._entries.items()}
        tmp_fd = None
        tmp_path = None
        try:
            # pylint: disable=consider-using-with
            tmp_fd = NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(CACHE_DIR),
                delete=False,
                suffix=".tmp",
            )
            tmp_path = tmp_fd.name
            json.dump(data, tmp_fd, default=str, ensure_ascii=False)
            tmp_fd.flush()
            os.fsync(tmp_fd.fileno())
            tmp_fd.close()
            tmp_fd = None
            os.replace(tmp_path, str(CACHE_FILE))
        finally:
            if tmp_fd is not None:
                try:
                    tmp_fd.close()
                except OSError:
                    pass
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    # ── Eviction LRU ──────────────────────────────────────────────

    def _evict_lru(self) -> None:
        """Rimuove le entry meno recentemente usate se superano MAX_ENTRIES."""
        if len(self._entries) <= MAX_ENTRIES:
            return
        sorted_entries = sorted(
            self._entries.items(),
            key=lambda item: item[1].last_access,
        )
        to_remove = len(self._entries) - MAX_ENTRIES
        for key, _ in sorted_entries[:to_remove]:
            del self._entries[key]

    # ── Garbage collection ────────────────────────────────────────

    def _evict_expired(self) -> None:
        """Rimuove entry scadute dal dizionario in-memory."""
        now = time.time()
        expired = [
            key for key, entry in self._entries.items()
            if now - entry.ts_created > entry.ttl_seconds
        ]
        for key in expired:
            del self._entries[key]

    # ── Statistiche ───────────────────────────────────────────────

    def _record_hit(self, tool: str) -> None:
        """Registra un cache hit nelle statistiche."""
        if tool not in self._stats:
            self._stats[tool] = {"hits": 0, "misses": 0}
        self._stats[tool]["hits"] += 1

    def _record_miss(self, tool: str) -> None:
        """Registra un cache miss nelle statistiche."""
        if tool not in self._stats:
            self._stats[tool] = {"hits": 0, "misses": 0}
        self._stats[tool]["misses"] += 1

    # ── API pubblica ──────────────────────────────────────────────

    def get(self, tool: str, ticker: str, params: dict[str, Any]) -> Any | None:
        """Cerca un risultato nella cache. Restituisce None se miss o scaduto."""
        key = _make_key(tool, ticker, params)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._evict_expired()
                self._record_miss(tool)
                sys.stderr.write(
                    f"[result-cache] MISS tool={tool} ticker={ticker.upper()}\n"
                )
                sys.stderr.flush()
                return None

            now = time.time()
            if now - entry.ts_created > entry.ttl_seconds:
                del self._entries[key]
                self._record_miss(tool)
                sys.stderr.write(
                    f"[result-cache] MISS (expired) tool={tool} ticker={ticker.upper()}\n"
                )
                sys.stderr.flush()
                return None

            entry.last_access = now
            self._record_hit(tool)
            sys.stderr.write(
                f"[result-cache] HIT tool={tool} ticker={ticker.upper()}\n"
            )
            sys.stderr.flush()
            return entry.payload

    def set(
        self,
        tool: str,
        ticker: str,
        params: dict[str, Any],
        payload: Any,
        ttl_override: int | None = None,
    ) -> None:
        """Salva un risultato nella cache."""
        key = _make_key(tool, ticker, params)
        ttl = ttl_override if ttl_override is not None else _resolve_ttl(tool)
        now = time.time()
        entry = ResultCacheEntry(
            key=key,
            ts_created=now,
            ttl_seconds=ttl,
            payload=payload,
            last_access=now,
        )
        with self._lock:
            self._evict_expired()
            self._entries[key] = entry
            self._evict_lru()
            self._save()

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Restituisce le statistiche hit/miss per tool."""
        with self._lock:
            result: dict[str, dict[str, Any]] = {}
            for tool, stats in self._stats.items():
                total = stats["hits"] + stats["misses"]
                hit_rate = round(stats["hits"] / total * 100, 1) if total > 0 else 0.0
                result[tool] = {
                    "hits": stats["hits"],
                    "misses": stats["misses"],
                    "hit_rate": hit_rate,
                }
            return result

    def clear_all(self) -> None:
        """Svuota la cache (in-memory e su file). Non chiamata automaticamente."""
        with self._lock:
            self._entries.clear()
            self._stats.clear()
            if CACHE_FILE.exists():
                try:
                    CACHE_FILE.unlink()
                except OSError:
                    pass


# ── Singleton ─────────────────────────────────────────────────────────
result_cache = ResultCache()
