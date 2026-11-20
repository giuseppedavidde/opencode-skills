"""Unit tests for the result cache (isolated in tmp_path, never the real cache)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from trading_mcp.data import result_cache as rc
from trading_mcp.data.result_cache import (
    MAX_ENTRIES,
    ResultCache,
    _canonicalize_params,
    _eod_seconds,
    _json_safe,
    _make_key,
    _resolve_ttl,
    is_cacheable,
)


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the module (and its singleton) at tmp_path for every test."""
    monkeypatch.setattr(rc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(rc, "CACHE_FILE", tmp_path / "result_cache.json")
    rc.result_cache.clear_all()
    yield
    rc.result_cache.clear_all()


@pytest.fixture()
def cache() -> ResultCache:
    return rc.result_cache


# ── canonicalization ───────────────────────────────────────────────

def test_canonicalize_excludes_verbose():
    result = _canonicalize_params({"ticker": "AAPL", "verbose": True, "score": 75})
    assert "verbose" not in result
    assert result == {"score": 75, "ticker": "AAPL"}


def test_canonicalize_keeps_fetch_news():
    """DATA-18: fetch_news changes the answer, so it stays in the key."""
    assert _canonicalize_params({"fetch_news": False})["fetch_news"] is False


def test_canonicalize_removes_none_and_sorts():
    result = _canonicalize_params({"z": 1, "a": None, "m": 3})
    assert list(result) == ["m", "z"]


def test_json_safe_complex_types():
    assert _json_safe({"a": [1, 2]}) == {"a": [1, 2]}
    assert _json_safe(42) == 42
    assert isinstance(_json_safe(object()), str)


# ── keys ───────────────────────────────────────────────────────────

def test_make_key_is_stable_and_normalizes_ticker():
    assert _make_key("analyze_stock", "aapl", {"x": 1}) == _make_key("analyze_stock", "AAPL", {"x": 1})


def test_make_key_differs_by_tool_and_expiry():
    assert _make_key("analyze_stock", "AAPL", {}) != _make_key("tsmom_signals", "AAPL", {})
    assert _make_key("fetch_options_chain", "AAPL", {"expiry": "2025-09-19"}) != _make_key(
        "fetch_options_chain", "AAPL", {"expiry": "2025-10-17"})


def test_make_key_separates_fetch_news():
    assert _make_key("analyze_stock", "AAPL", {"fetch_news": True}) != _make_key(
        "analyze_stock", "AAPL", {"fetch_news": False})


def test_make_key_ignores_verbose():
    assert _make_key("analyze_stock", "AAPL", {"verbose": True}) == _make_key(
        "analyze_stock", "AAPL", {"verbose": False})


def test_new_session_rotates_the_key():
    """DATA-10: the key follows the exchange session, not the UTC date."""
    assert _make_key("tsmom_signals", "AAPL", {}, session="2026-11-19") != _make_key(
        "tsmom_signals", "AAPL", {}, session="2026-11-20")


# ── TTLs ───────────────────────────────────────────────────────────

def test_resolve_ttl_fixed():
    assert _resolve_ttl("scan_market") == 30 * 60
    assert _resolve_ttl("analyze_stock") == 15 * 60
    assert _resolve_ttl("analyze_options") == 60


def test_session_ttl_ends_at_the_next_bar():
    seconds = _resolve_ttl("tsmom_signals", "AAPL")
    assert 60 <= seconds <= 86400


def test_eod_seconds_positive():
    assert 0 < _eod_seconds() <= 86400


# ── set / get ──────────────────────────────────────────────────────

def test_set_and_get_with_metadata(cache: ResultCache):
    assert cache.set("bali_signals", "AAPL", {"period": "1y"}, {"score": 75})
    hit = cache.get("bali_signals", "AAPL", {"period": "1y"})
    assert hit["score"] == 75
    assert hit["cached"] is True
    assert hit["cache_age_s"] >= 0
    assert hit["cached_at"].endswith("+00:00")


def test_hit_is_a_deep_copy(cache: ResultCache):
    cache.set("scan_market", "BATCH", {}, {"results": [{"ticker": "A"}]})
    hit = cache.get("scan_market", "BATCH", {})
    hit["results"][0]["ticker"] = "MUTATED"
    assert cache.get("scan_market", "BATCH", {})["results"][0]["ticker"] == "A"


def test_get_miss_unknown_key(cache: ResultCache):
    assert cache.get("analyze_stock", "MSFT", {}) is None


def test_fetch_news_false_never_answers_fetch_news_true(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {"fetch_news": False}, {"verdict": "Buy"})
    assert cache.get("analyze_stock", "AAPL", {"fetch_news": True}) is None
    assert cache.get("analyze_stock", "AAPL", {"fetch_news": False})["verdict"] == "Buy"


def test_verbose_does_not_split_entries(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {"verbose": True}, {"verdict": "Buy"})
    assert cache.get("analyze_stock", "AAPL", {"verbose": False})["verdict"] == "Buy"


@pytest.mark.parametrize("payload", [
    {"degraded": True, "results": []},
    {"error": "boom"},
    {"error": None, "error_kind": "blocking"},
])
def test_degraded_and_error_answers_are_never_stored(cache: ResultCache, payload: dict):
    assert not is_cacheable(payload)
    assert cache.set("scan_market", "BATCH", {}, payload) is False
    assert cache.get("scan_market", "BATCH", {}) is None
    assert cache.get_stats()["scan_market"]["refused"] == 1


def test_cache_metadata_is_not_stored_twice(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {}, {"x": 1, "cached": True, "cache_age_s": 99})
    stored = next(iter(cache._entries.values())).payload
    assert "cached" not in stored and "cache_age_s" not in stored


def test_ttl_expired(cache: ResultCache):
    cache.set("fetch_options_chain", "AAPL", {}, {"chain": "data"})
    for entry in cache._entries.values():
        entry.ts_created = time.time() - 3600
        entry.ttl_seconds = 1
    assert cache.get("fetch_options_chain", "AAPL", {}) is None


def test_ttl_override(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {}, {"score": 95}, ttl_override=10)
    assert cache.get("analyze_stock", "AAPL", {}) is not None
    for entry in cache._entries.values():
        entry.ts_created = time.time() - 20
    assert cache.get("analyze_stock", "AAPL", {}) is None


def test_invalidate_by_ticker(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {}, {"a": 1})
    cache.set("analyze_stock", "MSFT", {}, {"a": 2})
    assert cache.invalidate(ticker="aapl") == 1
    assert cache.get("analyze_stock", "AAPL", {}) is None
    assert cache.get("analyze_stock", "MSFT", {}) is not None


def test_lru_eviction(cache: ResultCache):
    start = time.time()
    for i in range(MAX_ENTRIES + 50):
        cache._entries[f"key_{i:04d}"] = rc.ResultCacheEntry(
            key=f"key_{i:04d}", ts_created=start, ttl_seconds=3600,
            payload={"data": i}, last_access=start - (MAX_ENTRIES + 50 - i),
        )
    cache._evict_lru()
    assert len(cache._entries) == MAX_ENTRIES
    assert "key_0000" not in cache._entries
    assert f"key_{MAX_ENTRIES + 49:04d}" in cache._entries


# ── persistence ────────────────────────────────────────────────────

def test_persist_and_reload(cache: ResultCache):
    cache.set("bali_signals", "AAPL", {"period": "1y"}, {"score": 80})
    cache._flush_pending()
    assert rc.CACHE_FILE.exists()
    assert rc.CACHE_FILE.stat().st_mode & 0o777 == 0o600
    reloaded = ResultCache()
    hit = reloaded.get("bali_signals", "AAPL", {"period": "1y"})
    assert hit is not None
    assert hit["score"] == 80


def test_debounce_timer_rearms_after_flush(cache: ResultCache, monkeypatch: pytest.MonkeyPatch):
    """DATA-18: writes after the first flush still reach the disk."""
    monkeypatch.setattr(rc, "_SAVE_DEBOUNCE_SECONDS", 0.05)
    cache.set("bali_signals", "AAA", {}, {"n": 1})
    time.sleep(0.4)
    cache.set("bali_signals", "BBB", {}, {"n": 2})
    time.sleep(0.4)
    reloaded = ResultCache()
    assert reloaded.get("bali_signals", "AAA", {}) is not None
    assert reloaded.get("bali_signals", "BBB", {}) is not None


def test_corrupted_file_recovery(cache: ResultCache):
    rc.CACHE_FILE.write_text("{this is not valid json!!!", encoding="utf-8")
    rc.CACHE_FILE.chmod(0o600)
    assert len(ResultCache()._entries) == 0
    cache.clear_all()
    assert not rc.CACHE_FILE.exists()


def test_foreign_file_is_ignored(cache: ResultCache, monkeypatch: pytest.MonkeyPatch):
    cache.set("bali_signals", "AAPL", {}, {"score": 1})
    cache._flush_pending()
    rc.CACHE_FILE.chmod(0o666)
    assert ResultCache().get("bali_signals", "AAPL", {}) is None


def test_stats_hit_miss(cache: ResultCache):
    cache.set("analyze_stock", "AAPL", {}, {"score": 90})
    cache.get("analyze_stock", "AAPL", {})
    cache.get("analyze_stock", "MSFT", {})
    stats = cache.get_stats()["analyze_stock"]
    assert (stats["hits"], stats["misses"], stats["hit_rate"]) == (1, 1, 50.0)
