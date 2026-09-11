"""Aggregatore telemetria routing: legge routing_events.jsonl e produce statistiche.

Fornisce funzioni per aggregare per giorno e per tipo di subagent,
con join opzionale sul DB sessioni per dati di costo.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

from pydantic import BaseModel, Field

STATS_DIR_DEFAULT = Path.home() / ".config" / "opencode" / "stats"
STATS_FILE_DEFAULT = STATS_DIR_DEFAULT / "routing_events.jsonl"
DB_PATH_DEFAULT = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


class RoutingEvent(BaseModel):
    """Singolo evento di delegazione registrato dal plugin."""

    ts: str
    subagent_type: str
    prompt_snippet: str
    has_verifica: bool
    confidenza: Optional[int] = None
    escalation_consigliata: Optional[bool] = None

    @property
    def date(self) -> date:
        """Data dell'evento (componente YYYY-MM-DD)."""
        return datetime.fromisoformat(self.ts).date()


class SubagentStats(BaseModel):
    """Statistiche aggregate per un tipo di subagent."""

    count: int = 0
    has_verifica_count: int = 0
    has_verifica_pct: float = 0.0
    confidenza_values: list[int] = Field(default_factory=list)
    confidenza_mean: Optional[float] = None
    escalation_yes_count: int = 0
    confidenza_lt40_count: int = 0

    _valid_confidenza: bool = False

    def add(self, event: RoutingEvent) -> None:
        """Aggiunge un evento alle statistiche."""
        self.count += 1
        if event.has_verifica:
            self.has_verifica_count += 1
        if event.confidenza is not None:
            self.confidenza_values.append(event.confidenza)  # pylint: disable=no-member
            if event.confidenza < 40:
                self.confidenza_lt40_count += 1
        if event.escalation_consigliata is True:
            self.escalation_yes_count += 1

    def finalize(self) -> None:  # pylint: disable=missing-function-docstring
        if self.count > 0:
            self.has_verifica_pct = round(self.has_verifica_count / self.count * 100, 1)
        if self.confidenza_values:
            self.confidenza_mean = round(
                sum(self.confidenza_values) / len(self.confidenza_values), 1
            )


class DayReport(BaseModel):
    """Report aggregato per un giorno."""

    day: date
    total_delegations: int = 0
    by_subagent: dict[str, SubagentStats] = Field(default_factory=dict)
    overall_verifica_pct: float = 0.0
    overall_confidenza_mean: Optional[float] = None
    overall_escalation_pct: float = 0.0
    cost_data: Optional[dict[str, float]] = None


def load_events(stats_file: Path | None = None) -> list[RoutingEvent]:
    """Carica tutti gli eventi dal file JSONL.

    Args:
        stats_file: Percorso al file JSONL. Default: ~/.config/opencode/stats/routing_events.jsonl

    Returns:
        Lista di RoutingEvent. Lista vuota se il file non esiste.
    """
    path = stats_file or STATS_FILE_DEFAULT
    if not path.exists():
        return []
    events: list[RoutingEvent] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(RoutingEvent.model_validate_json(line))
            except (ValueError, KeyError):
                continue
    return events


def aggregate_by_day(events: Sequence[RoutingEvent],
                     target_day: date | None = None,
                     ) -> dict[date, DayReport]:
    """Aggrega eventi per giorno.

    Args:
        events: Lista di eventi di routing.
        target_day: Se specificato, restituisce solo quel giorno.

    Returns:
        Dizionario data -> DayReport.
    """
    days: dict[date, list[RoutingEvent]] = defaultdict(list)
    for ev in events:
        if target_day and ev.date != target_day:
            continue
        days[ev.date].append(ev)

    reports: dict[date, DayReport] = {}
    for day_val, day_events in days.items():
        report = DayReport(day=day_val, total_delegations=len(day_events))
        for ev in day_events:
            sub = ev.subagent_type
            if sub not in report.by_subagent:
                report.by_subagent[sub] = SubagentStats()
            report.by_subagent[sub].add(ev)

        total_verifica = sum(
            s.has_verifica_count for s in report.by_subagent.values()  # pylint: disable=no-member
        )
        if report.total_delegations > 0:
            report.overall_verifica_pct = round(
                total_verifica / report.total_delegations * 100, 1
            )

        all_conf_values: list[int] = []
        for s in report.by_subagent.values():  # pylint: disable=no-member
            s.finalize()
            all_conf_values.extend(s.confidenza_values)  # pylint: disable=no-member
        if all_conf_values:
            report.overall_confidenza_mean = round(
                sum(all_conf_values) / len(all_conf_values), 1
            )

        total_esc = sum(
            s.escalation_yes_count for s in report.by_subagent.values()  # pylint: disable=no-member
        )
        if report.total_delegations > 0:
            report.overall_escalation_pct = round(
                total_esc / report.total_delegations * 100, 1
            )

        reports[day_val] = report

    return reports


