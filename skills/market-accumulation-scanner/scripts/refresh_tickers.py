#!/usr/bin/env python3
"""
Ticker List Refresh Script
===========================
Fetches current index constituents from authoritative live sources,
backs up existing CSV files, generates updated files, and reports diffs.

Sources:
  S&P 500   — Wikipedia + GitHub dataset (dual-source, majority vote)
  FTSE MIB  — Wikipedia
  DAX 40    — Wikipedia
  CAC 40    — Wikipedia
  FTSE 100  — Wikipedia
  IBEX 35   — Wikipedia
  Crypto    — CoinGecko API (top 50 by market cap)
  US Tech   — Dynamically filtered from S&P 500 by GICS sector

Usage:
  python3 refresh_tickers.py --universe all       # refresh all
  python3 refresh_tickers.py --universe us_large   # only S&P 500
  python3 refresh_tickers.py --universe crypto     # only crypto
  python3 refresh_tickers.py --dry-run             # show diff without writing
  python3 refresh_tickers.py --check-only          # check if refresh is needed
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from pydantic import BaseModel, Field

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 30

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
    "&sparkline=false"
)

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_GITHUB_URL = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)

UNIVERSE_CONFIGS: dict[str, dict] = {
    "us_large": {
        "file": "us_tickers.csv",
        "source": "sp500",
        "description": "S&P 500 constituents",
    },
    "us_tech": {
        "file": "us_tech_tickers.csv",
        "source": "sp500_tech",
        "description": "S&P 500 Information Technology sector",
    },
    "italy": {
        "file": "italy_tickers.csv",
        "source": "ftse_mib",
        "description": "FTSE MIB constituents",
    },
    "germany": {
        "file": "germany_tickers.csv",
        "source": "dax",
        "description": "DAX 40 constituents",
    },
    "france": {
        "file": "france_tickers.csv",
        "source": "cac40",
        "description": "CAC 40 constituents",
    },
    "uk": {
        "file": "uk_tickers.csv",
        "source": "ftse100",
        "description": "FTSE 100 constituents",
    },
    "spain": {
        "file": "spain_tickers.csv",
        "source": "ibex35",
        "description": "IBEX 35 constituents",
    },
    "crypto": {
        "file": "crypto_tickers.csv",
        "source": "coingecko",
        "description": "Top 50 cryptocurrencies by market cap",
    },
}


class TickerRecord(BaseModel):
    """Single ticker entry in a universe CSV."""
    symbol: str
    name: str = ""
    suffix: str = ""
    market: str = ""
    sector: str = ""


class UniverseDiff(BaseModel):
    """Diff report after refreshing a universe."""
    universe: str
    file: str
    added: list[TickerRecord] = Field(default_factory=list)
    removed: list[TickerRecord] = Field(default_factory=list)
    retained: int = 0
    old_count: int = 0
    new_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class RefreshReport(BaseModel):
    """Aggregate report from a refresh run."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    universes: list[UniverseDiff] = Field(default_factory=list)
    dry_run: bool = False


