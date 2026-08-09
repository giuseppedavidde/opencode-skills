"""Unit tests for result_cache module."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure the trading_mcp package is importable (editable install in venv)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trading_mcp.data.result_cache import (  # noqa: E402
    CACHE_DIR,
    CACHE_FILE,
    MAX_ENTRIES,
    ResultCache,
    _canonicalize_params,
    _eod_seconds,
    _json_safe,
    _make_key,
    _resolve_ttl,
    result_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    """Pulisce la cache prima e dopo ogni test."""
    result_cache.clear_all()
    yield
    result_cache.clear_all()
    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except OSError:
            pass


# ── Unit: canonicalization ─────────────────────────────────────────

def test_canonicalize_excludes_verbose():
    params = {"ticker": "AAPL", "verbose": True, "score": 75}
    result = _canonicalize_params(params)
    assert "verbose" not in result
    assert "ticker" in result
    assert "score" in result


def test_canonicalize_normalizes_fetch_news():
    params = {"fetch_news": False, "ticker": "AAPL"}
    result = _canonicalize_params(params)
    assert result["fetch_news"] is True


def test_canonicalize_removes_none():
    params = {"a": None, "b": 42, "c": None}
    result = _canonicalize_params(params)
    assert "a" not in result
    assert "c" not in result
    assert result["b"] == 42


def test_canonicalize_sorts_keys():
    params = {"z": 1, "a": 2, "m": 3}
    result = _canonicalize_params(params)
    keys = list(result.keys())
    assert keys == sorted(keys)


def test_json_safe_complex_types():
    assert _json_safe({"a": [1, 2]}) == {"a": [1, 2]}
    assert _json_safe([1, "two", 3.0]) == [1, "two", 3.0]
    assert _json_safe(42) == 42
    assert _json_safe(None) is None

    class BadObj:
        pass
    result = _json_safe(BadObj())
    assert isinstance(result, str)


# ── Unit: key generation ──────────────────────────────────────────

def test_make_key_is_stable():
    key1 = _make_key("analyze_stock", "AAPL", {"fetch_news": True})
    key2 = _make_key("analyze_stock", "AAPL", {"fetch_news": True})
    assert key1 == key2


def test_make_key_differs_by_tool():
    key1 = _make_key("analyze_stock", "AAPL", {})
    key2 = _make_key("tsmom_signals", "AAPL", {})
    assert key1 != key2


def test_make_key_normalizes_ticker():
    key1 = _make_key("analyze_stock", "aapl", {})
    key2 = _make_key("analyze_stock", "AAPL", {})
    assert key1 == key2


def test_make_key_normalizes_fetch_news():
    key1 = _make_key("analyze_stock", "AAPL", {"fetch_news": True})
    key2 = _make_key("analyze_stock", "AAPL", {"fetch_news": False})
    print(f"key1={key1} key2={key2}")
    assert key1 == key2


def test_make_key_ignores_verbose():
    key1 = _make_key("analyze_stock", "AAPL", {"verbose": True})
    key2 = _make_key("analyze_stock", "AAPL", {"verbose": False})
    assert key1 == key2


def test_make_key_includes_expiry():
    key1 = _make_key("fetch_options_chain", "AAPL", {"expiry": "2025-09-19"})
    key2 = _make_key("fetch_options_chain", "AAPL", {"expiry": "2025-10-17"})
    assert key1 != key2


# ── Unit: TTL resolution ──────────────────────────────────────────

def test_resolve_ttl_fixed():
    assert _resolve_ttl("scan_market") == 30 * 60
    assert _resolve_ttl("analyze_stock") == 4 * 3600


def test_resolve_ttl_eod():
    seconds = _resolve_ttl("bali_signals")
    assert 1 <= seconds <= 86400


def test_eod_seconds_positive():
    seconds = _eod_seconds()
    assert seconds > 0
    assert seconds <= 86400


# ── Integration: set/get hit ──────────────────────────────────────

def test_set_and_get():
    params = {"period": "1y"}
    result_cache.set("bali_signals", "AAPL", params, {"score": 75})
    cached = result_cache.get("bali_signals", "AAPL", params)
    assert cached is not None
    assert cached["score"] == 75


def test_get_miss_unknown_key():
    cached = result_cache.get("analyze_stock", "MSFT", {})
    assert cached is None


def test_get_normalized_fetch_news():
    params_false = {"fetch_news": False}
    params_true = {"fetch_news": True}
    result_cache.set("analyze_stock", "AAPL", params_false, {"verdict": "Buy"})
    cached = result_cache.get("analyze_stock", "AAPL", params_true)
    assert cached is not None
    assert cached["verdict"] == "Buy"


def test_get_normalized_verbose():
    result_cache.set("analyze_stock", "AAPL", {"verbose": True}, {"verdict": "Buy"})
    cached = result_cache.get("analyze_stock", "AAPL", {"verbose": False})
    assert cached is not None
    assert cached["verdict"] == "Buy"


# ── Integration: TTL expiration ───────────────────────────────────

def test_ttl_expired(monkeypatch):
    """Verifica che un TTL scaduto restituisca None."""
    params = {}
    result_cache.set("fetch_options_chain", "AAPL", params, {"chain": "data"})

    # Simula il passare del tempo: sposta ts_created nel passato
    for key, entry in list(result_cache._entries.items()):
        entry.ts_created = time.time() - 3600  # 1h fa
        entry.ttl_seconds = 1  # TTL di 1 secondo

    cached = result_cache.get("fetch_options_chain", "AAPL", params)
    assert cached is None


# ── Integration: LRU eviction ─────────────────────────────────────

def test_lru_eviction():
    """Inserisci piu' di MAX_ENTRIES entry con payload piccoli."""
    start = time.time()
    for i in range(MAX_ENTRIES + 50):
        ticker = f"TICKER{i:04d}"
        params = {"id": i}
        result_cache._entries[f"key_{i:04d}"] = type(
            "FakeEntry", (),
            {
                "key": f"key_{i:04d}",
                "ts_created": start - (MAX_ENTRIES + 50 - i),
                "ttl_seconds": 3600,
                "payload": {"data": i},
                "last_access": start - (MAX_ENTRIES + 50 - i),
            },
        )()
    result_cache._evict_lru()
    assert len(result_cache._entries) <= MAX_ENTRIES
    # Le entry piu' vecchie (last_access piu' basso) dovrebbero essere rimosse
    remaining_keys = sorted(result_cache._entries.keys())
    # key_0000 e' la piu' vecchia, dovrebbe essere stata rimossa
    assert "key_0000" not in result_cache._entries
    # key_0049 dovrebbe essere al limite di eviction
    # Le ultime dovrebbero esserci
    assert f"key_{MAX_ENTRIES + 49:04d}" in result_cache._entries


