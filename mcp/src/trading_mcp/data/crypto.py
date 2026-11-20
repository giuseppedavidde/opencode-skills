"""Crypto data: CoinGecko market data plus Yahoo bars and quotes (DATA-02).

Symbol mapping (CoinGecko id to Yahoo symbol):

1. An argument that is already a Yahoo crypto symbol (``BTC-USD``) is used
   as given.
2. A curated table maps common CoinGecko ids, including the Yahoo symbols
   with a numeric suffix (Uniswap is ``UNI7083-USD``; ``UNI-USD`` is another
   coin).
3. Otherwise the CoinGecko ticker gives ``<SYMBOL>-USD`` and a warning says
   that the mapping is not verified.

An unknown id (CoinGecko HTTP 404) is an error; it never becomes a made-up
symbol such as ``BITCOIN-USD``. CoinGecko answers are cached for 60 s;
HTTP 429 blocks the CoinGecko bucket for the ``Retry-After`` time. Errors
are returned in ``warnings``/``error``, never swallowed.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
from typing import Any

import pandas as pd

from trading_mcp.data.http_policy import ERROR_NOT_FOUND, UpstreamFailure
from trading_mcp.data.provider import data_provider
from trading_mcp.data.web_json import COINGECKO_BUCKET, TTLCache, get_json

logger = logging.getLogger(__name__)

COINGECKO_TTL_S = 60.0
_coingecko_cache = TTLCache()

COINGECKO_TO_YAHOO: dict[str, str] = {
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "solana": "SOL-USD", "binancecoin": "BNB-USD",
    "ripple": "XRP-USD", "cardano": "ADA-USD", "dogecoin": "DOGE-USD", "polkadot": "DOT-USD",
    "chainlink": "LINK-USD", "litecoin": "LTC-USD", "avalanche-2": "AVAX-USD", "tron": "TRX-USD",
    "stellar": "XLM-USD", "bitcoin-cash": "BCH-USD", "near": "NEAR-USD", "internet-computer": "ICP-USD",
    "cosmos": "ATOM-USD", "monero": "XMR-USD", "ethereum-classic": "ETC-USD",
    "hedera-hashgraph": "HBAR-USD", "filecoin": "FIL-USD", "aave": "AAVE-USD", "algorand": "ALGO-USD",
    "tezos": "XTZ-USD", "shiba-inu": "SHIB-USD",
    # Yahoo symbols with a numeric suffix (the plain ticker is another asset).
    "uniswap": "UNI7083-USD", "the-graph": "GRT6719-USD", "sui": "SUI20947-USD",
    "aptos": "APT21794-USD", "arbitrum": "ARB11841-USD", "pepe": "PEPE24478-USD",
    "the-open-network": "TON11419-USD", "immutable-x": "IMX10603-USD", "blockstack": "STX4847-USD",
    "bittensor": "TAO22974-USD", "mantle": "MNT27075-USD",
}
_YAHOO_TO_COINGECKO = {symbol: coin for coin, symbol in COINGECKO_TO_YAHOO.items()}
_YAHOO_CRYPTO = re.compile(r"^[A-Z0-9]+-(USD|USDT|USDC|EUR|GBP|BTC|ETH)$")
_COIN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def _coingecko_api_key() -> str | None:
    return os.environ.get("COINGECKO_API_KEY")


def fetch_coingecko_coin(coin_id: str) -> dict[str, Any]:
    """CoinGecko ``/coins/{id}`` (60 s cache). Raises :class:`UpstreamFailure`."""
    hit = _coingecko_cache.get(coin_id)
    if hit is not None:
        value, _, failure = hit
        if failure is not None:
            raise failure
        return value
    url = (
        f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(coin_id, safe='-')}"
        "?localization=false&tickers=false&community_data=false&developer_data=false&sparkline=false"
    )
    key = _coingecko_api_key()
    try:
        payload = get_json(url, what=f"coingecko coin {coin_id}", bucket=COINGECKO_BUCKET,
                           headers={"x-cg-demo-api-key": key} if key else None, timeout=15.0)
    except UpstreamFailure as exc:
        _coingecko_cache.set_failure(coin_id, exc)
        raise
    if not isinstance(payload, dict) or not payload.get("id"):
        failure = UpstreamFailure("empty", f"coingecko coin {coin_id}: empty payload", retryable=False)
        _coingecko_cache.set_failure(coin_id, failure)
        raise failure
    _coingecko_cache.set(coin_id, payload, COINGECKO_TTL_S)
    return payload


def resolve_symbol(coin_id: str, coingecko: dict[str, Any] | None) -> tuple[str | None, str]:
    """Return ``(yahoo_symbol, how)`` for a CoinGecko id or a Yahoo symbol."""
    raw = coin_id.strip()
    if _YAHOO_CRYPTO.match(raw.upper()):
        return raw.upper(), "yahoo_symbol"
    if raw.lower() in COINGECKO_TO_YAHOO:
        return COINGECKO_TO_YAHOO[raw.lower()], "curated_map"
    ticker = (coingecko or {}).get("symbol")
    if ticker:
        return f"{str(ticker).upper()}-USD", "coingecko_symbol_unverified"
    return None, "unresolved"


def clear_coingecko_cache() -> None:
    """Drop cached CoinGecko answers."""
    _coingecko_cache.clear()


def fetch_crypto_yfinance(symbol: str, period: str = "1y") -> pd.DataFrame:
    """Daily crypto bars (complete UTC days) from the DataProvider."""
    return data_provider.get_crypto_hist(symbol, period=period)


def fetch_crypto_info_yfinance(symbol: str) -> dict[str, Any]:
    """Crypto ``info`` from the DataProvider."""
    return data_provider.get_info(symbol)


def fetch_crypto_full(coin_id: str, period: str = "1y") -> dict[str, Any]:
    """CoinGecko market data, Yahoo quote and complete daily bars for one coin.

    Returns ``coin_id``, ``symbol`` (Yahoo, or ``None``), ``symbol_source``,
    ``current_price_usd`` (``None`` when no source answers), ``price_source``,
    ``price_as_of``, ``quote``, ``market_cap``, ``total_volume``,
    ``market_data_as_of``, ``hist``, ``hist_meta``, ``coingecko`` (raw),
    ``warnings``, ``error`` and ``error_kind``.
    """
    warnings: list[str] = []
    result: dict[str, Any] = {
        "coin_id": coin_id, "symbol": None, "symbol_source": None, "current_price_usd": None,
        "price_source": None, "price_as_of": None, "quote": None, "market_cap": None,
        "total_volume": None, "market_data_as_of": None, "hist": pd.DataFrame(), "hist_meta": None,
        "info": {}, "coingecko": {}, "warnings": warnings, "error": None, "error_kind": None,
    }
    raw = coin_id.strip()
    gecko_id = raw.lower() if _COIN_ID.match(raw.lower()) and not _YAHOO_CRYPTO.match(raw.upper()) else None
    if gecko_id is None:
        gecko_id = _YAHOO_TO_COINGECKO.get(raw.upper())
    coingecko: dict[str, Any] = {}
    if gecko_id:
        try:
            coingecko = fetch_coingecko_coin(gecko_id)
        except UpstreamFailure as exc:
            warnings.append(f"coingecko unavailable ({exc.kind}): {exc.message}")
            if exc.kind == ERROR_NOT_FOUND and raw.lower() not in COINGECKO_TO_YAHOO:
                result.update(error=f"unknown CoinGecko coin id '{coin_id}'", error_kind="not_found")
                return result
    result["coingecko"] = coingecko
    symbol, how = resolve_symbol(raw, coingecko)
    result["symbol"], result["symbol_source"] = symbol, how
    if symbol is None:
        result.update(error=f"cannot map '{coin_id}' to a Yahoo symbol", error_kind="unresolved")
        return result
    if how == "coingecko_symbol_unverified":
        warnings.append(f"{symbol} comes from the CoinGecko ticker; Yahoo may list another asset")

    hist, meta = data_provider.get_hist_with_meta(symbol, period=period)
    result["hist"], result["hist_meta"] = hist, meta
    if meta.error:
        warnings.append(f"yahoo bars unavailable ({meta.error_kind})")
    quote = data_provider.get_quote(symbol)
    result["quote"] = quote

    market = coingecko.get("market_data") or {}
    result["market_cap"] = (market.get("market_cap") or {}).get("usd")
    result["total_volume"] = (market.get("total_volume") or {}).get("usd")
    result["market_data_as_of"] = market.get("last_updated") or coingecko.get("last_updated")
    if quote.price is not None and symbol.endswith("-USD"):
        result.update(current_price_usd=quote.price, price_source=quote.source, price_as_of=quote.as_of)
    else:
        gecko_price = (market.get("current_price") or {}).get("usd")
        if gecko_price is not None:
            result.update(current_price_usd=float(gecko_price), price_source="coingecko:/coins",
                          price_as_of=result["market_data_as_of"])
            warnings.append("yahoo quote unavailable; CoinGecko price used")
    if result["current_price_usd"] is None and hist.empty:
        result.update(error=f"no price and no bars for {symbol}", error_kind=quote.error_kind or "upstream")
    return result
