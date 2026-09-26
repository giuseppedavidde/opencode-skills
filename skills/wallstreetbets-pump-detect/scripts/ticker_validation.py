#!/usr/bin/env python3
"""Phase 2 Step B ticker validation for the WSB pump-detect skill.

Candidates are validated against a bundled NASDAQ-trader universe
(`nasdaqlisted.txt` + `otherlisted.txt`) and, for symbols missing from that
universe, against yfinance as a fallback. The yfinance fallback runs inside the
shared trading venv (``~/.local/share/opencode/trading-mcp-venv``) instead of a
duplicate environment: the skill venv stays minimal and the existing yfinance
install is reused.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "TickerUniverse",
    "ValidatedTicker",
    "fetch_universe",
    "load_universe",
    "validate_candidates",
    "write_snapshot",
]

DATA_DIR = Path(__file__).resolve().parent / "data"
SNAPSHOT_FILE = DATA_DIR / "us_tickers.txt.gz"
META_FILE = DATA_DIR / "us_tickers.meta.json"
CACHE_DIR = Path(
    os.environ.get(
        "WSB_TICKER_CACHE_DIR",
        os.path.expanduser("~/.cache/opencode/wsb-pump-detect"),
    )
)
CACHE_FILE = CACHE_DIR / "us_tickers.txt.gz"
YF_CACHE_FILE = Path(
    os.environ.get("WSB_TICKER_YF_CACHE", "/tmp/opencode/wsb_ticker_cache.json")
)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
TRADING_VENV_PYTHON = os.path.expanduser(
    "~/.local/share/opencode/trading-mcp-venv/bin/python"
)

CACHE_TTL_SECONDS = 7 * 24 * 3600
YF_CACHE_TTL_SECONDS = 30 * 24 * 3600
HTTP_TIMEOUT_SECONDS = 30
YF_TIMEOUT_SECONDS = 45
MIN_TICKER_LEN = 2
MAX_TICKER_LEN = 5
DEFAULT_MAX_YFINANCE = 25
ACCEPTED_QUOTE_TYPES = frozenset({"EQUITY", "ETF"})

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,5}$")
_LEVERAGE_RE = re.compile(
    r"(\b(2X|3X|4X|1\.5X|2\.5X|-1X|-2X|-3X)\b"
    r"|\b(ULTRA|LEVERAGED|INVERSE|BULL|BEAR|SHORT|PROSHARES|DIREXION|DAILY)\b)",
    re.IGNORECASE,
)
_YF_SCRIPT = """
import json
import sys

try:
    import yfinance as yf
except Exception as exc:  # pragma: no cover - depends on external venv
    print(json.dumps({"_error": "yfinance unavailable: %s" % exc}))
    sys.exit(0)

symbols = json.load(sys.stdin)
accepted = {"EQUITY", "ETF"}
result = {}
for symbol in symbols:
    try:
        info = dict(yf.Ticker(symbol).info or {})
    except Exception:  # pragma: no cover - network failure path
        info = {}
    quote_type = str(info.get("quoteType") or "").upper()
    named = bool(info.get("symbol") or info.get("shortName") or info.get("longName"))
    valid = named and quote_type in accepted
    result[symbol] = {
        "valid": valid,
        "is_etf": quote_type == "ETF",
    }
print(json.dumps(result))
"""


class ValidatedTicker(BaseModel):
    """A candidate symbol confirmed as a listed US security."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    is_etf: bool = False
    is_leverage: bool = False
    source: str = "universe"


class TickerUniverse(BaseModel):
    """Static set of listed US symbols with ETF/leverage metadata."""

    model_config = ConfigDict(frozen=True)

    stocks: frozenset[str] = Field(default_factory=frozenset)
    etfs: frozenset[str] = Field(default_factory=frozenset)
    leverage: frozenset[str] = Field(default_factory=frozenset)
    source: str = "empty"
    fetched: str = ""

    def contains(self, symbol: str) -> bool:
        """Return True when ``symbol`` is a known stock or ETF."""
        return symbol in self.stocks or symbol in self.etfs

    def flag(self, symbol: str) -> ValidatedTicker:
        """Return the ETF/leverage metadata for a known ``symbol``."""
        return ValidatedTicker(
            symbol=symbol,
            is_etf=symbol in self.etfs,
            is_leverage=symbol in self.leverage,
            source="universe",
        )

    def __len__(self) -> int:
        return len(self.stocks) + len(self.etfs)


