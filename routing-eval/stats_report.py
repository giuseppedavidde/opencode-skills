#!/usr/bin/env python3
"""CLI per la telemetria live del routing.

Uso:
    /routing-stats                  # mostra riepilogo globale
    /routing-stats --day 2026-08-09  # report per un giorno specifico
    /routing-stats --json            # output JSON invece della tabella
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from src.live_stats import (  # pylint: disable=no-name-in-module
    aggregate_by_day,
    build_summary_table,
    build_table_string,
    compute_global_summary,
    load_events,
    STATS_FILE_DEFAULT,
)

PROJECT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_DIR / "data" / "reports" / "live"


def save_json_report(data: dict, label: str) -> Path:
    """Salva il report JSON nella directory data/reports/live/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{label}_{ts}.json"
    path = REPORTS_DIR / filename
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    return path


def main() -> None:  # pylint: disable=missing-function-docstring
    parser = argparse.ArgumentParser(
        description="Routing telemetry: mostra statistiche delle delegazioni"
    )
    parser.add_argument(
        "--day", type=str, default=None,
        help="Filtra per giorno (YYYY-MM-DD). Default: tutti i giorni.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in formato JSON invece della tabella terminale.",
    )
    parser.add_argument(
        "--stats-file", type=str, default=None,
        help="Percorso alternativo al file JSONL.",
    )

    args = parser.parse_args()

    stats_path = Path(args.stats_file) if args.stats_file else STATS_FILE_DEFAULT
    events = load_events(stats_path)

    if not events:
        msg = (
            "nessun dato: il plugin non è attivo o non ci sono ancora delegazioni.\n"
            f"File atteso: {stats_path}\n"
        )
        if args.json:
            print(json.dumps({"error": msg.strip(), "total_events": 0}))
        else:
            print(f"\n⚠️  {msg}")
        sys.exit(0)

    target_day = date.fromisoformat(args.day) if args.day else None

    if target_day:
        day_reports = aggregate_by_day(events, target_day=target_day)
        if target_day not in day_reports:
            if args.json:
                print(json.dumps({
                    "day": target_day.isoformat(),
                    "total_delegations": 0,
                    "message": "nessuna delegazione in questa data"
                }))
            else:
                print(f"\n⚠️  Nessuna delegazione registrata per {target_day.isoformat()}")
            sys.exit(0)

        report = day_reports[target_day]
        data = report.model_dump()

        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        else:
            print(build_table_string(report))

        saved = save_json_report(data, f"day_{target_day.isoformat()}")
        sys.stderr.write(f"[report salvato → {saved}]\n")
    else:
        summary = compute_global_summary(events)

        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        else:
            print(build_summary_table(summary))

        saved = save_json_report(summary, "global")
        sys.stderr.write(f"[report salvato → {saved}]\n")


if __name__ == "__main__":
    main()
