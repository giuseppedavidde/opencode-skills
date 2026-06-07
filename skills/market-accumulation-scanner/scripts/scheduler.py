#!/usr/bin/env python3
"""
Cron-based scheduler for market-accumulation-scanner runs.

Manages crontab entries that periodically scan US and European markets
and update the watchlist with fresh scores.

Usage:
    python3 scheduler.py --setup       # Create crontab entries
    python3 scheduler.py --status      # Show scheduled scanner runs
    python3 scheduler.py --remove      # Remove all scanner scheduling
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

MARKER = "# opencode-scanner"
SCANNER_SCRIPT = "scripts/scanner.py"
WATCHLIST_SCRIPT = "scripts/watchlist_update.py"

COMMENT_HEADER = f"\n# Market Accumulation Scanner — auto-generated entries {MARKER}\n"

CRON_ENTRIES = [
    "30 22 * * 1-5  # US large + US tech (after market close) {marker}",
    "30 18 * * 1-5  # EU markets (after European close) {marker}",
    "0 10 * * 6     # Weekly watchlist update + alerts {marker}",
]


def detect_scanner_dir() -> Path:
    """Return the absolute path to the skill root directory."""
    return Path(__file__).resolve().parent.parent


def build_cron_lines(scanner_dir: Path) -> list[str]:
    """Build the full crontab lines with absolute paths and commands."""
    scanner_path = scanner_dir / SCANNER_SCRIPT
    watchlist_path = scanner_dir / WATCHLIST_SCRIPT
    reports_base = scanner_dir / "reports"

    lines = [COMMENT_HEADER]

    # Entry 1: US scan (large + tech) weekdays at 22:30 CET
    lines.append(
        f"30 22 * * 1-5  "
        f"cd {scanner_dir} && "
        f"python3 {scanner_path} --universe us_large --min-score 50 --top 15 "
        f"--output-dir {reports_base / 'us_large'} "
        f"&& python3 {scanner_path} --universe us_tech --min-score 50 --top 15 "
        f"--output-dir {reports_base / 'us_tech'} "
        f"{MARKER}"
    )

    # Entry 2: EU markets weekdays at 18:30 CET
    eu_markets = ["italy", "germany", "france", "uk", "spain"]
    eu_cmds = " && ".join(
        f"python3 {scanner_path} --universe {m} --min-score 50 --top 15 "
        f"--output-dir {reports_base / m}"
        for m in eu_markets
    )
    lines.append(
        f"30 18 * * 1-5  "
        f"cd {scanner_dir} && {eu_cmds} "
        f"{MARKER}"
    )

    # Entry 3: Weekly watchlist update Saturday at 10:00 CET
    lines.append(
        f"0 10 * * 6     "
        f"cd {scanner_dir} && "
        f"python3 {watchlist_path} "
        f"{MARKER}"
    )

    lines.append("")
    return lines


def get_current_crontab() -> str:
    """Read the current user's crontab. Returns empty string if none exists."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"Error reading crontab: {exc}", file=sys.stderr)
        sys.exit(1)


def write_crontab(content: str) -> None:
    """Write content to the user's crontab via stdin."""
    try:
        result = subprocess.run(
            ["crontab", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"Error writing crontab: {result.stderr}", file=sys.stderr)
            sys.exit(1)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"Error writing crontab: {exc}", file=sys.stderr)
        sys.exit(1)


def has_scanner_entries(crontab: str) -> bool:
    """Check whether the crontab already contains scanner entries."""
    return MARKER in crontab


def remove_scanner_entries(crontab: str) -> str:
    """Remove all lines containing the scanner marker."""
    lines = crontab.splitlines()
    filtered: list[str] = []

    skip_block = False
    for line in lines:
        if line.startswith("# Market Accumulation Scanner") and MARKER in line:
            skip_block = True
            continue
        if skip_block:
            if MARKER in line or line.strip() == "":
                continue
            skip_block = False
        if MARKER in line:
            continue
        filtered.append(line)

    return "\n".join(filtered).strip() + "\n" if filtered else ""