def _download(url: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> str:
    """Download ``url`` and return it decoded as UTF-8."""
    request = urllib.request.Request(url, headers={"User-Agent": "wsb-pump-detect/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _accumulate(
    text: str,
    stocks: set[str],
    etfs: set[str],
    leverage: set[str],
) -> None:
    """Merge one nasdaqtrader pipe-delimited listing into the given sets."""
    lines = text.splitlines()
    if not lines:
        return
    header = [column.strip() for column in lines[0].split("|")]
    try:
        symbol_index = (
            header.index("Symbol") if "Symbol" in header else header.index("ACT Symbol")
        )
        etf_index = header.index("ETF")
        test_index = header.index("Test Issue")
        name_index = header.index("Security Name")
    except ValueError:
        return
    limit = max(symbol_index, etf_index, test_index, name_index)
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) <= limit:
            continue
        symbol = parts[symbol_index].strip().upper()
        if not symbol or parts[test_index].strip().upper() == "Y":
            continue
        if not _SYMBOL_RE.match(symbol):
            continue
        if parts[etf_index].strip().upper() == "Y":
            etfs.add(symbol)
            if _LEVERAGE_RE.search(parts[name_index]):
                leverage.add(symbol)
        else:
            stocks.add(symbol)


def fetch_universe(timeout: int = HTTP_TIMEOUT_SECONDS) -> TickerUniverse:
    """Fetch the live nasdaqtrader listing files and build a universe."""
    stocks: set[str] = set()
    etfs: set[str] = set()
    leverage: set[str] = set()
    for url in (NASDAQ_LISTED_URL, OTHER_LISTED_URL):
        _accumulate(_download(url, timeout), stocks, etfs, leverage)
    stocks -= etfs
    leverage &= etfs
    return TickerUniverse(
        stocks=frozenset(stocks),
        etfs=frozenset(etfs),
        leverage=frozenset(leverage),
        source="nasdaqtrader.com SymDir nasdaqlisted.txt + otherlisted.txt",
        fetched=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


def _serialize(universe: TickerUniverse) -> bytes:
    """Serialize a universe to the compact plain-text snapshot format."""
    lines = [
        f"# source: {universe.source}",
        f"# fetched: {universe.fetched}",
        "# sections: STOCKS, ETFS, LEVERAGE (leveraged/inverse ETFs)",
        "STOCKS",
        *sorted(universe.stocks),
        "ETFS",
        *sorted(universe.etfs),
        "LEVERAGE",
        *sorted(universe.leverage),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _parse_snapshot(text: str, source: str, fetched: str) -> TickerUniverse:
    """Parse the compact snapshot format back into a universe."""
    stocks: set[str] = set()
    etfs: set[str] = set()
    leverage: set[str] = set()
    section = "STOCKS"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper in {"STOCKS", "ETFS", "LEVERAGE"}:
            section = upper
            continue
        if line.startswith("#"):
            lowered = line.lower()
            if lowered.startswith("# fetched:"):
                fetched = line.split(":", 1)[1].strip()
            elif lowered.startswith("# source:"):
                source = line.split(":", 1)[1].strip()
            continue
        if section == "LEVERAGE":
            leverage.add(upper)
        elif section == "ETFS":
            etfs.add(upper)
        else:
            stocks.add(upper)
    leverage &= etfs
    stocks -= etfs
    return TickerUniverse(
        stocks=frozenset(stocks),
        etfs=frozenset(etfs),
        leverage=frozenset(leverage),
        source=source,
        fetched=fetched,
    )


def _write_gz(path: Path, universe: TickerUniverse) -> None:
    """Write a gzip-compressed snapshot, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(_serialize(universe), 9))


def _load_snapshot(path: Path) -> TickerUniverse:
    """Load a gzip-compressed snapshot from disk."""
    text = gzip.decompress(path.read_bytes()).decode("utf-8")
    return _parse_snapshot(text, source=str(path), fetched="")


def _is_fresh(path: Path, ttl_seconds: int) -> bool:
    """Return True when ``path`` exists and is younger than ``ttl_seconds``."""
    try:
        return (time.time() - path.stat().st_mtime) < ttl_seconds
    except OSError:
        return False


def write_snapshot(
    universe: TickerUniverse | None = None,
    snapshot_path: Path = SNAPSHOT_FILE,
    meta_path: Path = META_FILE,
) -> TickerUniverse:
    """Persist ``universe`` (fetching if needed) as the bundled snapshot."""
    resolved = universe or fetch_universe()
    _write_gz(snapshot_path, resolved)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "source": resolved.source,
                "fetched": resolved.fetched,
                "stocks": len(resolved.stocks),
                "etfs": len(resolved.etfs),
                "leverage": len(resolved.leverage),
                "total": len(resolved),
                "generator": "scripts/ticker_validation.py --refresh-snapshot",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return resolved


def load_universe(
    refresh: bool = False,
    allow_network: bool | None = None,
) -> TickerUniverse:
    """Load the ticker universe (offline-bundled first, cache/network optional)."""
    online = (
        allow_network
        if allow_network is not None
        else os.environ.get("WSB_TICKER_OFFLINE") != "1"
    )
    if not refresh and _is_fresh(CACHE_FILE, CACHE_TTL_SECONDS):
        try:
            return _load_snapshot(CACHE_FILE)
        except (OSError, ValueError, EOFError):
            pass
    if not refresh and SNAPSHOT_FILE.exists():
        try:
            return _load_snapshot(SNAPSHOT_FILE)
        except (OSError, ValueError, EOFError):
            pass
    if online:
        try:
            universe = fetch_universe()
            _write_gz(CACHE_FILE, universe)
            return universe
        except (urllib.error.URLError, OSError, ValueError, EOFError):
            pass
    if SNAPSHOT_FILE.exists():
        try:
            return _load_snapshot(SNAPSHOT_FILE)
        except (OSError, ValueError, EOFError):
            pass
    if CACHE_FILE.exists():
        try:
            return _load_snapshot(CACHE_FILE)
        except (OSError, ValueError, EOFError):
            pass
    return TickerUniverse(source="empty")


def _normalize(candidates: Iterable[str]) -> list[str]:
    """Normalize candidates to unique, upper-case, plausible symbols."""
    seen: dict[str, None] = {}
    for candidate in candidates:
        symbol = str(candidate).strip().lstrip("$").upper()
        if not _SYMBOL_RE.match(symbol):
            continue
        if not MIN_TICKER_LEN <= len(symbol) <= MAX_TICKER_LEN:
            continue
        seen.setdefault(symbol, None)
    return list(seen)


def _load_yf_cache() -> dict[str, dict[str, object]]:
    """Load the persistent yfinance result cache, dropping stale entries."""
    try:
        raw = json.loads(YF_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time()
    cache: dict[str, dict[str, object]] = {}
    for symbol, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            fresh = (now - float(entry.get("ts", 0))) < YF_CACHE_TTL_SECONDS
        except (TypeError, ValueError):
            continue
        if fresh:
            cache[str(symbol)] = entry
    return cache


def _save_yf_cache(cache: dict[str, dict[str, object]]) -> None:
    """Persist the yfinance result cache, ignoring write failures."""
    try:
        YF_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        YF_CACHE_FILE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _query_yfinance(symbols: list[str], timeout: int) -> dict[str, dict[str, object]]:
    """Query yfinance for ``symbols`` inside the shared trading venv."""
    if not symbols or not os.path.exists(TRADING_VENV_PYTHON):
        return {}
    try:
        proc = subprocess.run(
            [TRADING_VENV_PYTHON, "-c", _YF_SCRIPT],
            input=json.dumps(symbols),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}
    if not isinstance(parsed, dict) or parsed.get("_error"):
        return {}
    return parsed


def validate_candidates(  # pylint: disable=too-many-locals
    candidates: Iterable[str],
    universe: TickerUniverse | None = None,
    use_yfinance: bool = True,
    yf_timeout: int = YF_TIMEOUT_SECONDS,
    max_yfinance: int = DEFAULT_MAX_YFINANCE,
) -> list[ValidatedTicker]:
    """Validate candidates, returning the confirmed symbols with ETF/leverage flags.

    The bundled universe resolves the vast majority of symbols offline; only
    symbols absent from it are checked through the yfinance fallback (batched,
    capped by ``max_yfinance`` and cached for ``YF_CACHE_TTL_SECONDS``). The
    fallback accepts only ``EQUITY``/``ETF`` quote types, so mutual funds and
    ECN quotes are rejected.
    """
    resolved = universe if universe is not None else load_universe()
    results: list[ValidatedTicker] = []
    unknown: list[str] = []
    for symbol in _normalize(candidates):
        if resolved.contains(symbol):
            results.append(resolved.flag(symbol))
        else:
            unknown.append(symbol)

    if use_yfinance and unknown:
        cache = _load_yf_cache()
        misses: list[str] = []
        for symbol in unknown:
            entry = cache.get(symbol)
            if entry is None:
                misses.append(symbol)
                continue
            if entry.get("valid"):
                results.append(
                    ValidatedTicker(
                        symbol=symbol,
                        is_etf=bool(entry.get("is_etf")),
                        source="yfinance",
                    )
                )
        if misses:
            queried = _query_yfinance(misses[:max_yfinance], yf_timeout)
            now = time.time()
            for symbol in misses[:max_yfinance]:
                info = queried.get(symbol, {})
                valid = bool(info.get("valid")) if isinstance(info, dict) else False
                cache[symbol] = {
                    "valid": valid,
                    "is_etf": bool(info.get("is_etf")) if isinstance(info, dict) else False,
                    "ts": now,
                }
                if valid:
                    results.append(
                        ValidatedTicker(
                            symbol=symbol,
                            is_etf=bool(info.get("is_etf")) if isinstance(info, dict) else False,
                            source="yfinance",
                        )
                    )
            _save_yf_cache(cache)

    return sorted(results, key=lambda item: item.symbol)


def _iter_results(results: list[ValidatedTicker]) -> Iterator[str]:
    """Yield formatted result lines for CLI output."""
    for item in results:
        flags = ",".join(
            flag
            for flag, active in (
                ("ETF", item.is_etf),
                ("LEVERAGE", item.is_leverage),
            )
            if active
        )
        yield f"{item.symbol}\t{flags or 'STOCK'}\t{item.source}"


def main() -> None:
    """Parse arguments and run validation or snapshot maintenance."""
    parser = argparse.ArgumentParser(
        description="Validate WSB ticker candidates against the US listing universe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 ticker_validation.py --validate AVGO goog TSLA TQQQ
  python3 ticker_validation.py --validate GME --json
  python3 ticker_validation.py --refresh-snapshot
  python3 ticker_validation.py --universe-stats
        """,
    )
    parser.add_argument("--validate", "-v", nargs="+", metavar="TICKER",
                        help="Validate the given candidate tickers")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Emit validation results as JSON")
    parser.add_argument("--refresh-snapshot", action="store_true",
                        help="Fetch the live nasdaqtrader list and rewrite the bundled snapshot")
    parser.add_argument("--refresh", action="store_true",
                        help="Force a network refresh of the runtime cache")
    parser.add_argument("--offline", action="store_true",
                        help="Never touch the network (bundled snapshot only)")
    parser.add_argument("--no-yfinance", action="store_true",
                        help="Skip the yfinance fallback")
    parser.add_argument("--universe-stats", action="store_true",
                        help="Print universe size and provenance")
    args = parser.parse_args()

    if args.refresh_snapshot:
        universe = write_snapshot()
        print(f"snapshot written: {SNAPSHOT_FILE} ({len(universe)} symbols)")
        return

    universe = load_universe(refresh=args.refresh, allow_network=not args.offline)

    if args.universe_stats:
        print(
            f"source={universe.source}\nfetched={universe.fetched}\n"
            f"stocks={len(universe.stocks)} etfs={len(universe.etfs)} "
            f"leverage={len(universe.leverage)} total={len(universe)}"
        )
        return

    if args.validate:
        results = validate_candidates(
            args.validate,
            universe=universe,
            use_yfinance=not args.no_yfinance and not args.offline,
        )
        if args.json:
            print(json.dumps([item.model_dump() for item in results], indent=2))
        else:
            for line in _iter_results(results):
                print(line)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
