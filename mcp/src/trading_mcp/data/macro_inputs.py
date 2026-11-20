"""Macro inputs, each with value, data time and source (DATA-06, DATA-07).

:func:`collect_macro_inputs` never invents a value: a missing input is
``value=None`` with ``error``/``error_kind``, and a refresh failure that
serves an older value sets ``stale=True``. BTC, BTC dominance and the crypto
Fear & Greed index are crypto context only; the equity regime never reads
them (see :mod:`trading_mcp.analysis.macro`).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from trading_mcp.data import prices
from trading_mcp.data.http_policy import UpstreamFailure
from trading_mcp.data.web_json import ALTERNATIVE_ME_BUCKET, COINGECKO_BUCKET, TTLCache, get_json
from trading_mcp.timeutil import epoch_to_iso, utc_iso

logger = logging.getLogger(__name__)

MACRO_SYMBOLS: dict[str, str] = {
    "vix": "^VIX",
    "vix3m": "^VIX3M",
    "spx": "^GSPC",
    "dxy": "DX-Y.NYB",
    "rate": "^IRX",
    "btc": "BTC-USD",
}

# Quote freshness values that the regime may use.
USABLE_FRESHNESS = ("realtime", "delayed", "last_close")

_CRYPTO_CONTEXT_TTL_S = 300.0
_crypto_cache = TTLCache()


class MacroInput(BaseModel):
    """One macro input with provenance."""

    name: str
    symbol: str | None = None
    value: float | None = None
    unit: str | None = None
    as_of: str | None = Field(default=None, description="Data time (ISO 8601 with offset)")
    source: str | None = None
    stale: bool = False
    freshness: str | None = None
    error: str | None = None
    error_kind: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """True when the value is present and not stale."""
        return self.value is not None and not self.stale


class MacroInputs(BaseModel):
    """Every macro input plus the derived equity and dollar trends."""

    vix: MacroInput
    vix3m: MacroInput
    spx: MacroInput
    dxy: MacroInput
    rate: MacroInput
    btc: MacroInput
    btc_dominance: MacroInput
    fear_greed: MacroInput
    equity_trend: str | None = None
    dxy_trend: str | None = None
    collected_at: str = Field(default_factory=utc_iso)
    warnings: list[str] = Field(default_factory=list)

    def missing(self, names: tuple[str, ...] = ("vix", "spx", "dxy", "rate")) -> list[str]:
        """Names of required inputs without a usable value."""
        return [name for name in names if not getattr(self, name).usable]

    def legacy_dict(self) -> dict[str, Any]:
        """The pre-4.0 ``DataProvider.get_macro_context`` keys plus ``inputs``."""
        return {
            "vix": self.vix.value,
            "dxy": self.dxy.value,
            "dxy_prev": self.dxy.details.get("reference_close"),
            "equity_trend": self.equity_trend,
            "btc_price": self.btc.value,
            "btc_dominance": self.btc_dominance.value,
            "fear_greed": self.fear_greed.value,
            "inputs": {name: getattr(self, name).model_dump() for name in (
                "vix", "vix3m", "spx", "dxy", "rate", "btc", "btc_dominance", "fear_greed")},
        }


def _from_quote(provider: Any, name: str, symbol: str, unit: str) -> MacroInput:
    quote = provider.get_quote(symbol)
    item = MacroInput(
        name=name, symbol=symbol, unit=unit, value=quote.price, as_of=quote.as_of,
        source=quote.source, freshness=quote.freshness, error=quote.error, error_kind=quote.error_kind,
        details={"age_s": quote.age_s, "session_state": quote.session_state},
    )
    if quote.price is not None and quote.freshness not in USABLE_FRESHNESS:
        item.stale = True
        item.details["warning"] = f"quote freshness is {quote.freshness}"
    if quote.warnings:
        item.details["warnings"] = list(quote.warnings)
    return item


def _equity_trend(provider: Any) -> tuple[MacroInput, str | None]:
    """S&P 500 trend from complete daily bars: price vs MA50 and the 60-bar return."""
    frame, meta = provider.get_hist_with_meta("^GSPC", period="1y", interval="1d")
    item = MacroInput(name="spx", symbol="^GSPC", unit="index points", as_of=meta.as_of,
                      source=meta.source, stale=bool(meta.stale or meta.up_to_date is False),
                      error=meta.error, error_kind=meta.error_kind)
    close = frame["Close"].dropna() if not frame.empty and "Close" in frame else None
    if close is None or len(close) < 60:
        item.error = item.error or f"S&P 500 history too short ({0 if close is None else len(close)} bars)"
        item.error_kind = item.error_kind or "insufficient_data"
        return item, None
    item.value = round(float(close.iloc[-1]), 2)
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ret_60 = prices.total_return(frame, 60)
    item.details = {"ma50": round(ma50, 2), "return_60d": round(ret_60, 4) if ret_60 is not None else None,
                    "bars": len(close), "last_bar_date": meta.last_bar_date}
    if ret_60 is None:
        return item, None
    if item.value > ma50 and ret_60 > 0.02:
        trend = "up"
    elif item.value < ma50 and ret_60 < -0.02:
        trend = "down"
    else:
        trend = "range"
    item.details["trend"] = trend
    return item, trend


def _dollar(provider: Any) -> tuple[MacroInput, str | None]:
    """DXY level (quote) and the 1-month trend from complete daily bars (+-2%)."""
    item = _from_quote(provider, "dxy", "DX-Y.NYB", "index points")
    frame, meta = provider.get_hist_with_meta("DX-Y.NYB", period="1mo", interval="1d")
    close = frame["Close"].dropna() if not frame.empty and "Close" in frame else None
    if close is None or len(close) < 5:
        item.details["trend_error"] = meta.error or "DXY history too short for a trend"
        return item, None
    last = float(close.iloc[-1])
    reference = float(close.iloc[-min(len(close), 22)])
    item.details.update(reference_close=round(reference, 4), last_close=round(last, 4),
                        trend_as_of=meta.as_of, trend_bars=len(close))
    if item.value is None:
        item.details["warning"] = "DXY quote unavailable; only the trend is known"
    if last > reference * 1.02:
        trend = "rising"
    elif last < reference * 0.98:
        trend = "falling"
    else:
        trend = "neutral"
    item.details["trend"] = trend
    return item, trend


def _rate() -> MacroInput:
    from trading_mcp.data.risk_free import get_risk_free_rate  # pylint: disable=import-outside-toplevel

    snapshot = get_risk_free_rate()
    item = MacroInput(name="rate", symbol=snapshot.source_ticker, unit="percent",
                      source=snapshot.source, as_of=snapshot.as_of, stale=snapshot.stale,
                      details={"tenor": snapshot.tenor, "fallback_reason": snapshot.fallback_reason})
    if snapshot.is_live:
        item.value = round(snapshot.value * 100.0, 3)
    elif snapshot.as_of is not None:
        # Last live value served after a failed refresh: real data, flagged stale.
        item.value = round(snapshot.value * 100.0, 3)
        item.error, item.error_kind = snapshot.fallback_reason, "stale_fallback"
    else:
        item.error, item.error_kind = snapshot.fallback_reason, "fallback"
    return item


def _coingecko_headers() -> dict[str, str]:
    key = os.environ.get("COINGECKO_API_KEY")
    return {"x-cg-demo-api-key": key} if key else {}


def _cached_crypto_context(key: str, fetch) -> MacroInput:
    hit = _crypto_cache.get(key)
    if hit is not None:
        value, _, failure = hit
        if failure is not None:
            return MacroInput(name=key, error=failure.message, error_kind=failure.kind)
        return MacroInput.model_validate(value)
    try:
        item = fetch()
    except UpstreamFailure as exc:
        _crypto_cache.set_failure(key, exc)
        logger.warning("%s unavailable: %s", key, exc.kind)
        return MacroInput(name=key, error=exc.message, error_kind=exc.kind)
    _crypto_cache.set(key, item.model_dump(), _CRYPTO_CONTEXT_TTL_S)
    return item


def fetch_btc_dominance() -> MacroInput:
    """BTC market-cap dominance (%) from CoinGecko ``/global`` (5 min cache)."""

    def _fetch() -> MacroInput:
        payload = get_json("https://api.coingecko.com/api/v3/global", what="coingecko global",
                           headers=_coingecko_headers(), bucket=COINGECKO_BUCKET)
        data = (payload or {}).get("data") or {}
        pct = (data.get("market_cap_percentage") or {}).get("btc")
        if pct is None:
            raise UpstreamFailure("empty", "coingecko global: no btc dominance", retryable=False)
        return MacroInput(name="btc_dominance", value=round(float(pct), 2), unit="percent",
                          as_of=epoch_to_iso(data.get("updated_at")), source="coingecko:/global")

    return _cached_crypto_context("btc_dominance", _fetch)


def fetch_fear_greed() -> MacroInput:
    """Crypto Fear & Greed index (0-100) from alternative.me (5 min cache)."""

    def _fetch() -> MacroInput:
        payload = get_json("https://api.alternative.me/fng/", what="alternative.me fng",
                           bucket=ALTERNATIVE_ME_BUCKET)
        entries = (payload or {}).get("data") or []
        if not entries or entries[0].get("value") is None:
            raise UpstreamFailure("empty", "alternative.me fng: no value", retryable=False)
        first = entries[0]
        return MacroInput(name="fear_greed", value=float(first["value"]), unit="index 0-100",
                          as_of=epoch_to_iso(first.get("timestamp")), source="alternative.me:/fng",
                          details={"classification": first.get("value_classification")})

    return _cached_crypto_context("fear_greed", _fetch)


def clear_crypto_context_cache() -> None:
    """Drop the cached BTC dominance and Fear & Greed answers."""
    _crypto_cache.clear()


def collect_macro_inputs(provider: Any | None = None) -> MacroInputs:
    """Fetch every macro input through the provider (quotes, complete daily bars)."""
    if provider is None:
        from trading_mcp.data.provider import data_provider as provider  # pylint: disable=import-outside-toplevel
    spx, equity_trend = _equity_trend(provider)
    dxy, dxy_trend = _dollar(provider)
    inputs = MacroInputs(
        vix=_from_quote(provider, "vix", "^VIX", "index points"),
        vix3m=_from_quote(provider, "vix3m", "^VIX3M", "index points"),
        spx=spx,
        dxy=dxy,
        rate=_rate(),
        btc=_from_quote(provider, "btc", "BTC-USD", "USD"),
        btc_dominance=fetch_btc_dominance(),
        fear_greed=fetch_fear_greed(),
        equity_trend=equity_trend,
        dxy_trend=dxy_trend,
    )
    for name in ("vix", "vix3m", "spx", "dxy", "rate", "btc", "btc_dominance", "fear_greed"):
        item: MacroInput = getattr(inputs, name)
        if item.value is None:
            inputs.warnings.append(f"{name} unavailable: {item.error or 'no data'}")
        elif item.stale:
            inputs.warnings.append(f"{name} is stale (as_of {item.as_of})")
    return inputs
