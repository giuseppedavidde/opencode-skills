#!/usr/bin/env python3
"""Unusual Options Activity (UOA) flow filter for market screening.

Pulls the Barchart unusual-options-activity feed via the ``opencli`` bridge,
downloads live spot prices with yfinance, and filters each signal by the
OTM distance configured by the user, size ("whale") notional, contract
volume, penny-stock price and time-to-expiration.

The OTM bands are NOT invented here: they mirror the source of truth in
``gen_report.py`` (~lines 356-385, ``auto_select_strikes``):

    * Put  — ideal band 12-22% OTM (optimum ~17%), hard bound strike in
      [spot*0.55, spot*0.96] i.e. 4% .. 45% OTM.
    * Call — ideal band 0-15% OTM (optimum ~5%), hard bound strike in
      [spot, spot*1.35] i.e. 0% .. 35% OTM.

The ideal bands are the CLI defaults (``--min-otm-put`` etc.); the hard
bounds are fixed constants below. Signals inside the ideal band are ranked
in the primary table, signals inside only the hard bound are shown in a
secondary "wide" section, and everything else (including ITM strikes) is
dropped.

The ``iv`` field returned by the Barchart bridge is anomalous (0.4%-11%)
and is intentionally NOT used for any decision — it is only carried through
for reference and a warning is printed.

Usage:
    python3 uoa_flow.py --limit 100
    python3 uoa_flow.py --limit 200 --min-notional 100000 --json-out reports/uoa.json
    python3 uoa_flow.py --limit 100 --scan-json reports/us_large_scan.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yfinance as yf
from pydantic import BaseModel

# ── Paths ────────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = SKILL_DIR / "reports"

# ── Hard OTM bounds (source of truth: gen_report.py auto_select_strikes) ──
PUT_HARD_OTM_MIN = 0.04   # strike >= spot * 0.96
PUT_HARD_OTM_MAX = 0.45   # strike <= spot * 0.55
CALL_HARD_OTM_MIN = 0.0   # strike >= spot
CALL_HARD_OTM_MAX = 0.35  # strike <= spot * 1.35

# Ideal bands (CLI defaults) also mirror gen_report.py.
PUT_OTM_IDEAL_MIN = 0.12
PUT_OTM_IDEAL_MAX = 0.22
CALL_OTM_IDEAL_MIN = 0.0
CALL_OTM_IDEAL_MAX = 0.15

CONTRACT_MULTIPLIER = 100
OPENCLI_TIMEOUT_SECONDS = 90

BRIDGE_HINT = (
    "Impossibile ottenere il feed UOA da Barchart.\n"
    "  Cause tipiche:\n"
    "  1) Il bridge browser opencli non e' connesso: apri Brave, attiva "
    "l'estensione\n"
    "     opencli ed effettua il login su www.barchart.com, poi riprova.\n"
    "  2) opencli non e' nel PATH (usa --opencli /percorso/opencli).\n"
    "  Verifica con: opencli doctor\n"
)


class FlowRecord(BaseModel):
    """Normalised Barchart UOA flow record (raw JSON mapped to snake_case)."""

    symbol: str
    opt_type: str
    strike: float
    expiration: str
    last: float
    volume: float
    open_interest: float
    vol_oi_ratio: float
    iv: str | None = None


class Signal(BaseModel):
    """Filtered, enriched UOA signal ready for output."""

    symbol: str
    opt_type: str
    strike: float
    expiration: str
    dte: int
    last: float
    volume: float
    open_interest: float
    vol_oi_ratio: float
    otm_pct: float
    spot: float
    notional: float
    band: str
    in_scan: bool = False
    scan_score: float | None = None
    iv: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────
def _to_float(value: Any) -> float | None:
    """Coerce a JSON scalar to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_flow_records(raw: list[dict]) -> list[FlowRecord]:
    """Convert raw Barchart JSON rows into validated FlowRecord objects."""
    records: list[FlowRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        strike = _to_float(item.get("strike"))
        if strike is None:
            continue
        symbol = str(item.get("symbol") or "").upper().strip()
        opt_type = str(item.get("type") or "").strip()
        expiration = str(item.get("expiration") or "").strip()
        if not symbol or opt_type not in ("Call", "Put"):
            continue
        iv_raw = item.get("iv")
        records.append(
            FlowRecord(
                symbol=symbol,
                opt_type=opt_type,
                strike=strike,
                expiration=expiration,
                last=_to_float(item.get("last")) or 0.0,
                volume=_to_float(item.get("volume")) or 0.0,
                open_interest=_to_float(item.get("openInterest")) or 0.0,
                vol_oi_ratio=_to_float(item.get("volOiRatio")) or 0.0,
                iv=str(iv_raw) if iv_raw not in (None, "") else None,
            )
        )
    return records


def run_opencli_flow(opencli: str, limit: int) -> list[dict]:
    """Run ``opencli barchart flow`` and return the parsed JSON list.

    Raises SystemExit with a clear bridge hint on any failure.
    """
    cmd = [opencli, "barchart", "flow", "--limit", str(limit), "-f", "json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=OPENCLI_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            f"opencli non trovato ('{opencli}'). Usa --opencli PATH.\n{BRIDGE_HINT}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"Timeout ({OPENCLI_TIMEOUT_SECONDS}s) durante la chiamata opencli.\n"
            f"{BRIDGE_HINT}"
        ) from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise SystemExit(
            f"opencli e' uscito con codice {proc.returncode}.\n"
            f"stderr: {stderr or '(vuoto)'}\n{BRIDGE_HINT}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Risposta opencli non e' JSON valido: {exc}\n{BRIDGE_HINT}"
        ) from exc

    if not isinstance(data, list):
        raise SystemExit(
            f"Risposta opencli inattesa (atteso array JSON): {type(data).__name__}\n"
            f"{BRIDGE_HINT}"
        )
    return data


def fetch_spots(symbols: list[str]) -> dict[str, float]:
    """Download latest spot price per symbol (batch yfinance, per-symbol fallback).

    Failures for a single ticker are swallowed; the caller flags those
    signals as "spot non disponibile" rather than crashing.
    """
    spots: dict[str, float] = {}
    uniq = sorted(set(symbols))
    if not uniq:
        return spots
    try:
        df = yf.download(
            uniq,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
        for sym in uniq:
            try:
                close = df[sym]["Close"].dropna()
                if not close.empty:
                    spots[sym] = float(close.iloc[-1])
            except (KeyError, IndexError, TypeError):
                continue
    except Exception:  # pylint: disable=broad-except
        pass  # fall through to per-symbol fetch

    for sym in uniq:
        if sym in spots:
            continue
        try:
            hist = yf.Ticker(sym).history(period="5d", interval="1d")
            if not hist.empty:
                spots[sym] = float(hist["Close"].dropna().iloc[-1])
        except Exception:  # pylint: disable=broad-except
            continue
    return spots


def compute_otm_pct(opt_type: str, strike: float, spot: float) -> float:
    """Return OTM distance as a fraction (0.17 == 17% OTM).

    Put:  (spot - strike) / spot   (positive when strike is below spot)
    Call: (strike - spot) / spot   (positive when strike is above spot)
    """
    if opt_type == "Put":
        return (spot - strike) / spot
    return (strike - spot) / spot


def _ideal_and_hard_bands(
    opt_type: str,
    min_otm_put: float,
    max_otm_put: float,
    min_otm_call: float,
    max_otm_call: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return ((ideal_lo, ideal_hi), (hard_lo, hard_hi)) for the option type."""
    if opt_type == "Put":
        return (min_otm_put, max_otm_put), (PUT_HARD_OTM_MIN, PUT_HARD_OTM_MAX)
    return (min_otm_call, max_otm_call), (CALL_HARD_OTM_MIN, CALL_HARD_OTM_MAX)


def classify_band(
    otm_pct: float,
    ideal: tuple[float, float],
    hard: tuple[float, float],
) -> str:
    """Return 'ideal', 'wide' or 'out' given the configured ideal bands.

    'ideal' -> inside the user's ideal OTM band (ranked highest).
    'wide'  -> inside the hard bound from gen_report.py but outside ideal.
    'out'   -> outside the hard bound (including ITM) — dropped.
    """
    if ideal[0] <= otm_pct <= ideal[1]:
        return "ideal"
    if hard[0] <= otm_pct <= hard[1]:
        return "wide"
    return "out"


def compute_dte(expiration: str, today: date) -> int | None:
    """Days-to-expiration, or None if the date is unparseable."""
    try:
        exp = datetime.strptime(expiration, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (exp - today).days


def load_scan_map(path: str) -> dict[str, float | None]:
    """Load scan_market results into {symbol: score}.

    Accepts a JSON array of dicts (key 'ticker' or 'symbol') or a dict with
    a 'results'/'tickers' list.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("results") or data.get("tickers") or []
    else:
        items = []
    scan_map: dict[str, float | None] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("ticker") or entry.get("symbol")
        if not symbol:
            continue
        score_raw = entry.get("final_score") or entry.get("score") or entry.get("finalScore")
        score = _to_float(score_raw)
        scan_map[str(symbol).upper()] = score
    return scan_map


def _filter_record(  # pylint: disable=too-many-return-statements
    rec: FlowRecord,
    spot: float | None,
    args: argparse.Namespace,
    scan_map: dict[str, float | None],
    today: date,
) -> tuple[Signal | None, str | None]:
    """Apply the noise + OTM filters to one record.

    Returns (signal, None) when the record survives, or (None, reason)
    when it is rejected.
    """
    if spot is None or spot <= 0:
        return None, "spot_non_disponibile"
    if spot < args.min_price:
        return None, "penny_stock"
    if rec.volume < args.min_volume:
        return None, "volume_basso"
    notional = rec.volume * rec.last * CONTRACT_MULTIPLIER
    if notional < args.min_notional:
        return None, "notional_basso"
    dte = compute_dte(rec.expiration, today)
    if dte is None or dte < args.dte_min or dte > args.dte_max:
        return None, "dte_fuori_finestra"
    otm_pct = compute_otm_pct(rec.opt_type, rec.strike, spot)
    ideal, hard = _ideal_and_hard_bands(
        rec.opt_type,
        args.min_otm_put,
        args.max_otm_put,
        args.min_otm_call,
        args.max_otm_call,
    )
    band = classify_band(otm_pct, ideal, hard)
    if band == "out":
        return None, "otm_fuori_banda"
    in_scan = rec.symbol in scan_map
    signal = Signal(
        symbol=rec.symbol,
        opt_type=rec.opt_type,
        strike=rec.strike,
        expiration=rec.expiration,
        dte=dte,
        last=rec.last,
        volume=rec.volume,
        open_interest=rec.open_interest,
        vol_oi_ratio=rec.vol_oi_ratio,
        otm_pct=otm_pct,
        spot=spot,
        notional=notional,
        band=band,
        in_scan=in_scan,
        scan_score=scan_map.get(rec.symbol) if in_scan else None,
        iv=rec.iv,
    )
    return signal, None


def build_signals(
    records: list[FlowRecord],
    spots: dict[str, float],
    args: argparse.Namespace,
    scan_map: dict[str, float | None],
    today: date,
) -> tuple[list[Signal], dict[str, int]]:
    """Apply all filters and enrich the surviving records into Signal objects."""
    signals: list[Signal] = []
    rejected: Counter[str] = Counter()
    for rec in records:
        signal, reason = _filter_record(rec, spots.get(rec.symbol), args, scan_map, today)
        if signal is None:
            rejected[reason] += 1
        else:
            signals.append(signal)
    return signals, dict(rejected)


def sort_signals(signals: list[Signal]) -> list[Signal]:
    """Rank: ideal band first, then in_scan first, then vol/OI ratio desc."""
    return sorted(
        signals,
        key=lambda s: (s.band != "ideal", not s.in_scan, -s.vol_oi_ratio),
    )


# ── Rendering ────────────────────────────────────────────────────────────
_HEADERS = [
    "Symbol",
    "Type",
    "Strike",
    "Exp",
    "DTE",
    "Last",
    "Vol",
    "OI",
    "Vol/OI",
    "OTM%",
    "Notional",
    "InScan",
]


def _fmt_cell(value: Any) -> str:
    return str(value)


def _render_table(signals: list[Signal], title: str, has_scan: bool) -> None:
    """Print a fixed-width terminal table of signals."""
    print(f"\n{title}")
    rows: list[list[str]] = []
    for sig in signals:
        rows.append(
            [
                sig.symbol,
                sig.opt_type,
                f"{sig.strike:.2f}",
                sig.expiration,
                str(sig.dte),
                f"{sig.last:.2f}",
                f"{sig.volume:,.0f}",
                f"{sig.open_interest:,.0f}",
                f"{sig.vol_oi_ratio:,.1f}",
                f"{sig.otm_pct * 100:.1f}%",
                f"${sig.notional:,.0f}",
                ("✓" if sig.in_scan else "·") if has_scan else "-",
            ]
        )
    widths = [
        max(len(header), *(len(row[i]) for row in rows))
        for i, header in enumerate(_HEADERS)
    ]
    header_line = "  ".join(
        _HEADERS[i].ljust(widths[i]) for i in range(len(_HEADERS))
    )
    print(header_line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(_fmt_cell(row[i]).ljust(widths[i]) for i in range(len(row))))
    print(f"  ({len(signals)} segnali)")


def _render_sections(signals: list[Signal], has_scan: bool) -> None:
    """Render the primary (ideal) and secondary (wide) tables."""
    ideal = [s for s in signals if s.band == "ideal"]
    wide = [s for s in signals if s.band == "wide"]
    if ideal:
        _render_table(ideal, "── BANDA IDEALE ──", has_scan)
    if wide:
        _render_table(
            wide,
            "── BANDA AMPIA (wide: dentro hard bound, fuori ottimale) ──",
            has_scan,
        )


def _print_summary(
    total_raw: int,
    signals: list[Signal],
    rejected: dict[str, int],
    scan_map: dict[str, float | None],
) -> None:
    """Print a compact summary block."""
    ideal = [s for s in signals if s.band == "ideal"]
    wide = [s for s in signals if s.band == "wide"]
    puts = [s for s in signals if s.opt_type == "Put"]
    calls = [s for s in signals if s.opt_type == "Call"]
    in_scan = [s for s in signals if s.in_scan]
    print("\n── RIEPILOGO ────────────────────────────────────────────────")
    print(f"  Feed raw      : {total_raw} record")
    print(
        f"  Dopo filtri   : {len(signals)} segnali "
        f"({len(ideal)} ideali + {len(wide)} wide)"
    )
    print(f"  Put / Call    : {len(puts)} / {len(calls)}")
    if scan_map:
        print(f"  In scan       : {len(in_scan)} intersezioni")
    print(
        "  Scartati      : "
        + ", ".join(f"{reason} {count}" for reason, count in sorted(rejected.items()))
        if rejected
        else "  Scartati      : nessuno"
    )


def _print_iv_warning() -> None:
    print(
        "\n⚠️  WARNING: il campo 'iv' del feed Barchart e' inaffidabile "
        "(valori anomali 0.4%-11%) e NON viene usato per alcuna decisione."
    )


# ── JSON output ──────────────────────────────────────────────────────────
def build_payload(
    args: argparse.Namespace,
    total_raw: int,
    signals: list[Signal],
) -> dict:
    """Assemble the structured JSON document for --json-out."""
    in_scan = [s for s in signals if s.in_scan]
    return {
        "timestamp": datetime.now().isoformat(),
        "query_params": {
            "limit": args.limit,
            "min_otm_put": args.min_otm_put,
            "max_otm_put": args.max_otm_put,
            "min_otm_call": args.min_otm_call,
            "max_otm_call": args.max_otm_call,
            "min_notional": args.min_notional,
            "min_volume": args.min_volume,
            "min_price": args.min_price,
            "dte_min": args.dte_min,
            "dte_max": args.dte_max,
            "scan_json": args.scan_json,
        },
        "total_raw": total_raw,
        "filtered": len(signals),
        "signals": [s.model_dump() for s in signals],
        "scan_intersection": [s.model_dump() for s in in_scan],
    }


def write_json_out(path: str, payload: dict) -> None:
    """Write the payload to disk, creating parent dirs."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── CLI ──────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse CLI arguments (ideal-band defaults mirror gen_report.py)."""
    parser = argparse.ArgumentParser(
        description="Filtra il feed UOA Barchart per distanze OTM configurate."
    )
    parser.add_argument("--limit", type=int, default=100, help="Record UOA da Barchart.")
    parser.add_argument(
        "--max-otm-put", type=float, default=PUT_OTM_IDEAL_MAX,
        help="OTM max put (default 0.22).",
    )
    parser.add_argument(
        "--min-otm-put", type=float, default=PUT_OTM_IDEAL_MIN,
        help="OTM min put (default 0.12).",
    )
    parser.add_argument(
        "--max-otm-call", type=float, default=CALL_OTM_IDEAL_MAX,
        help="OTM max call (default 0.15).",
    )
    parser.add_argument(
        "--min-otm-call", type=float, default=CALL_OTM_IDEAL_MIN,
        help="OTM min call (default 0.0).",
    )
    parser.add_argument(
        "--min-notional", type=float, default=50000.0,
        help="Soglia notional = volume*last*100 (default 50000).",
    )
    parser.add_argument(
        "--min-volume", type=float, default=100.0,
        help="Contratti minimi (default 100).",
    )
    parser.add_argument(
        "--min-price", type=float, default=5.0,
        help="Esclude penny stock sotto questo spot (default 5.0).",
    )
    parser.add_argument(
        "--dte-min", type=int, default=3,
        help="DTE minimo (default 3).",
    )
    parser.add_argument(
        "--dte-max", type=int, default=120,
        help="DTE massimo (default 120).",
    )
    parser.add_argument(
        "--scan-json", type=str, default=None,
        help="File JSON con risultati scan_market per incrocio.",
    )
    parser.add_argument(
        "--json-out", type=str, default=None,
        help="Salva output strutturato in questo file JSON.",
    )
    parser.add_argument(
        "--opencli", type=str, default=None,
        help="Percorso del binario opencli (default: quello in PATH).",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point."""
    args = parse_args()
    opencli = args.opencli or shutil.which("opencli") or "opencli"

    raw = run_opencli_flow(opencli, args.limit)
    records = parse_flow_records(raw)
    symbols = sorted({rec.symbol for rec in records})
    spots = fetch_spots(symbols)
    scan_map = load_scan_map(args.scan_json) if args.scan_json else {}
    today = date.today()

    signals, rejected = build_signals(records, spots, args, scan_map, today)
    signals = sort_signals(signals)
    has_scan = bool(scan_map)

    if args.json_out:
        write_json_out(args.json_out, build_payload(args, len(raw), signals))

    if not signals:
        print("Nessun segnale UOA supera i filtri configurati.")
        _print_summary(len(raw), signals, rejected, scan_map)
        _print_iv_warning()
    else:
        _render_sections(signals, has_scan)
        _print_summary(len(raw), signals, rejected, scan_map)
        _print_iv_warning()

    if args.json_out:
        print(f"\n💾 Output JSON salvato: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
