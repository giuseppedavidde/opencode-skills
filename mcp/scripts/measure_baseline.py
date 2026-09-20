#!/usr/bin/env python3
"""Fase MISURAZIONE del trading MCP server.

Script standalone di SOLA misura: monkey-patch (nessuna modifica ai moduli del
server) per contare traffico di rete reale, tempi per tool e per sottoblocco di
``process_ticker``, hit/miss cache, e costo di load/predizione LGBM.

Produce:
  * report JSON   ``/tmp/opencode/measurement-baseline.json``
  * report Markdown ``/tmp/opencode/measurement-baseline.md``

Uso:
  ~/.local/share/opencode/trading-mcp-venv/bin/python mcp/scripts/measure_baseline.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_TMP_RUN = Path("/tmp/opencode/measurement_run")
_TMP_RUN.mkdir(parents=True, exist_ok=True)
# Isola la cache su disco del provider: misurazione "cold", nessun side-effect
# sulla cache utente. Deve essere impostata PRIMA di importare trading_mcp.
os.environ["TRADING_DATA_CACHE_DIR"] = str(_TMP_RUN / "data_cache")

import yfinance as yf  # noqa: E402  pylint: disable=wrong-import-position

MACRO_SYMBOLS = {"^VIX", "DX-Y.NYB", "^TNX", "^IXIC", "SHY", "^GSPC", "BTC-USD"}

# ── Ledger thread-safe ────────────────────────────────────────────────
class Ledger:
    """Contatori e tempi thread-safe per la misurazione."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.net: dict[str, int] = defaultdict(int)
        self.net_by_symbol: dict[str, int] = defaultdict(int)
        self.net_calls: list[dict[str, Any]] = []
        self.provider: dict[str, int] = defaultdict(int)
        self.provider_calls: list[dict[str, Any]] = []
        self.block_time: dict[str, float] = defaultdict(float)
        self.block_calls: dict[str, int] = defaultdict(int)

    def record_net(self, kind: str, symbol: Any, detail: str = "") -> None:
        sym = str(symbol)
        with self._lock:
            self.net[kind] += 1
            self.net_by_symbol[sym] += 1
            if len(self.net_calls) < 20000:
                self.net_calls.append(
                    {"t": time.time(), "kind": kind, "symbol": sym, "detail": detail}
                )

    def net_for(self, symbol: str) -> int:
        with self._lock:
            return self.net_by_symbol.get(str(symbol), 0)

    def record_provider(
        self, method: str, symbol: str, seconds: float, key: str, net_delta: int
    ) -> None:
        with self._lock:
            self.provider[method] += 1
            self.provider_calls.append(
                {
                    "method": method,
                    "symbol": symbol,
                    "key": key,
                    "seconds": round(seconds, 4),
                    "network_calls_during": net_delta,
                }
            )

    def record_block(self, group: str, seconds: float) -> None:
        with self._lock:
            self.block_time[group] += seconds
            self.block_calls[group] += 1

    def block_snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {
                g: {
                    "total_s": round(self.block_time[g], 3),
                    "calls": self.block_calls[g],
                }
                for g in self.block_time
            }

    def provider_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counts": dict(self.provider),
                "calls": list(self.provider_calls),
            }

    def net_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "by_kind": dict(self.net),
                "total": sum(self.net.values()),
                "calls": list(self.net_calls),
            }


LEDGER = Ledger()


# ── Monkey-patch yfinance ─────────────────────────────────────────────
_REAL_TICKER = yf.Ticker
_REAL_DOWNLOAD = yf.download