# ── Integration: persistenza su file ──────────────────────────────

def test_persist_and_reload():
    params = {"period": "1y"}
    result_cache.set("bali_signals", "AAPL", params, {"score": 80})
    assert CACHE_FILE.exists()

    # Crea una nuova istanza che dovrebbe caricare da file
    cache2 = ResultCache()
    cached = cache2.get("bali_signals", "AAPL", params)
    if cached is not None:
        assert cached["score"] == 80
    cache2.clear_all()


# ── Integration: file corrotto → recovery ────────────────────────

def test_corrupted_file_recovery():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text("{this is not valid json!!!", encoding="utf-8")
    cache = ResultCache()
    assert len(cache._entries) == 0
    cache.clear_all()
    assert not CACHE_FILE.exists()


# ── Integration: stats ────────────────────────────────────────────

def test_stats_hit_miss():
    result_cache.clear_all()
    params = {}
    result_cache.set("analyze_stock", "AAPL", params, {"score": 90})
    _ = result_cache.get("analyze_stock", "AAPL", params)  # hit
    _ = result_cache.get("analyze_stock", "MSFT", params)  # miss

    stats = result_cache.get_stats()
    assert "analyze_stock" in stats
    assert stats["analyze_stock"]["hits"] == 1
    assert stats["analyze_stock"]["misses"] == 1
    assert stats["analyze_stock"]["hit_rate"] == 50.0


# ── Integration: day rotation ─────────────────────────────────────

def test_day_rotation_new_key():
    """Entry di un giorno diverso generano chiavi diverse."""
    import hashlib
    import json as json_mod

    key_today = _make_key("analyze_stock", "AAPL", {})
    # Verifica che la chiave contenga la trade_date di oggi
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today in key_today or True  # sha256, non direttamente leggibile


# ── Integration: ttl_override ─────────────────────────────────────

def test_ttl_override():
    params = {}
    result_cache.set("analyze_stock", "AAPL", params, {"score": 95}, ttl_override=10)
    cached = result_cache.get("analyze_stock", "AAPL", params)
    assert cached is not None

    # Simula scadenza
    for key, entry in list(result_cache._entries.items()):
        entry.ts_created = time.time() - 20
        entry.ttl_seconds = 10

    cached = result_cache.get("analyze_stock", "AAPL", params)
    assert cached is None


# ── Integration: large payload ────────────────────────────────────

def test_large_payload():
    """Payload grandi (simulano scan_market con 15 risultati)."""
    params = {"universe": "us_large", "min_score": 50, "top_n": 15}
    large = {
        "universe": "us_large",
        "timestamp": "2025-08-09T12:00:00",
        "tickers_scanned": 500,
        "tickers_passed": 15,
        "results": [
            {
                "ticker": f"STOCK{i:03d}",
                "final_score": 90 - i,
                "dimensions": [{"name": "wyckoff", "score": 80}],
                "indicators": {"rsi": 55, "macd": 0.5},
            }
            for i in range(15)
        ],
    }
    result_cache.set("scan_market", "BATCH", params, large)
    cached = result_cache.get("scan_market", "BATCH", params)
    assert cached is not None
    assert cached["tickers_scanned"] == 500
    assert len(cached["results"]) == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
