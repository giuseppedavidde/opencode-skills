"""Observability: JSON logs on stderr, one audit line per tool call, health state (DATA-24).

- :func:`configure_logging` writes every log record as one JSON line on
  stderr (never stdout: the MCP stdio transport owns stdout). Secrets are
  masked by :mod:`trading_mcp.data.redact`.
- :class:`ToolCallObserver` is FastMCP middleware. Each ``tools/call`` gets a
  ``request_id`` (also on every log line written during the call) and one
  ``tool_call`` line with the tool name, duration, result-cache hit or miss,
  data-cache counter deltas, sources, ``as_of``, ``degraded`` and the error
  kind. Argument values are not logged: only their names and a SHA-256.
- :data:`STATE` keeps per-tool counters, the last error, the newest data time
  seen for each source and the last outcome for each upstream host. The
  ``health`` tool reads it; nothing is persisted.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastmcp.server.middleware import Middleware

from trading_mcp.data.redact import redact
from trading_mcp.timeutil import UTC, age_seconds, to_datetime, utc_iso, utc_now

REQUEST_ID: ContextVar[str | None] = ContextVar("trading_mcp_request_id", default=None)
TOOL_NAME: ContextVar[str | None] = ContextVar("trading_mcp_tool", default=None)

AUDIT_LOGGER = "trading_mcp.audit"
_HANDLER_FLAG = "_trading_mcp_json"
_MAX_TEXT = 300
_MAX_WALK_NODES = 400
_IDENTIFIER_ARGS = ("ticker", "coin_id", "universe", "skill_name", "symbol")
_VERSION_PACKAGES = ("trading-mcp-server", "fastmcp", "mcp", "yfinance", "pandas", "numpy", "scipy",
                     "pydantic", "requests", "curl_cffi", "PyYAML", "click")
LOCKFILE = Path(__file__).resolve().parents[2] / "requirements.lock"


# ── JSON logging ─────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """One JSON object per record: ts, level, logger, msg, request_id, tool and extra ``fields``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        request_id = REQUEST_ID.get()
        if request_id:
            payload["request_id"] = request_id
        tool = TOOL_NAME.get()
        if tool:
            payload["tool"] = tool
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = record.exc_text or redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str | int | None = None, *, stream: Any = None, fmt: str | None = None) -> logging.Handler:
    """Send every log record to stderr as JSON (idempotent).

    Args:
        level: Level of the ``trading_mcp`` loggers (default ``TRADING_LOG_LEVEL`` or INFO).
            Other libraries log WARNING and above.
        stream: Output stream (default ``sys.stderr``; never stdout).
        fmt: ``json`` (default, or ``TRADING_LOG_FORMAT``) or ``text``.
    """
    chosen = level if level is not None else (os.environ.get("TRADING_LOG_LEVEL") or "INFO")
    if isinstance(chosen, str):
        chosen = logging.getLevelName(chosen.strip().upper())
        if not isinstance(chosen, int):
            chosen = logging.INFO
    style = (fmt or os.environ.get("TRADING_LOG_FORMAT") or "json").strip().lower()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    setattr(handler, _HANDLER_FLAG, True)
    if style == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("trading_mcp").setLevel(chosen)
    # FastMCP has its own rich handler; send its records through the same JSON stream.
    fastmcp_logger = logging.getLogger("fastmcp")
    for existing in list(fastmcp_logger.handlers):
        fastmcp_logger.removeHandler(existing)
    fastmcp_logger.propagate = True
    fastmcp_logger.setLevel(logging.WARNING)
    return handler


# ── Upstream hosts ───────────────────────────────────────────────────

def _thetadata_host() -> str:
    from trading_mcp import config  # pylint: disable=import-outside-toplevel

    return urlparse(config.THETADATA_URL).netloc or config.THETADATA_URL