def fetch_session_costs(db_path: Path | None = None,
                        target_day: date | None = None) -> dict[str, dict[str, float]]:
    """Legge il DB sessioni (READ-ONLY) per estrarre costi per sessione.

    Args:
        db_path: Percorso al DB. Default: ~/.local/share/opencode/opencode.db
        target_day: Filtra per giorno (created_at).

    Returns:
        Dizionario session_id -> {tokens_input, tokens_output, cost}.
        Vuoto se il DB non esiste o non è accessibile.
    """
    path = db_path or DB_PATH_DEFAULT
    if not path.exists():
        return {}

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return {}

    try:
        cur = conn.cursor()
        if target_day:
            day_str = target_day.isoformat()
            cur.execute(
                """SELECT id, tokens_input, tokens_output, cost
                   FROM sessions
                   WHERE date(created_at) = ?""",
                (day_str,),
            )
        else:
            cur.execute(
                "SELECT id, tokens_input, tokens_output, cost FROM sessions"
            )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {}
    finally:
        conn.close()

    costs: dict[str, dict[str, float]] = {}
    for row in rows:
        sid, tin, tout, cost = row
        costs[sid] = {
            "tokens_input": tin or 0,
            "tokens_output": tout or 0,
            "cost": cost or 0.0,
        }
    return costs


def compute_global_summary(events: Sequence[RoutingEvent],
                           ) -> dict:
    """Riepilogo globale su tutti gli eventi disponibili.

    Returns:
        Dizionario con totali, distribuzione per subagent e trend.
    """
    total = len(events)
    if total == 0:
        return {"total_events": 0, "message": "nessun evento registrato"}

    by_sub: dict[str, SubagentStats] = {}
    days_set: set[str] = set()
    for ev in events:
        sub = ev.subagent_type
        if sub not in by_sub:
            by_sub[sub] = SubagentStats()
        by_sub[sub].add(ev)
        days_set.add(ev.date.isoformat())

    summary: dict = {
        "total_events": total,
        "days_with_activity": len(days_set),
        "by_subagent": {},
    }

    total_verifica = 0
    total_esc = 0
    all_conf: list[int] = []
    for sub, stats in by_sub.items():
        stats.finalize()
        summary["by_subagent"][sub] = stats.model_dump()
        total_verifica += stats.has_verifica_count
        total_esc += stats.escalation_yes_count
        all_conf.extend(stats.confidenza_values)

    summary["overall_verifica_pct"] = (
        round(total_verifica / total * 100, 1) if total > 0 else 0.0
    )
    summary["overall_confidenza_mean"] = (
        round(sum(all_conf) / len(all_conf), 1) if all_conf else None
    )
    summary["overall_escalation_pct"] = (
        round(total_esc / total * 100, 1) if total > 0 else 0.0
    )
    summary["confidenza_lt40_total"] = sum(
        s.confidenza_lt40_count for s in by_sub.values()
    )

    return summary


