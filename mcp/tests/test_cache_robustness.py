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


# ── provider: atomic pickle write + corrupt read ───────────────────────

def test_provider_save_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_disk_save scrive payload + meta in modo atomico, nessun tmp residuo."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)

    prov._disk_save("hist", "AAPL:1d", {"close": [1.0, 2.0]})

    pkl_files = list(tmp_path.glob("hist_*.pkl"))
    meta_files = list(tmp_path.glob("*.meta.json"))
    assert len(pkl_files) == 1
    assert len(meta_files) == 1
    assert list(tmp_path.glob(".*tmp")) == []

    loaded = prov._disk_load("hist", "AAPL:1d", ttl=3600)
    assert loaded == {"close": [1.0, 2.0]}


def test_provider_corrupt_pickle_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un pickle corrotto → None (miss), non UnpicklingError propagato."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)

    data_path = prov._disk_path("hist", "BAD:1d")
    meta_path = prov._disk_meta_path("hist", "BAD:1d")
    data_path.write_bytes(b"not a pickle at all")
    meta_path.write_text(json.dumps({"ts": 0.0}))

    assert prov._disk_load("hist", "BAD:1d", ttl=10_000_000) is None


def test_provider_truncated_pickle_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pickle troncato a metà (EOFError) → None."""
    monkeypatch.setattr(prov, "_DATA_CACHE_DIR", tmp_path)

    data_path = prov._disk_path("info", "TRUNC")
    meta_path = prov._disk_meta_path("info", "TRUNC")
    blob = pickle.dumps({"a": list(range(100))}, protocol=pickle.HIGHEST_PROTOCOL)
    data_path.write_bytes(blob[: len(blob) // 2])
    meta_path.write_text(json.dumps({"ts": 0.0}))

    assert prov._disk_load("info", "TRUNC", ttl=10_000_000) is None


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
    assert cache.get("analyze_stock", "AAPL", {"q": 1}) == {"ok": True}