class _CountingTicker(_REAL_TICKER):  # type: ignore[misc,valid-type]
    """Subclass di yfinance.Ticker che registra le chiamate di rete."""

    def _sym(self) -> str:
        return str(getattr(self, "ticker", getattr(self, "symbol", "?")))

    @property
    def options(self):  # type: ignore[override]
        LEDGER.record_net("yf.options", self._sym())
        return _REAL_TICKER.options.fget(self)  # type: ignore[attr-defined]

    def option_chain(self, *args, **kwargs):  # type: ignore[override]
        expiry = args[0] if args else kwargs.get("date", "")
        LEDGER.record_net("yf.option_chain", self._sym(), detail=str(expiry))
        return _REAL_TICKER.option_chain(self, *args, **kwargs)

    @property
    def news(self):  # type: ignore[override]
        LEDGER.record_net("yf.news", self._sym())
        return _REAL_TICKER.news.fget(self)  # type: ignore[attr-defined]

    @property
    def earnings_history(self):  # type: ignore[override]
        LEDGER.record_net("yf.earnings_history", self._sym())
        return _REAL_TICKER.earnings_history.fget(self)  # type: ignore[attr-defined]

    @property
    def info(self):  # type: ignore[override]
        LEDGER.record_net("yf.info", self._sym())
        return _REAL_TICKER.info.fget(self)  # type: ignore[attr-defined]

    def history(self, *args, **kwargs):  # type: ignore[override]
        period = kwargs.get("period", args[0] if args else "")
        interval = kwargs.get("interval", "")
        LEDGER.record_net("yf.history", self._sym(), detail=f"{period}/{interval}")
        return _REAL_TICKER.history(self, *args, **kwargs)


def _counting_download(*args, **kwargs):
    tickers = kwargs.get("tickers", args[0] if args else "")
    LEDGER.record_net("yf.download", tickers)
    return _REAL_DOWNLOAD(*args, **kwargs)


yf.Ticker = _CountingTicker  # type: ignore[misc]
yf.download = _counting_download  # type: ignore[assignment]


