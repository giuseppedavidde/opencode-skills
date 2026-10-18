"""Backend registry: build the priority-ordered, availability-filtered chain."""

from __future__ import annotations

from trading_mcp import config
from trading_mcp.data.backends.base import OptionsBackend
from trading_mcp.data.backends.marketdata_backend import MarketDataBackend
from trading_mcp.data.backends.polygon_backend import PolygonBackend
from trading_mcp.data.backends.rest import HttpGet
from trading_mcp.data.backends.thetadata_backend import ThetaDataBackend
from trading_mcp.data.backends.yfinance_backend import YFinanceBackend

# Backends that take an injectable ``http_get`` (REST) vs. local ones.
_REST_BUILDERS: dict[str, type] = {
    "thetadata": ThetaDataBackend,
    "polygon": PolygonBackend,
    "marketdata": MarketDataBackend,
}
_LOCAL_BUILDERS: dict[str, type] = {"yfinance": YFinanceBackend}

_KNOWN = set(_REST_BUILDERS) | set(_LOCAL_BUILDERS)


def default_priority() -> list[str]:
    """Return the configured backend priority (``TRADING_OPTIONS_BACKENDS``)."""
    return list(config.OPTIONS_BACKENDS)


def build_backends(
    priority: list[str] | None = None,
    http_get: HttpGet | None = None,
) -> list[OptionsBackend]:
    """Build the ordered, available backend chain.

    ``yfinance`` is always appended last as an emergency fallback, even if it is
    not listed in ``priority``. Backends that fail their availability probe are
    skipped silently.
    """
    order = default_priority() if priority is None else list(priority)
    seen: set[str] = set()
    backend_list: list[OptionsBackend] = []
    for raw_name in order:
        name = str(raw_name).strip().lower()
        if name not in _KNOWN or name == "yfinance" or name in seen:
            continue
        seen.add(name)
        backend = _build_one(name, http_get)
        if backend is not None and backend.is_available():
            backend_list.append(backend)
    backend_list.append(YFinanceBackend())  # always the last resort
    return backend_list


def _build_one(name: str, http_get: HttpGet | None) -> OptionsBackend | None:
    """Instantiate a single backend by name (``None`` when unknown)."""
    if name in _REST_BUILDERS:
        return _REST_BUILDERS[name](http_get=http_get)
    if name in _LOCAL_BUILDERS:
        return _LOCAL_BUILDERS[name]()
    return None