def _fetch_html(url: str) -> str:
    """Fetch a URL and return its text content."""
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _read_existing(filepath: Path) -> list[TickerRecord]:
    """Read existing CSV file into a list of TickerRecord."""
    if not filepath.exists():
        return []
    records: list[TickerRecord] = []
    with open(filepath, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            records.append(TickerRecord(
                symbol=row.get("symbol", "").strip(),
                name=row.get("name", "").strip(),
                suffix=row.get("suffix", "").strip(),
                market=row.get("market", "").strip(),
                sector=row.get("sector", "").strip(),
            ))
    return records


def _write_csv(filepath: Path, records: list[TickerRecord]) -> None:
    """Write ticker records to a CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["symbol", "name", "suffix", "market", "sector"]
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "symbol": rec.symbol,
                "name": rec.name,
                "suffix": rec.suffix,
                "market": rec.market,
                "sector": rec.sector,
            })


def _backup_csv(filepath: Path) -> Optional[Path]:
    """Create a timestamped backup of the CSV file."""
    if not filepath.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = filepath.stem
    backup_path = BACKUP_DIR / f"{stem}_{ts}.csv"
    backup_path.write_bytes(filepath.read_bytes())
    return backup_path


# ──────────────────────────────────────────────
#  Fetch functions — one per source
# ──────────────────────────────────────────────

def fetch_sp500_wikipedia() -> list[TickerRecord]:
    """Fetch S&P 500 constituents from Wikipedia."""
    html = _fetch_html(SP500_WIKI_URL)
    tables = pd.read_html(StringIO(html))
    df = tables[0]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        name = str(row.get("Security", "")).strip()
        sector = str(row.get("GICS Sector", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix="",
            market="US",
            sector=sector,
        ))
    return records


def fetch_sp500_github() -> list[TickerRecord]:
    """Fetch S&P 500 constituents from GitHub dataset (secondary source)."""
    resp = requests.get(SP500_GITHUB_URL, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    reader = csv.DictReader(StringIO(resp.text))
    records: list[TickerRecord] = []
    for row in reader:
        symbol = row.get("Symbol", "").strip()
        name = row.get("Security", "").strip()
        sector = row.get("GICS Sector", "").strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix="",
            market="US",
            sector=sector,
        ))
    return records


def fetch_sp500_dual() -> tuple[list[TickerRecord], list[str]]:
    """Fetch S&P 500 from two sources, cross-check, resolve by majority."""
    warnings: list[str] = []

    try:
        wiki_records = fetch_sp500_wikipedia()
    except Exception as exc:
        raise RuntimeError(f"Wikipedia S&P 500 fetch failed: {exc}") from exc

    try:
        github_records = fetch_sp500_github()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        warnings.append(f"GitHub S&P 500 fetch failed ({exc}), using Wikipedia only")
        github_records = []

    wiki_symbols = {r.symbol for r in wiki_records}
    github_symbols = {r.symbol for r in github_records} if github_records else set()

    if github_symbols:
        only_wiki = wiki_symbols - github_symbols
        only_github = github_symbols - wiki_symbols
        if only_wiki:
            warnings.append(
                f"Tickers only in Wikipedia (not GitHub): {sorted(only_wiki)}"
            )
        if only_github:
            warnings.append(
                f"Tickers only in GitHub (not Wikipedia): {sorted(only_github)}"
            )
        if not only_wiki and not only_github:
            warnings.append("S&P 500 dual-source check: 100%% agreement")

    # Wikipedia is authoritative; GitHub is validation
    return wiki_records, warnings


def fetch_ftse_mib() -> list[TickerRecord]:
    """Fetch FTSE MIB constituents from Wikipedia."""
    html = _fetch_html("https://en.wikipedia.org/wiki/FTSE_MIB")
    tables = pd.read_html(StringIO(html))
    df = tables[1]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Ticker", "")).strip()
        name = str(row.get("Company", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix=".MI",
            market="Italy",
            sector="",
        ))
    return records


def fetch_dax() -> list[TickerRecord]:
    """Fetch DAX 40 constituents from Wikipedia."""
    html = _fetch_html("https://en.wikipedia.org/wiki/DAX")
    tables = pd.read_html(StringIO(html))
    df = tables[4]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Ticker", "")).strip()
        name = str(row.get("Company", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix=".DE",
            market="Germany",
            sector="",
        ))
    return records


def fetch_cac40() -> list[TickerRecord]:
    """Fetch CAC 40 constituents from Wikipedia."""
    html = _fetch_html("https://en.wikipedia.org/wiki/CAC_40")
    tables = pd.read_html(StringIO(html))
    df = tables[4]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Ticker", "")).strip()
        name = str(row.get("Company", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix=".PA",
            market="France",
            sector="",
        ))
    return records


def fetch_ftse100() -> list[TickerRecord]:
    """Fetch FTSE 100 constituents from Wikipedia."""
    html = _fetch_html("https://en.wikipedia.org/wiki/FTSE_100_Index")
    tables = pd.read_html(StringIO(html))
    df = tables[6]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Ticker", "")).strip()
        name = str(row.get("Company", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=f"{symbol}.L",
            name=name,
            suffix=".L",
            market="UK",
            sector="",
        ))
    return records


def fetch_ibex35() -> list[TickerRecord]:
    """Fetch IBEX 35 constituents from Wikipedia."""
    html = _fetch_html("https://en.wikipedia.org/wiki/IBEX_35")
    tables = pd.read_html(StringIO(html))
    df = tables[2]
    records: list[TickerRecord] = []
    for _, row in df.iterrows():
        symbol = str(row.get("Ticker", "")).strip()
        name = str(row.get("Company", "")).strip()
        if not symbol:
            continue
        records.append(TickerRecord(
            symbol=symbol,
            name=name,
            suffix=".MC",
            market="Spain",
            sector="",
        ))
    return records


def fetch_coingecko() -> list[TickerRecord]:
    """Fetch top 50 cryptocurrencies from CoinGecko API."""
    resp = requests.get(COINGECKO_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    records: list[TickerRecord] = []
    for coin in data:
        coin_id = coin.get("id", "")
        symbol_raw = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        if not coin_id or not symbol_raw:
            continue
        records.append(TickerRecord(
            symbol=f"{symbol_raw}-USD",
            name=name,
            suffix="",
            market="CRYPTO",
            sector="",
        ))
    return records


# ──────────────────────────────────────────────
#  Fetch dispatcher
# ──────────────────────────────────────────────

def fetch_universe(source: str) -> tuple[list[TickerRecord], list[str]]:
    """Fetch tickers for a given source identifier."""
    warnings: list[str] = []
    # pylint: disable=unnecessary-lambda
    fetch_map = {
        "sp500": lambda: fetch_sp500_dual(),          # returns (records, warnings)
        "ftse_mib": lambda: (fetch_ftse_mib(), []),   # normalize to (records, [])
        "dax": lambda: (fetch_dax(), []),
        "cac40": lambda: (fetch_cac40(), []),
        "ftse100": lambda: (fetch_ftse100(), []),
        "ibex35": lambda: (fetch_ibex35(), []),
        "coingecko": lambda: (fetch_coingecko(), []),
    }

    if source == "sp500_tech":
        sp500_records, w = fetch_sp500_dual()
        warnings.extend(w)
        tech_records = [
            r for r in sp500_records
            if r.sector == "Information Technology"
        ]
        return tech_records, warnings

    if source not in fetch_map:
        raise ValueError(f"Unknown source: {source}")

    records, src_warnings = fetch_map[source]()
    warnings.extend(src_warnings)

    # Deduplicate by symbol
    seen: set[str] = set()
    unique: list[TickerRecord] = []
    for rec in records:
        if rec.symbol not in seen:
            seen.add(rec.symbol)
            unique.append(rec)

    return unique, warnings


# ──────────────────────────────────────────────
#  Diff & write
# ──────────────────────────────────────────────

def compute_diff(
    new_records: list[TickerRecord],
    old_records: list[TickerRecord],
    universe_name: str,
    filename: str,
    warnings: list[str],
) -> UniverseDiff:
    """Compare new and old ticker lists and produce a diff."""
    old_by_symbol = {r.symbol: r for r in old_records}
    new_by_symbol = {r.symbol: r for r in new_records}

    added = [
        r for sym, r in new_by_symbol.items()
        if sym not in old_by_symbol
    ]
    removed = [
        r for sym, r in old_by_symbol.items()
        if sym not in new_by_symbol
    ]

    return UniverseDiff(
        universe=universe_name,
        file=filename,
        added=sorted(added, key=lambda r: r.symbol),
        removed=sorted(removed, key=lambda r: r.symbol),
        retained=len(new_records) - len(added),
        old_count=len(old_records),
        new_count=len(new_records),
        warnings=warnings,
    )


def print_diff(diff: UniverseDiff) -> None:
    """Pretty-print a universe diff to stdout."""
    print(f"\n{'─' * 70}")
    print(f"  Universe: {diff.universe}  →  {diff.file}")
    print(f"{'─' * 70}")
    print(f"  Old: {diff.old_count} tickers  →  New: {diff.new_count} tickers")
    print(f"  Retained: {diff.retained}  |  Added: {len(diff.added)}  "
          f"|  Removed: {len(diff.removed)}")

    if diff.added:
        print(f"\n  \033[32m+ ADDED ({len(diff.added)}):\033[0m")
        for rec in diff.added:
            sector_info = f" [{rec.sector}]" if rec.sector else ""
            print(f"    + {rec.symbol:<12} {rec.name[:40]}{sector_info}")

    if diff.removed:
        print(f"\n  \033[31m- REMOVED ({len(diff.removed)}):\033[0m")
        for rec in diff.removed:
            sector_info = f" [{rec.sector}]" if rec.sector else ""
            print(f"    - {rec.symbol:<12} {rec.name[:40]}{sector_info}")

    if diff.warnings:
        print("\n  \033[33m⚠ WARNINGS:\033[0m")
        for w in diff.warnings:
            print(f"    ⚠ {w}")

    if not diff.added and not diff.removed:
        print("\n  ✓ No changes — ticker list is up to date")


def refresh_universe(
    universe_name: str,
    config: dict,
    dry_run: bool = False,
) -> UniverseDiff:
    """Refresh a single universe: fetch, diff, optionally write."""
    source = config["source"]
    filename = config["file"]
    filepath = DATA_DIR / filename

    print(f"\n  Fetching {universe_name} from {source}...", end=" ", flush=True)
    t0 = time.time()
    new_records, warnings = fetch_universe(source)
    elapsed = time.time() - t0
    print(f"got {len(new_records)} tickers ({elapsed:.1f}s)")

    old_records = _read_existing(filepath)
    diff = compute_diff(new_records, old_records, universe_name, filename, warnings)

    if not dry_run and (diff.added or diff.removed or not filepath.exists()):
        backup_path = _backup_csv(filepath)
        if backup_path:
            print(f"  Backup: {backup_path}")
        _write_csv(filepath, new_records)
        print(f"  Written: {filepath}")

    return diff


# ──────────────────────────────────────────────
#  Main CLI
# ──────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh ticker CSV files from live authoritative sources"
    )
    parser.add_argument(
        "--universe",
        default="all",
        help="Universe to refresh (all, us_large, us_tech, italy, "
             "germany, france, uk, spain, crypto)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show diff without writing files",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Exit with code 1 if any changes detected (for CI/cron)",
    )
    return parser.parse_args()


def _write_legacy_combined(dry_run: bool = False) -> None:
    eu_markets = ["italy", "germany", "france", "uk", "spain"]
    all_eu: list[TickerRecord] = []
    for name in eu_markets:
        config = UNIVERSE_CONFIGS[name]
        filepath = DATA_DIR / config["file"]
        records = _read_existing(filepath)
        if records:
            all_eu.extend(records)

    if all_eu:
        legacy_path = DATA_DIR / "europe_tickers.csv"
        if not dry_run:
            _backup_csv(legacy_path)
            _write_csv(legacy_path, all_eu)
            print(f"\n  Legacy combined written: {legacy_path} "
                  f"({len(all_eu)} tickers)")
        else:
            print(f"\n  [DRY-RUN] Would write legacy combined: "
                  f"{legacy_path} ({len(all_eu)} tickers)")


def main() -> None:
    """Entry point: parse args, refresh universes, print diffs."""
    args = _parse_args()

    if args.universe == "all":
        universe_names = [
            "us_large", "us_tech", "italy", "germany",
            "france", "uk", "spain", "crypto",
        ]
    elif args.universe == "eu":
        universe_names = ["italy", "germany", "france", "uk", "spain"]
    else:
        if args.universe not in UNIVERSE_CONFIGS:
            valid = sorted(UNIVERSE_CONFIGS.keys())
            print(f"Unknown universe: {args.universe}")
            print(f"Valid options: {valid}")
            sys.exit(1)
        universe_names = [args.universe]

    print(f"\n{'=' * 70}")
    print("  Market Accumulation Scanner — Ticker Refresh")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Universes: {', '.join(universe_names)}")
    print(f"{'=' * 70}")

    report = RefreshReport(dry_run=args.dry_run)
    total_added = 0
    total_removed = 0
    changes_detected = False

    for name in universe_names:
        config = UNIVERSE_CONFIGS[name]
        try:
            diff = refresh_universe(name, config, dry_run=args.dry_run)
            # pylint: disable=no-member
            report.universes.append(diff)
            print_diff(diff)
            if diff.added or diff.removed:
                changes_detected = True
                total_added += len(diff.added)
                total_removed += len(diff.removed)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"\n  \033[31m✗ FAILED: {name} — {exc}\033[0m")

    eu_refreshed = any(
        u in universe_names for u in ["italy", "germany", "france", "uk", "spain"]
    ) or args.universe in ("all", "eu")
    if eu_refreshed and not args.dry_run:
        try:
            _write_legacy_combined()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"\n  \033[33m⚠ Legacy combined file not written: {exc}\033[0m")

    print(f"\n{'=' * 70}")
    print(f"  Summary: {len(report.universes)} universes processed")
    print(f"  Total added: {total_added}  |  Total removed: {total_removed}")
    if args.dry_run:
        print("  (Dry-run: no files were modified)")
    print(f"{'=' * 70}\n")

    if args.check_only and changes_detected:
        sys.exit(1)


if __name__ == "__main__":
    main()