# ── Monkey-patch DataProvider ─────────────────────────────────────────
def _patch_provider() -> None:
    from trading_mcp.data.provider import DataProvider

    def _wrap(method: str) -> None:
        original: Callable[..., Any] = getattr(DataProvider, method)

        def wrapper(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            symbol = args[0] if args else kwargs.get("symbol", "?")
            period = kwargs.get("period", args[1] if len(args) > 1 else "1y")
            interval = kwargs.get("interval", args[2] if len(args) > 2 else "1d")
            key = ""
            if method == "get_hist":
                key = f"{period}/{interval}"
            elif method == "get_options_chain":
                expiry = args[1] if len(args) > 1 else kwargs.get("expiry", "")
                key = str(expiry)
            before = LEDGER.net_for(str(symbol))
            t0 = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                dt = time.perf_counter() - t0
                delta = LEDGER.net_for(str(symbol)) - before
                LEDGER.record_provider(method, str(symbol), dt, key, delta)

        wrapper.__name__ = method
        setattr(DataProvider, method, wrapper)

    for m in ("get_hist", "get_info", "get_options_chain", "get_options_expirations"):
        _wrap(m)


_patch_provider()

from trading_mcp.data.provider import data_provider  # noqa: E402
from trading_mcp.data import result_cache as rc_mod  # noqa: E402

# Isola la result cache su /tmp (nessun side-effect sulla cache utente).
rc_mod.CACHE_DIR = _TMP_RUN
rc_mod.CACHE_FILE = _TMP_RUN / "result_cache.json"
rc_mod.result_cache._entries.clear()  # pylint: disable=protected-access
rc_mod.result_cache._stats.clear()  # pylint: disable=protected-access


# ── Monkey-patch sottoblocchi di process_ticker ───────────────────────
BLOCK_MAP: dict[str, str] = {
    "compute_wyckoff": "wyckoff",
    "compute_6clue_test": "wyckoff",
    "compute_sentiment_6d": "sentiment_6d",
    "compute_squeeze_play": "squeeze_play",
    "compute_meta_label": "meta_label",
    "get_meta_label_setup": "meta_label",
    "compute_volume_profile": "volume_profile",
    "compute_price_action": "price_action",
    "compute_fundamentals": "fundamentals",
    "compute_sentiment": "sentiment_legacy",
    "compute_bollinger": "indicators",
    "compute_obv": "indicators",
    "compute_candlestick_patterns": "indicators",
    "compute_candlestick_advanced": "indicators",
    "compute_risk_reward": "indicators",
    "compute_psychology_advanced": "indicators",
    "compute_point_figure": "indicators",
    "compute_taa_patterns": "taa",
    "compute_sot_weis_wave": "weis",
}


def _patch_blocks() -> list[str]:
    import trading_mcp.analysis.scanner as scanner

    patched: list[str] = []
    for name, group in BLOCK_MAP.items():
        original = getattr(scanner, name, None)
        if original is None:
            continue

        def make_wrapper(fn, grp):  # type: ignore[no-untyped-def]
            def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                t0 = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    LEDGER.record_block(grp, time.perf_counter() - t0)

            return wrapper

        setattr(scanner, name, make_wrapper(original, group))
        patched.append(name)
    return patched


PATCHED_BLOCKS = _patch_blocks()


# ── LGBM load / predict timing ────────────────────────────────────────
LGBM_SKILL_DIR = Path.home() / ".config" / "opencode" / "skills" / "lgbm-trader-skill"
LGBM_TIMES: dict[str, float] = defaultdict(float)
LGBM_COUNTS: dict[str, int] = defaultdict(int)


def _patch_lgbm() -> bool:
    if str(LGBM_SKILL_DIR) not in sys.path:
        sys.path.insert(0, str(LGBM_SKILL_DIR))
    try:
        from models import stacking as stacking_mod  # type: ignore
        from models import lgbm_trainer as trainer_mod  # type: ignore
    except Exception:  # pylint: disable=broad-exception-caught
        return False

    def _time(name: str, fn):  # type: ignore[no-untyped-def]
        def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                LGBM_TIMES[name] += time.perf_counter() - t0
                LGBM_COUNTS[name] += 1

        return wrapper

    for cls, tag in (
        (stacking_mod.StackingEnsemble, "stacking"),
        (trainer_mod.LGBMTrainer, "single"),
    ):
        setattr(
            cls,
            "load",
            classmethod(_time(f"{tag}_load", cls.__dict__["load"].__func__)),
        )
        setattr(cls, "predict", _time(f"{tag}_predict", cls.predict))
    return True


LGBM_PATCHED = _patch_lgbm()


# ── Tool registry ─────────────────────────────────────────────────────
def _load_tools() -> dict[str, Callable[..., Any]]:
    import asyncio

    from trading_mcp.mcp import initialize_mcp

    srv = initialize_mcp()
    listed = srv._list_tools()  # pylint: disable=protected-access
    if hasattr(listed, "__await__"):
        listed = asyncio.run(listed)
    return {t.name: t.fn for t in listed}


def _run_tool(name: str, fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    """Esegue un tool registrando tempi, rete e delta cache."""
    rc_before = rc_mod.result_cache.get_stats()
    prov_before = data_provider.cache_stats()
    net_snapshot = LEDGER.net_snapshot()
    net_before = net_snapshot["by_kind"].copy()
    net_calls_before = len(net_snapshot["calls"])
    block_before = LEDGER.block_snapshot()
    prov_calls_before = len(LEDGER.provider_snapshot()["calls"])

    t0 = time.perf_counter()
    error = None
    result: Any = None
    try:
        result = fn(**kwargs)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    dt = time.perf_counter() - t0

    net_snapshot2 = LEDGER.net_snapshot()
    net_after = net_snapshot2["by_kind"]
    net_delta = {k: net_after.get(k, 0) - net_before.get(k, 0) for k in net_after}
    net_delta = {k: v for k, v in net_delta.items() if v}
    rc_after = rc_mod.result_cache.get_stats()
    prov_after = data_provider.cache_stats()

    blocks_after = LEDGER.block_snapshot()
    block_delta: dict[str, dict[str, float]] = {}
    for g, val in blocks_after.items():
        prev = block_before.get(g, {"total_s": 0.0, "calls": 0})
        block_delta[g] = {
            "total_s": round(val["total_s"] - prev["total_s"], 3),
            "calls": int(val["calls"] - prev["calls"]),
        }

    return {
        "tool": name,
        "args": kwargs,
        "seconds": round(dt, 3),
        "error": error,
        "net_delta": net_delta,
        "net_total_delta": sum(net_delta.values()),
        "blocks": block_delta,
        "result_cache_delta": _cache_delta(rc_before, rc_after),
        "provider_calls": LEDGER.provider_snapshot()["calls"][prov_calls_before:],
        "net_calls": net_snapshot2["calls"][net_calls_before:],
        "provider_entries": {
            "before": prov_before.get("total_entries"),
            "after": prov_after.get("total_entries"),
        },
        "result_summary": _summarize(name, result),
    }


def _cache_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for tool, stats in after.items():
        b = before.get(tool, {"hits": 0, "misses": 0})
        dh = stats.get("hits", 0) - b.get("hits", 0)
        dm = stats.get("misses", 0) - b.get("misses", 0)
        if dh or dm:
            delta[tool] = {"hits": dh, "misses": dm}
    return delta


def _summarize(_name: str, result: Any) -> Any:
    """Estrae solo campi compatti, evitando payload enormi nei report."""
    if not isinstance(result, dict):
        return None
    out: dict[str, Any] = {}
    for key in (
        "ticker", "verdict", "score", "final_score", "confidence",
        "action", "signal", "regime", "signal_score", "composite_score",
        "universe", "scanned", "matches", "available", "error", "model",
        "iv_rank", "spot_price",
    ):
        if key in result and not isinstance(result[key], (dict, list)):
            out[key] = result[key]
    if "results" in result and isinstance(result["results"], list):
        out["n_results"] = len(result["results"])
    if "total_scanned" in result:
        out["total_scanned"] = result["total_scanned"]
    return out


# ── Percorsi ──────────────────────────────────────────────────────────
SCAN_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK-B",
    "JPM", "LLY", "UNH", "XOM", "V", "MA", "COST", "JNJ", "PG", "HD", "MRK",
    "ABBV", "CVX", "PEP", "KO", "AMD", "NFLX", "CRM", "ADBE", "MCD", "WMT",
    "DIS", "CSCO", "INTC", "QCOM", "TXN", "AMGN", "CAT", "BA", "GS", "NKE",
]


def path_a_single(tools: dict[str, Callable[..., Any]], ticker: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    steps.append(_run_tool("analyze_stock", tools["analyze_stock"], ticker=ticker))
    for tname in ("bali_signals", "tsmom_signals", "bakshi_signals"):
        steps.append(_run_tool(tname, tools[tname], ticker=ticker))
    steps.append(_run_tool("lgbm_predict", tools["lgbm_predict"], ticker=ticker))
    steps.append(
        _run_tool("lgbm_postprocess", tools["lgbm_postprocess"], ticker=ticker)
    )
    steps.append(
        _run_tool(
            "suggest_options_strategy",
            tools["suggest_options_strategy"],
            ticker=ticker,
            composite_score=65.0,
            verdict="bullish",
        )
    )
    return steps


def path_b_scan(tools: dict[str, Callable[..., Any]]) -> list[dict[str, Any]]:
    tickers = ",".join(SCAN_TICKERS)
    return [
        _run_tool(
            "scan_market",
            tools["scan_market"],
            universe="us_large",
            tickers=tickers,
            min_score=0.0,
            top_n=5,
            max_workers=4,
            fetch_news=False,
        )
    ]


def path_c_options(tools: dict[str, Callable[..., Any]], ticker: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    # Ricava una scadenza valida via provider.
    expirations = data_provider.get_options_expirations(ticker)
    expiry = expirations[0] if expirations else ""
    steps.append(
        _run_tool(
            "fetch_options_chain",
            tools["fetch_options_chain"],
            ticker=ticker,
            expiry=expiry,
            strike_window=10,
        )
    )
    if expiry:
        steps.append(
            _run_tool(
                "analyze_options",
                tools["analyze_options"],
                ticker=ticker,
                legs=[],
                expiry=expiry,
            )
        )
    steps.append(
        _run_tool(
            "suggest_options_strategy",
            tools["suggest_options_strategy"],
            ticker=ticker,
            composite_score=70.0,
            verdict="bullish",
            iv_rank=55.0,
        )
    )
    return steps


# ── Verdetti R1/R3/R7 ─────────────────────────────────────────────────
def _verdicts(
    path_a: list[dict[str, Any]], net_calls: list[dict[str, Any]]
) -> dict[str, Any]:
    verdicts: dict[str, Any] = {}

    yf_chain = [c for c in net_calls if c["kind"] == "yf.option_chain"]
    yf_options = [c for c in net_calls if c["kind"] == "yf.options"]

    analyze_step = next((s for s in path_a if s["tool"] == "analyze_stock"), None)
    a_net = analyze_step.get("net_calls", []) if analyze_step else []
    a_chain = [c for c in a_net if c["kind"] == "yf.option_chain"]
    a_options = [c for c in a_net if c["kind"] == "yf.options"]
    prov_chain = []
    prov_exps = []
    if analyze_step:
        for pc in analyze_step["provider_calls"]:
            if pc["method"] == "get_options_chain":
                prov_chain.append(pc)
            elif pc["method"] == "get_options_expirations":
                prov_exps.append(pc)

    # Decomposizione (dentro analyze_stock): yf.option_chain totali =
    # squeeze_play diretto + provider (sentiment_6d). Il provider interno
    # coincide con i network_calls_during delle get_options_chain.
    provider_internal_chain = sum(pc["network_calls_during"] for pc in prov_chain)
    direct_chain = max(0, len(a_chain) - provider_internal_chain)
    r1_confirmed = direct_chain > 0 and len(prov_chain) > 0
    verdicts["R1"] = {
        "ipotesi": "Doppio fetch opzioni: squeeze_play usa yf diretto "
        "(ticker.options/option_chain), sentiment_6d usa il DataProvider sullo "
        "stesso sottostante ⇒ stesse catene scaricate 2 volte.",
        "verdetto": "CONFERMATA" if r1_confirmed else "SMENTITA",
        "evidenza": {
            "dentro_analyze_stock": {
                "yf_option_chain_totali": len(a_chain),
                "squeeze_play_chain_dirette": direct_chain,
                "provider_get_options_chain_calls": len(prov_chain),
                "provider_chain_network_calls": provider_internal_chain,
                "yf_options_property_calls": len(a_options),
                "provider_get_options_expirations_calls": len(prov_exps),
                "expiries_richieste": [c["detail"] for c in a_chain],
            },
            "sessione_intera": {
                "yf_option_chain_totali": len(yf_chain),
                "yf_options_property_totali": len(yf_options),
                "provider_get_options_chain_totali": sum(
                    1 for s in path_a for pc in s["provider_calls"]
                    if pc["method"] == "get_options_chain"
                ),
            },
        },
    }

    # R3: chiavi (period, interval) distinte per get_hist dello stesso ticker
    hist_calls = []
    for step in path_a:
        for pc in step["provider_calls"]:
            if pc["method"] == "get_hist":
                hist_calls.append({"step": step["tool"], **pc})
    periods = {h["key"] for h in hist_calls if h["symbol"] == "AAPL"}
    r3_confirmed = len(periods) >= 2
    verdicts["R3"] = {
        "ipotesi": "Cache warming inefficace per chiave (period, interval): "
        "analyze_stock scalda 1y/1d, lgbm_predict chiede 5y/1d ⇒ miss + refetch.",
        "verdetto": "CONFERMATA" if r3_confirmed else "SMENTITA",
        "evidenza": {
            "get_hist_calls": [
                {"step": h["step"], "symbol": h["symbol"], "key": h["key"],
                 "network": h["network_calls_during"] > 0}
                for h in hist_calls
            ],
            "distinct_keys_aapl": sorted(periods),
            "n_get_hist_totali": len(hist_calls),
            "n_fetch_rete": sum(1 for h in hist_calls if h["network_calls_during"] > 0),
            "n_cache_hit": sum(1 for h in hist_calls if h["network_calls_during"] == 0),
            "nota": "Il warming funziona a pari chiave (bali/bakshi su 1y/1d "
            "hanno network=0), ma non copre periodi diversi (5y, 6mo, 5d, 15mo).",
        },
    }

    # R7: lgbm_predict scarica macro fuori dal provider
    lgbm_step = next((s for s in path_a if s["tool"] == "lgbm_predict"), None)
    macro_net = [c for c in net_calls if c["symbol"] in MACRO_SYMBOLS]
    lgbm_macro = []
    if lgbm_step:
        lgbm_macro = [
            c for c in lgbm_step.get("net_calls", [])
            if c["symbol"] in MACRO_SYMBOLS
        ]
    provider_macro = [
        pc for step in path_a for pc in step["provider_calls"]
        if pc["method"] == "get_hist" and pc["symbol"] in MACRO_SYMBOLS
    ]
    r7_confirmed = bool(lgbm_macro)
    verdicts["R7"] = {
        "ipotesi": "lgbm_predict scarica i dati macro fuori dal DataProvider "
        "(skill data.fetcher.fetch_macro) ⇒ chiamate di rete non cacheate.",
        "verdetto": "CONFERMATA" if r7_confirmed else "SMENTITA",
        "evidenza": {
            "macro_network_calls_totali_sessione": len(macro_net),
            "macro_network_calls_durante_lgbm_predict": len(lgbm_macro),
            "macro_symbols_lgbm": sorted({c["symbol"] for c in lgbm_macro}),
            "macro_calls_per_kind_lgbm": _count_by(lgbm_macro, "kind"),
            "provider_macro_get_hist": len(provider_macro),
            "net_delta_lgbm_predict": lgbm_step["net_delta"] if lgbm_step else None,
            "lgbm_step_seconds": lgbm_step["seconds"] if lgbm_step else None,
        },
    }
    return verdicts


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for it in items:
        out[it[key]] += 1
    return dict(out)


# ── Report ────────────────────────────────────────────────────────────
def _build_bottlenecks(paths: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pname, steps in paths.items():
        for s in steps:
            rows.append(
                {
                    "path": pname,
                    "tool": s["tool"],
                    "seconds": s["seconds"],
                    "net_calls": s["net_total_delta"],
                }
            )
    rows.sort(key=lambda r: r["seconds"], reverse=True)
    return rows


def _write_reports(report: dict[str, Any]) -> None:
    json_path = Path("/tmp/opencode/measurement-baseline.json")
    json_path.write_text(json.dumps(report, indent=2, default=str))

    md = []
    md.append("# Fase MISURAZIONE — trading MCP (baseline)\n")
    md.append(f"Generato: {report['meta']['timestamp']}\n")
    md.append(f"Ticker: `{report['meta']['ticker']}` | "
              f"venv: `{report['meta']['python']}` | "
              f"LGBM patch: {report['meta']['lgbm_patched']}\n")

    md.append("\n## 1. Traffico di rete per tipo (intera sessione)\n")
    md.append("| call kind | count |\n|---|---|")
    for k, v in sorted(report["network"]["by_kind"].items(), key=lambda x: -x[1]):
        md.append(f"| `{k}` | {v} |")
    md.append(f"\n**Totale chiamate di rete: {report['network']['total']}**\n")

    md.append("\n## 2. Tempi per tool (tutti i percorsi)\n")
    md.append("| percorso | tool | secondi | chiamate rete |\n|---|---|---|---|")
    for row in report["bottlenecks"]:
        md.append(
            f"| {row['path']} | `{row['tool']}` | {row['seconds']} | "
            f"{row['net_calls']} |"
        )

    md.append("\n### 2b. Rete per percorso\n")
    md.append("| percorso | chiamate rete | per tipo |\n|---|---|---|")
    for pname, steps in report["paths"].items():
        agg: dict[str, int] = defaultdict(int)
        tot = 0
        for s in steps:
            for k, v in s["net_delta"].items():
                agg[k] = agg.get(k, 0) + v
                tot += v
        md.append(f"| {pname} | {tot} | {dict(agg)} |")

    md.append("\n### 2c. Chiamate DataProvider per percorso\n")
    md.append("| percorso | metodo | symbol | key | secondi | rete |\n|---|---|---|---|---|---|")
    for pname, steps in report["paths"].items():
        for s in steps:
            for pc in s["provider_calls"]:
                md.append(
                    f"| {pname}/{s['tool']} | {pc['method']} | {pc['symbol']} | "
                    f"`{pc['key']}` | {pc['seconds']} | "
                    f"{pc['network_calls_during']} |"
                )

    md.append("\n## 3. Tempi sottoblocchi process_ticker (aggregati)\n")
    md.append("| blocco | secondi totali | chiamate |\n|---|---|---|")
    for g, val in sorted(
        report["blocks"].items(), key=lambda x: -x[1]["total_s"]
    ):
        md.append(f"| {g} | {val['total_s']} | {val['calls']} |")

    md.append("\n## 4. Cache\n")
    md.append("### result_cache (hit/miss per tool)\n")
    md.append("| tool | hits | misses | hit_rate % |\n|---|---|---|---|")
    for tool, st in report["cache"]["result_cache"].items():
        md.append(
            f"| {tool} | {st.get('hits')} | {st.get('misses')} | "
            f"{st.get('hit_rate')} |"
        )
    md.append("\n### DataProvider.cache_stats\n")
    md.append(f"```json\n{json.dumps(report['cache']['provider'], indent=2)}\n```\n")

    md.append("\n## 5. LGBM: load pickle vs predizione\n")
    md.append("| fase | secondi | chiamate |\n|---|---|---|")
    for k, v in sorted(report["lgbm"]["times"].items()):
        md.append(f"| {k} | {round(v, 4)} | {report['lgbm']['counts'].get(k, 0)} |")
    md.append(f"\nModello AAPL stacking: `{report['lgbm']['model_file']}` "
              f"({report['lgbm']['model_bytes']} byte)\n")

    md.append("\n## 6. Verdetti ipotesi\n")
    for rid, v in report["verdicts"].items():
        md.append(f"### {rid}: {v['verdetto']}\n")
        md.append(f"*Ipotesi*: {v['ipotesi']}\n")
        md.append(f"```json\n{json.dumps(v['evidenza'], indent=2)}\n```\n")

    md.append("\n## 7. Top colli di bottiglia\n")
    md.append("| # | percorso | tool | secondi | rete |\n|---|---|---|---|---|")
    for i, row in enumerate(report["bottlenecks"][:10], 1):
        md.append(
            f"| {i} | {row['path']} | `{row['tool']}` | {row['seconds']} | "
            f"{row['net_calls']} |"
        )

    Path("/tmp/opencode/measurement-baseline.md").write_text("\n".join(md) + "\n")


# ── Main ──────────────────────────────────────────────────────────────
def _lgbm_model_info(ticker: str) -> tuple[str, int]:
    saved = LGBM_SKILL_DIR / "models" / "saved"
    stacking = sorted(saved.glob(f"{ticker}_stacking_*.pkl"))
    single = sorted(saved.glob(f"{ticker}_lgbm_*.pkl"))
    if stacking:
        f = stacking[-1]
    elif single:
        f = single[-1]
    else:
        return "", 0
    return f.name, f.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--only", default="abc")
    args = parser.parse_args()

    tools = _load_tools()
    print(f"[measure] tools caricati: {len(tools)}", file=sys.stderr)

    paths: dict[str, list[dict[str, Any]]] = {}
    started = time.time()

    if "a" in args.only:
        print("[measure] percorso A: singolo titolo...", file=sys.stderr)
        paths["A_single"] = path_a_single(tools, args.ticker)
    if "b" in args.only and not args.skip_scan:
        print("[measure] percorso B: scan ridotto...", file=sys.stderr)
        paths["B_scan"] = path_b_scan(tools)
    if "c" in args.only:
        print("[measure] percorso C: opzioni...", file=sys.stderr)
        paths["C_options"] = path_c_options(tools, args.ticker)

    net = LEDGER.net_snapshot()
    model_file, model_bytes = _lgbm_model_info(args.ticker)

    report: dict[str, Any] = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_s": round(time.time() - started, 2),
            "ticker": args.ticker,
            "python": sys.executable,
            "lgbm_patched": LGBM_PATCHED,
            "patched_blocks": PATCHED_BLOCKS,
            "scan_tickers": len(SCAN_TICKERS) if "B_scan" in paths else 0,
            "scan_fetch_news": False,
        },
        "network": {
            "by_kind": net["by_kind"],
            "total": net["total"],
            "by_symbol": _count_by(net["calls"], "symbol"),
        },
        "paths": paths,
        "bottlenecks": _build_bottlenecks(paths),
        "blocks": LEDGER.block_snapshot(),
        "cache": {
            "result_cache": rc_mod.result_cache.get_stats(),
            "provider": data_provider.cache_stats(),
        },
        "lgbm": {
            "times": dict(LGBM_TIMES),
            "counts": dict(LGBM_COUNTS),
            "model_file": model_file,
            "model_bytes": model_bytes,
        },
        "verdicts": _verdicts(paths.get("A_single", []), net["calls"]),
    }

    _write_reports(report)

    print("\n=== SINTESI ===", file=sys.stderr)
    print(f"rete totale={net['total']} per_kind={net['by_kind']}", file=sys.stderr)
    for rid, v in report["verdicts"].items():
        print(f"{rid} -> {v['verdetto']}", file=sys.stderr)
    print("report: /tmp/opencode/measurement-baseline.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