def _upstream_table() -> dict[str, dict[str, Any]]:
    """Known upstream hosts: source prefixes, key configuration and rate bucket."""
    # pylint: disable=import-outside-toplevel
    from trading_mcp import config
    from trading_mcp.data.http_policy import YAHOO_BUCKET
    from trading_mcp.data.web_json import ALTERNATIVE_ME_BUCKET, COINGECKO_BUCKET

    backends = set(config.OPTIONS_BACKENDS)
    return {
        "yahoo": {"host": "query1.finance.yahoo.com", "prefixes": ("yfinance", "yahoo"),
                  "configured": True, "bucket": YAHOO_BUCKET, "key_required": False},
        "coingecko": {"host": "api.coingecko.com", "prefixes": ("coingecko",),
                      "configured": True, "bucket": COINGECKO_BUCKET, "key_required": False},
        "alternative_me": {"host": "api.alternative.me", "prefixes": ("alternative.me", "alternative_me"),
                           "configured": True, "bucket": ALTERNATIVE_ME_BUCKET, "key_required": False},
        "fmp": {"host": "financialmodelingprep.com", "prefixes": ("fmp",),
                "configured": bool(config.FMP_API_KEY), "bucket": None, "key_required": True},
        "alpha_vantage": {"host": "www.alphavantage.co", "prefixes": ("alpha_vantage", "alphavantage"),
                          "configured": bool(config.ALPHA_VANTAGE_API_KEY), "bucket": None, "key_required": True},
        "thetadata": {"host": _thetadata_host(), "prefixes": ("thetadata",),
                      "configured": "thetadata" in backends and bool(config.THETADATA_API_KEY),
                      "bucket": None, "key_required": True},
        "polygon": {"host": "api.polygon.io", "prefixes": ("polygon",),
                    "configured": "polygon" in backends and bool(config.POLYGON_API_KEY),
                    "bucket": None, "key_required": True},
        "marketdata": {"host": "api.marketdata.app", "prefixes": ("marketdata",),
                       "configured": "marketdata" in backends and bool(config.MARKETDATA_API_KEY),
                       "bucket": None, "key_required": True},
    }


_PREFIX_TO_UPSTREAM = {
    "yfinance": "yahoo", "yahoo": "yahoo", "coingecko": "coingecko", "alternative.me": "alternative_me",
    "alternative_me": "alternative_me", "fmp": "fmp", "alpha_vantage": "alpha_vantage",
    "alphavantage": "alpha_vantage", "thetadata": "thetadata", "polygon": "polygon", "marketdata": "marketdata",
}


def upstreams_of(source: Any) -> list[str]:
    """Upstream names behind a source label such as ``yfinance:chart`` or ``coingecko+yfinance``."""
    if not isinstance(source, str) or not source:
        return []
    names: list[str] = []
    for part in re.split(r"[+,;\s]+", source.lower()):
        prefix = part.split(":", 1)[0].strip()
        name = _PREFIX_TO_UPSTREAM.get(prefix)
        if name and name not in names:
            names.append(name)
    return names


# ── State ────────────────────────────────────────────────────────────

def _short(text: Any) -> str | None:
    if text is None:
        return None
    value = redact(text)
    return value if len(value) <= _MAX_TEXT else value[: _MAX_TEXT - 3] + "..."


def _stamps(payload: Any) -> list[tuple[str, str | None, str | None]]:
    """``(source, as_of, error_kind)`` of nested blocks that name their source."""
    found: list[tuple[str, str | None, str | None]] = []
    stack: list[tuple[Any, int]] = [(payload, 0)]
    visited = 0
    while stack and visited < _MAX_WALK_NODES:
        node, depth = stack.pop()
        visited += 1
        if isinstance(node, dict):
            source = node.get("source")
            if isinstance(source, str) and source and (node.get("as_of") or node.get("error_kind")):
                as_of = node.get("as_of") if isinstance(node.get("as_of"), str) else None
                kind = node.get("error_kind") if isinstance(node.get("error_kind"), str) else None
                found.append((source, as_of, kind))
            if depth < 4:
                stack.extend((value, depth + 1) for value in node.values() if isinstance(value, (dict, list)))
        elif isinstance(node, list) and depth < 4:
            stack.extend((value, depth + 1) for value in node[:50] if isinstance(value, (dict, list)))
    return found