def build_table_string(report: DayReport) -> str:
    """Costruisce una tabella terminale da un DayReport."""
    lines: list[str] = []
    sep = "─" * 72
    lines.append(f"\n╭{sep}╮")
    lines.append(f"│ 📊 ROUTING STATS — {report.day.isoformat()}".ljust(75) + "│")
    lines.append(f"├{'─' * 72}┤")
    lines.append(f"│ Delegazioni totali: {report.total_delegations:>47d} │")
    lines.append(f"│ Blocco VERIFICA presente: {report.overall_verifica_pct:.1f}%".ljust(75) + "│")
    conf_str = f"{report.overall_confidenza_mean:.1f}" if report.overall_confidenza_mean else "N/A"
    lines.append(f"│ Confidenza media: {conf_str:>51s} │")
    lines.append(f"│ Escalation consigliata: {report.overall_escalation_pct:.1f}%".ljust(75) + "│")

    if report.cost_data:
        lines.append(f"├{'─' * 72}┤")
        lines.append("│ 💰 COSTI STIMATI (dal DB sessioni)".ljust(75) + "│")
        for k, v in report.cost_data.items():
            lines.append(f"│   {k}: {v}".ljust(75) + "│")

    lines.append(f"├{'─' * 72}┤")
    lines.append("│ PER SUBAGENT".ljust(75) + "│")
    header = "│ SUBAGENT                #  VERIFICA%  CONF_μ  ESCAL   C<40 │"
    lines.append(header)
    lines.append(f"│ {'─'*20} {'─'*5} {'─'*9} {'─'*7} {'─'*5} {'─'*5} │")

    for sub, stats in sorted(report.by_subagent.items()):
        conf_str = f"{stats.confidenza_mean:.1f}" if stats.confidenza_mean else "N/A"
        lines.append(
            f"│ {sub:<20} {stats.count:>5} " +
            f"{stats.has_verifica_pct:>8.1f}% " +
            f"{conf_str:>7} " +
            f"{stats.escalation_yes_count:>5} " +
            f"{stats.confidenza_lt40_count:>5} │"
        )

    lines.append(f"╰{sep}╯")
    return "\n".join(lines) + "\n"


def build_summary_table(summary: dict) -> str:
    """Costruisce una tabella riepilogativa globale."""
    if summary.get("total_events", 0) == 0:
        return (
            "\n╭──────────────────────────────────────────────────────────────────────╮\n"
            "│ ⚠️  Nessun dato: il plugin non è attivo o non ci sono ancora       │\n"
            "│    delegazioni registrate.                                           │\n"
            "╰──────────────────────────────────────────────────────────────────────╯\n"
        )

    lines: list[str] = []
    sep = "─" * 72
    lines.append(f"\n╭{sep}╮")
    lines.append("│ 📊 ROUTING TELEMETRY — RIEPILOGO GLOBALE".ljust(75) + "│")
    lines.append(f"├{'─' * 72}┤")
    lines.append(f"│ Eventi totali: {summary['total_events']:>49d} │")
    lines.append(f"│ Giorni con attività: {summary['days_with_activity']:>43d} │")
    lines.append(f"│ Blocco VERIFICA: {summary['overall_verifica_pct']:.1f}%".ljust(75) + "│")
    conf_str = (
        f"{summary['overall_confidenza_mean']:.1f}"
        if summary.get("overall_confidenza_mean") else "N/A"
    )
    lines.append(f"│ Confidenza media: {conf_str:>51s} │")
    lines.append(
        f"│ Escalation consigliate: {summary['overall_escalation_pct']:.1f}%".ljust(75) + "│"
    )
    lines.append(f"│ Confidenza <40: {summary.get('confidenza_lt40_total', 0):>50d} │")

    lines.append(f"├{'─' * 72}┤")
    lines.append("│ PER SUBAGENT".ljust(75) + "│")
    lines.append("│ SUBAGENT                #  VERIFICA%  CONF_μ  ESCAL   C<40 │")
    sep_line = (
        "│ " + "─" * 20 + " " + "─" * 5 + " " + "─" * 9
        + " " + "─" * 7 + " " + "─" * 5 + " " + "─" * 5 + " │"
    )
    lines.append(sep_line)

    for sub, stats in sorted(summary.get("by_subagent", {}).items()):
        conf_str = f"{stats['confidenza_mean']:.1f}" if stats.get("confidenza_mean") else "N/A"
        lines.append(
            f"│ {sub:<20} {stats['count']:>5} "
            f"{stats['has_verifica_pct']:>8.1f}% "
            f"{conf_str:>7} "
            f"{stats['escalation_yes_count']:>5} "
            f"{stats['confidenza_lt40_count']:>5} │"
        )

    lines.append(f"╰{sep}╯")
    return "\n".join(lines) + "\n"
