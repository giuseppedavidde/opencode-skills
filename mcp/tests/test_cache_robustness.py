"""Robustness tests: atomic cache writes and defensive corruption handling.

Verifica che le cache condivise (options_chain, provider, result_cache)
scrivano in modo atomico e sopravvivano a file corrotti/parziali senza
far crashare i tool, anche con processi paralleli.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trading_mcp.data import options_chain as oc  # noqa: E402
from trading_mcp.data import provider as prov  # noqa: E402
from trading_mcp.data.result_cache import (  # noqa: E402
    CACHE_FILE,
    ResultCache,
)


# ── options_chain: atomic write + corrupt read ─────────────────────────

def test_options_save_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_save_cached_chain non lascia file temporanei e scrive JSON valido."""
    monkeypatch.setattr(oc, "_CACHE_DIR", tmp_path)
    oc._MEM_CACHE.clear()
    oc._MEM_CACHE_TIMES.clear()

    oc._save_cached_chain("TESTX", "2026-01-16", {"_source": "live", "rows": [1, 2]})

    cache_file = tmp_path / "TESTX_2026-01-16.json"
    assert cache_file.exists()
    payload = json.loads(cache_file.read_text())
    assert payload["_source"] == "live"
    assert payload["_cached_at"]
    # Nessun file temporaneo residuo
    assert list(tmp_path.glob(".*tmp")) == []


def test_options_corrupt_read_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un file corrotto non fa crashare la lettura: ritorna None (miss)."""
    monkeypatch.setattr(oc, "_CACHE_DIR", tmp_path)
    oc._MEM_CACHE.clear()
    oc._MEM_CACHE_TIMES.clear()

    (tmp_path / "CORRUPT_auto.json").write_text("{ this is not json")

    assert oc._load_cached_chain("CORRUPT", None) is None


def test_options_partial_json_read_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON troncato a metà (scrittura concorrente) → miss, non eccezione."""
    monkeypatch.setattr(oc, "_CACHE_DIR", tmp_path)
    oc._MEM_CACHE.clear()
    oc._MEM_CACHE_TIMES.clear()

    (tmp_path / "PARTIAL_auto.json").write_text('{"_cached_at": "2026-01-01", "rows": [1,')

    assert oc._load_cached_chain("PARTIAL", None) is None


def test_options_roundtrip_after_atomic_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dopo save atomico, la lettura (memoria svuotata) ritrova i dati."""
    monkeypatch.setattr(oc, "_CACHE_DIR", tmp_path)
    oc._MEM_CACHE.clear()
    oc._MEM_CACHE_TIMES.clear()

    oc._save_cached_chain("RT", None, {"_source": "live", "n": 3})
    oc._MEM_CACHE.clear()
    oc._MEM_CACHE_TIMES.clear()

    loaded = oc._load_cached_chain("RT", None)
    assert loaded is not None
    assert loaded["n"] == 3


# ── provider: atomic JSON write + corrupt read (no pickle) ─────────────

def _entry() -> prov.CacheEntry:
    return prov.CacheEntry(data=None, fetched_at=1_700_000_000.0, ttl=60.0, source="test")


def test_provider_save_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_disk_save writes one private JSON file atomically, with no temp file left."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)

    prov._disk_save("hist", "AAPL", "hist:AAPL:1y:1d", _entry(), {"close": [1.0, 2.0]})

    files = list(tmp_path.glob("hist_AAPL_*.json"))
    assert len(files) == 1
    assert list(tmp_path.glob(".*tmp")) == []
    assert files[0].stat().st_mode & 0o777 == 0o600

    loaded = prov._disk_load("hist", "AAPL", "hist:AAPL:1y:1d")
    assert loaded is not None
    assert loaded["payload"] == {"close": [1.0, 2.0]}
    assert loaded["fetched_at"] == 1_700_000_000.0


def test_provider_corrupt_json_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A corrupt cache file is a miss, not an exception."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    path = prov._disk_path("hist", "BAD", "hist:BAD:1y:1d")
    path.write_text("{ not json")
    path.chmod(0o600)

    assert prov._disk_load("hist", "BAD", "hist:BAD:1y:1d") is None


def test_provider_truncated_json_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file cut in the middle (concurrent writer) is a miss."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    prov._disk_save("info", "TRUNC", "info:TRUNC", _entry(), {"a": list(range(100))})
    path = prov._disk_path("info", "TRUNC", "info:TRUNC")
    blob = path.read_text()
    path.write_text(blob[: len(blob) // 2])

    assert prov._disk_load("info", "TRUNC", "info:TRUNC") is None


def test_provider_never_reads_pickles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy pickle files are ignored: they could carry code from another user."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    (tmp_path / "hist_deadbeef.pkl").write_bytes(pickle.dumps({"x": 1}))

    assert prov._disk_load("hist", "X", "hist:X:1y:1d") is None


def test_provider_ignores_files_of_another_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cache file that another uid owns is never read."""
    from trading_mcp.data import cache_paths

    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    prov._disk_save("info", "OWN", "info:OWN", _entry(), {"a": 1})
    monkeypatch.setattr(cache_paths, "_current_uid", lambda: os.getuid() + 1)

    assert prov._disk_load("info", "OWN", "info:OWN") is None


def test_provider_ignores_group_writable_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A cache file that other users can write is never read."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)
    prov._disk_save("info", "GW", "info:GW", _entry(), {"a": 1})
    prov._disk_path("info", "GW", "info:GW").chmod(0o666)

    assert prov._disk_load("info", "GW", "info:GW") is None


# ── result_cache: corrupt persistent file ──────────────────────────────

def test_result_cache_corrupt_file_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un result_cache.json corrotto inizializza vuoto, senza crash."""
    monkeypatch.setattr("trading_mcp.data.result_cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("trading_mcp.data.result_cache.CACHE_FILE", tmp_path / "result_cache.json")
    (tmp_path / "result_cache.json").write_text('{"broken": ')

    cache = ResultCache()  # non deve sollevare
    assert cache.get_stats() == {}


def test_result_cache_mkdir_oserror_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se la cache dir non è creabile, ResultCache funziona in sola memoria."""
    class _BoomPath(type(Path())):
        def mkdir(self, *args, **kwargs):  # type: ignore[override]
            raise PermissionError("denied")

    monkeypatch.setattr("trading_mcp.data.result_cache.CACHE_DIR", _BoomPath("/nonexistent/x"))
    monkeypatch.setattr("trading_mcp.data.result_cache.CACHE_FILE", _BoomPath("/nonexistent/x/f.json"))

    cache = ResultCache()  # non deve sollevare
    cache.set("analyze_stock", "AAPL", {"q": 1}, {"ok": True})
    hit = cache.get("analyze_stock", "AAPL", {"q": 1})
    assert hit is not None and hit["ok"] is True and hit["cached"] is True