def cmd_setup(scanner_dir: Path) -> None:
    """Add scanner cron entries to the current crontab."""
    current = get_current_crontab()

    if has_scanner_entries(current):
        print("Scanner entries already present in crontab.")
        print("Use --status to view them or --remove to clear them first.")
        return

    new_lines = build_cron_lines(scanner_dir)
    new_content = current.rstrip("\n") + "\n\n" + "".join(new_lines)
    write_crontab(new_content)

    print(f"\n{'=' * 60}")
    print("  Market Accumulation Scanner — CRON SCHEDULING INSTALLED")
    print(f"{'=' * 60}")
    print()
    print(f"  Skill directory: {scanner_dir}")
    print()
    print("  Scheduled runs (CET times):")
    print("  ───────────────────────────────────────────────────")
    print("  Weekdays 22:30  →  US large + US tech")
    print("  Weekdays 18:30  →  EU markets (Italy, Germany, France, UK, Spain)")
    print("  Saturday  10:00  →  Watchlist update + alerts")
    print()
    print("  Reports saved under: reports/<universe>/")
    print()
    print("  Use --status to verify, --remove to uninstall.")
    print(f"{'=' * 60}\n")


def cmd_status() -> None:
    """Show currently scheduled scanner entries."""
    current = get_current_crontab()

    if not has_scanner_entries(current):
        print("No scanner entries found in crontab.")
        print("Use --setup to add them.")
        return

    lines = current.splitlines()
    scanner_lines = [ln for ln in lines if MARKER in ln]

    print(f"\n{'=' * 60}")
    print("  Market Accumulation Scanner — SCHEDULED RUNS")
    print(f"{'=' * 60}\n")
    print(f"  Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Total scanner entries: {len(scanner_lines)}\n")
    print("  ───────────────────────────────────────────────────")

    for idx, line in enumerate(scanner_lines, 1):
        clean = line.replace(f" {MARKER}", "")
        stripped = clean.strip()
        if stripped.startswith("cd "):
            parts = stripped.split(" && ")
            schedule = parts[0].split(" ", 5) if " " in parts[0] else []
            cron_parts = []
            extra = ""
            for segment in parts[0].split(" "):
                if not cron_parts and segment in ("#", ""):
                    continue
                cron_parts.append(segment)
                if len(cron_parts) == 5:
                    break
            if len(cron_parts) == 5:
                schedule = " ".join(cron_parts)
                extra = parts[0].split(" ", 5)[-1].strip()
            else:
                schedule = parts[0].strip()
                extra = ""
            commands = [c.strip() for c in parts[1:]]

            hour = cron_parts[1] if len(cron_parts) > 1 else "?"
            minute = cron_parts[0] if len(cron_parts) > 0 else "?"
            days = cron_parts[4] if len(cron_parts) > 4 else "?"

            day_desc = _cron_day_description(days)
            time_desc = f"{hour.lstrip('0') or '0'}:{minute.zfill(2)} CET"

            print(f"\n  Entry {idx}: {day_desc} at {time_desc}")
            for cmd in commands:
                short = cmd.replace(str(Path(".").resolve()), ".")
                if len(short) > 70:
                    short = short[:67] + "..."
                print(f"    → {short}")

    print(f"\n{'=' * 60}\n")


def _cron_day_description(day_field: str) -> str:
    """Convert a cron day-of-week field to a human-readable description."""
    if day_field == "*":
        return "Every day"
    if day_field == "1-5":
        return "Weekdays (Mon-Fri)"
    if day_field == "6":
        return "Saturday"
    if day_field == "0" or day_field == "7":
        return "Sunday"
    return f"Days={day_field}"


def cmd_remove() -> None:
    """Remove all scanner-related entries from crontab."""
    current = get_current_crontab()

    if not has_scanner_entries(current):
        print("No scanner entries found in crontab. Nothing to remove.")
        return

    cleaned = remove_scanner_entries(current)
    write_crontab(cleaned)
    print("All scanner-related crontab entries have been removed.")
    print("Use --setup to add them again.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage cron scheduling for market-accumulation-scanner"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--setup",
        action="store_true",
        help="Create crontab entries for scanner runs",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Show currently scheduled scanner runs",
    )
    group.add_argument(
        "--remove",
        action="store_true",
        help="Remove all scanner-related entries from crontab",
    )
    args = parser.parse_args()

    scanner_dir = detect_scanner_dir()
    if not scanner_dir.exists():
        print(f"Error: scanner directory not found: {scanner_dir}", file=sys.stderr)
        sys.exit(1)

    scanner_script = scanner_dir / SCANNER_SCRIPT
    if not scanner_script.exists() and args.setup:
        print(f"Error: scanner script not found: {scanner_script}", file=sys.stderr)
        sys.exit(1)

    if args.setup:
        cmd_setup(scanner_dir)
    elif args.status:
        cmd_status()
    elif args.remove:
        cmd_remove()


if __name__ == "__main__":
    main()