class ObservabilityState:
    """Thread-safe counters of this server process (reset on restart)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = utc_iso()
        self._started = time.monotonic()
        self.tools: dict[str, dict[str, Any]] = {}
        self.last_error: dict[str, Any] | None = None
        self.data_age: dict[str, dict[str, Any]] = {}
        self.hosts: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        """Forget every counter (tests and restarts)."""
        with self._lock:
            self.tools = {}
            self.last_error = None
            self.data_age = {}
            self.hosts = {}

    def uptime_s(self) -> float:
        """Seconds since the state was created."""
        return round(time.monotonic() - self._started, 3)

    def _tool(self, name: str) -> dict[str, Any]:
        return self.tools.setdefault(name, {
            "calls": 0, "errors": 0, "exceptions": 0, "degraded": 0, "cache_hits": 0,
            "total_ms": 0.0, "max_ms": 0.0, "last_ms": None, "last_called_at": None,
        })

    def _host(self, name: str) -> dict[str, Any]:
        return self.hosts.setdefault(name, {
            "successes": 0, "failures": 0, "last_success_at": None, "last_failure_at": None,
            "last_error": None, "last_error_kind": None,
        })

    def host_success(self, name: str) -> None:
        """Record a usable answer from an upstream host."""
        with self._lock:
            host = self._host(name)
            host["successes"] += 1
            host["last_success_at"] = utc_iso()

    def host_failure(self, name: str, error: Any, kind: Any) -> None:
        """Record a failed upstream answer."""
        with self._lock:
            host = self._host(name)
            host["failures"] += 1
            host["last_failure_at"] = utc_iso()
            host["last_error"] = _short(error)
            host["last_error_kind"] = kind if isinstance(kind, str) else None

    def record_result(self, tool: str, request_id: str, payload: dict[str, Any], duration_ms: float) -> None:
        """Update counters, data ages and host outcomes from one tool answer.

        Host outcomes come from the answers (a cache hit is not evidence that
        the host answers now, so it is not counted).
        """
        now = utc_iso()
        error = payload.get("error")
        blocking = bool(error) and payload.get("error_kind", "blocking") == "blocking"
        stamps = _stamps(payload)
        with self._lock:
            stats = self._tool(tool)
            stats["calls"] += 1
            stats["errors"] += int(blocking)
            stats["degraded"] += int(bool(payload.get("degraded")))
            stats["cache_hits"] += int(bool(payload.get("cached")))
            stats["total_ms"] += duration_ms
            stats["max_ms"] = max(stats["max_ms"], duration_ms)
            stats["last_ms"] = round(duration_ms, 3)
            stats["last_called_at"] = now
            if error:
                self.last_error = {"tool": tool, "request_id": request_id, "at": now,
                                   "error": _short(error), "error_kind": payload.get("error_kind")}
            for source, as_of, _kind in stamps:
                moment = to_datetime(as_of)
                if moment is None:
                    continue
                known = self.data_age.get(source)
                if known is None or (to_datetime(known["as_of"]) or moment) <= moment:
                    self.data_age[source] = {"source": source, "as_of": as_of, "seen_at": now, "tool": tool}
            sources = [s for s in payload.get("sources") or [] if isinstance(s, str)]
            if len(sources) == 1 and isinstance(payload.get("as_of"), str) and sources[0] not in self.data_age:
                self.data_age[sources[0]] = {"source": sources[0], "as_of": payload["as_of"], "seen_at": now,
                                             "tool": tool}
        if payload.get("cached"):
            return
        failed: set[str] = set()
        for source, as_of, kind in stamps:
            names = upstreams_of(source)
            if kind:
                for name in names:
                    self.host_failure(name, f"{source}: {kind}", kind)
                    failed.add(name)
            elif as_of:
                for name in names:
                    if name not in failed:
                        self.host_success(name)
        if error:
            for name in upstreams_of(payload.get("data_source")):
                if name not in failed:
                    self.host_failure(name, error, payload.get("error_kind"))
                    failed.add(name)
        else:
            for source in payload.get("sources") or []:
                for name in upstreams_of(source):
                    if name not in failed:
                        self.host_success(name)

    def record_exception(self, tool: str, request_id: str, exc: BaseException, duration_ms: float) -> None:
        """Count a tool that raised instead of answering."""
        now = utc_iso()
        with self._lock:
            stats = self._tool(tool)
            stats["calls"] += 1
            stats["exceptions"] += 1
            stats["total_ms"] += duration_ms
            stats["max_ms"] = max(stats["max_ms"], duration_ms)
            stats["last_ms"] = round(duration_ms, 3)
            stats["last_called_at"] = now
            self.last_error = {"tool": tool, "request_id": request_id, "at": now,
                               "error": _short(f"{type(exc).__name__}: {exc}"), "error_kind": "exception"}

    def snapshot(self) -> dict[str, Any]:
        """Deep copy of the counters (mean duration per tool added)."""
        with self._lock:
            tools = {}
            for name, stats in sorted(self.tools.items()):
                copy = dict(stats)
                copy["mean_ms"] = round(stats["total_ms"] / stats["calls"], 3) if stats["calls"] else None
                copy["total_ms"] = round(stats["total_ms"], 3)
                copy["max_ms"] = round(stats["max_ms"], 3)
                tools[name] = copy
            return {
                "tools": tools,
                "last_error": dict(self.last_error) if self.last_error else None,
                "data_age": {key: dict(value) for key, value in self.data_age.items()},
                "hosts": {key: dict(value) for key, value in self.hosts.items()},
            }


STATE = ObservabilityState()


# ── Middleware ───────────────────────────────────────────────────────

def _args_digest(arguments: dict[str, Any]) -> str:
    text = json.dumps(arguments, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _data_counters() -> dict[str, int]:
    from trading_mcp.data.provider import data_provider  # pylint: disable=import-outside-toplevel

    try:
        return dict(data_provider.cache_stats().get("counters") or {})
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def _result_cache_counts(tool: str) -> dict[str, int]:
    from trading_mcp.data.result_cache import result_cache  # pylint: disable=import-outside-toplevel

    try:
        stats = result_cache.get_stats().get(tool) or {}
    except Exception:  # pylint: disable=broad-exception-caught
        return {}
    return {"hits": int(stats.get("hits", 0)), "misses": int(stats.get("misses", 0))}


def _cache_label(payload: dict[str, Any], before: dict[str, int], after: dict[str, int]) -> str:
    if payload.get("cached"):
        return "hit"
    if after.get("misses", 0) > before.get("misses", 0):
        return "miss"
    return "none"


class ToolCallObserver(Middleware):
    """Request id, timing and one JSON audit line for every tool call."""

    def __init__(self, state: ObservabilityState | None = None) -> None:
        self.state = state or STATE
        self.logger = logging.getLogger(AUDIT_LOGGER)

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        message = context.message
        tool = str(getattr(message, "name", "unknown"))
        arguments = dict(getattr(message, "arguments", None) or {})
        request_id = uuid.uuid4().hex[:16]
        rid_token = REQUEST_ID.set(request_id)
        tool_token = TOOL_NAME.set(tool)
        data_before = _data_counters()
        cache_before = _result_cache_counts(tool)
        started = time.perf_counter()
        base: dict[str, Any] = {
            "event": "tool_call", "arg_names": sorted(arguments), "args_sha256": _args_digest(arguments),
        }
        base.update({key: arguments[key] for key in _IDENTIFIER_ARGS if isinstance(arguments.get(key), str)})
        try:
            result = await call_next(context)
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.state.record_exception(tool, request_id, exc, duration_ms)
            self.logger.error("tool %s raised %s", tool, type(exc).__name__, extra={"fields": {
                **base, "status": "exception", "duration_ms": round(duration_ms, 3),
                "error": _short(f"{type(exc).__name__}: {exc}")}})
            REQUEST_ID.reset(rid_token)
            TOOL_NAME.reset(tool_token)
            raise
        duration_ms = (time.perf_counter() - started) * 1000.0
        payload = getattr(result, "structured_content", None)
        payload = payload if isinstance(payload, dict) else {}
        try:
            self.state.record_result(tool, request_id, payload, duration_ms)
            data_after = _data_counters()
            delta = {key: data_after.get(key, 0) - data_before.get(key, 0) for key in data_after}
            status = "error" if payload.get("error") else ("degraded" if payload.get("degraded") else "ok")
            fields = {
                **base, "status": status, "duration_ms": round(duration_ms, 3),
                "cache": _cache_label(payload, cache_before, _result_cache_counts(tool)),
                "cache_age_s": payload.get("cache_age_s"),
                "data_cache": {key: value for key, value in delta.items() if value},
                "sources": payload.get("sources") or ([payload["data_source"]] if payload.get("data_source") else []),
                "as_of": payload.get("as_of"), "degraded": bool(payload.get("degraded")),
                "error_kind": payload.get("error_kind"), "error": _short(payload.get("error")),
                "warnings": len(payload.get("warnings") or []),
            }
            self.logger.info("tool %s %s in %.0f ms", tool, status, duration_ms, extra={"fields": fields})
        finally:
            REQUEST_ID.reset(rid_token)
            TOOL_NAME.reset(tool_token)
        return result


# ── Health snapshot ──────────────────────────────────────────────────

def package_versions() -> dict[str, str | None]:
    """Installed versions of the server and of its main dependencies."""
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in _VERSION_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def lockfile_drift(path: Path = LOCKFILE) -> dict[str, Any]:
    """Compare installed versions with the pins of ``requirements.lock`` (no marker evaluation).

    A package is in ``drift`` when its installed version is none of its
    pinned versions, and in ``missing`` when an unconditional pin is not
    installed.
    """
    if not path.is_file():
        return {"path": str(path), "found": False, "drift": [], "missing": []}
    pins: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)\s*(;.*)?$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        entry = pins.setdefault(_canonical(match.group(1)), {"versions": set(), "conditional": True})
        entry["versions"].add(match.group(2))
        entry["conditional"] = entry["conditional"] and bool(match.group(3))
    drift: list[dict[str, Any]] = []
    missing: list[str] = []
    for name, entry in sorted(pins.items()):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            if not entry["conditional"]:
                missing.append(name)
            continue
        if installed not in entry["versions"]:
            drift.append({"package": name, "locked": sorted(entry["versions"]), "installed": installed})
    return {"path": str(path), "found": True, "pins": len(pins), "drift": drift, "missing": missing}


def _bucket_stats(bucket: Any) -> dict[str, Any] | None:
    if bucket is None:
        return None
    try:
        return bucket.stats()
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def upstream_status(state: ObservabilityState = STATE) -> list[dict[str, Any]]:
    """Status of every known upstream host from the observed answers and the rate buckets."""
    snapshot = state.snapshot()["hosts"]
    rows: list[dict[str, Any]] = []
    for name, spec in _upstream_table().items():
        seen = snapshot.get(name, {})
        bucket = _bucket_stats(spec["bucket"])
        success, failure = seen.get("last_success_at"), seen.get("last_failure_at")
        if not spec["configured"]:
            status = "not_configured"
        elif bucket and bucket.get("blocked_for_s", 0) > 0:
            status = "rate_limited"
        elif failure and (not success or failure >= success):
            status = "failing"
        elif success:
            status = "ok"
        else:
            status = "unknown"
        rows.append({
            "name": name, "host": spec["host"], "configured": spec["configured"],
            "key_required": spec["key_required"], "status": status,
            "successes": seen.get("successes", 0), "failures": seen.get("failures", 0),
            "last_success_at": success, "last_failure_at": failure,
            "last_error": seen.get("last_error"), "last_error_kind": seen.get("last_error_kind"),
            "rate_limit": bucket,
        })
    return rows


def data_ages(state: ObservabilityState = STATE) -> list[dict[str, Any]]:
    """Newest data time seen for each source, with its age now."""
    now = utc_now()
    rows = []
    for source, entry in sorted(state.snapshot()["data_age"].items()):
        rows.append({**entry, "age_s": age_seconds(entry["as_of"], now)})
    return rows


def cache_overview() -> dict[str, Any]:
    """Data-provider counters with hit rate, and result-cache counters per tool."""
    # pylint: disable=import-outside-toplevel
    from trading_mcp.data.provider import data_provider
    from trading_mcp.data.result_cache import result_cache

    provider = data_provider.cache_stats()
    counters = provider.get("counters") or {}
    hits = int(counters.get("memory_hits", 0)) + int(counters.get("disk_hits", 0))
    lookups = hits + int(counters.get("network", 0))
    return {
        "data_provider": {
            "tickers_cached": provider.get("tickers_cached"), "entries": provider.get("total_entries"),
            "fresh_entries": provider.get("fresh_entries"), "counters": counters,
            "hit_rate_pct": round(100.0 * hits / lookups, 1) if lookups else None,
        },
        "result_cache": result_cache.get_stats(),
    }
