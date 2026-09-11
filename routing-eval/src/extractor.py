"""Extract routing decisions from the OpenCode SQLite database.

Reads the DB read-only, extracts user queries and their actual routing
decisions (which subagent was delegated to or SIMPLE), and exports to JSONL.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from src.models import SessionRecord, SUBAGENT_MAP, RoutingLabel

DB_PATH = Path.home() / ".local/share/opencode/opencode.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "history_dataset.jsonl"
MAX_QUERY_CHARS = 500


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _get_session_user_query(conn: sqlite3.Connection, session_id: str) -> tuple[str, bool]:
    rows = conn.execute(
        """
        SELECT m.id as msg_id, p.data as part_data
        FROM message m
        JOIN part p ON p.message_id = m.id
        WHERE m.session_id = ?
          AND json_extract(m.data, '$.role') = 'user'
          AND json_extract(p.data, '$.type') = 'text'
        ORDER BY m.time_created ASC, p.time_created ASC
        """,
        (session_id,),
    ).fetchall()

    seen_msg_ids: set[str] = set()
    query_parts: list[str] = []
    truncated = False

    for row in rows:
        msg_id = row["msg_id"]
        if msg_id in seen_msg_ids:
            continue
        seen_msg_ids.add(msg_id)
        try:
            part = json.loads(row["part_data"])
        except (json.JSONDecodeError, TypeError):
            continue
        text = part.get("text", "")
        if text:
            query_parts.append(text)

    full_query = query_parts[0] if query_parts else ""
    if len(full_query) > MAX_QUERY_CHARS:
        full_query = full_query[:MAX_QUERY_CHARS]
        truncated = True
    return full_query, truncated


def _get_session_routing(
    conn: sqlite3.Connection, session_id: str
) -> tuple[RoutingLabel, Optional[str]]:
    rows = conn.execute(
        """
        SELECT p.data
        FROM part p
        WHERE p.session_id = ?
          AND json_extract(p.data, '$.type') = 'tool'
          AND json_extract(p.data, '$.tool') = 'task'
        ORDER BY p.time_created ASC
        LIMIT 20
        """,
        (session_id,),
    ).fetchall()

    for row in rows:
        try:
            part = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        state = part.get("state", {})
        inp = state.get("input", {}) if isinstance(state, dict) else {}
        subagent = inp.get("subagent_type") if isinstance(inp, dict) else None
        if subagent and isinstance(subagent, str):
            label = SUBAGENT_MAP.get(subagent)
            if label is not None:
                return label, subagent
    fallback = _agent_part_fallback(conn, session_id)
    if fallback is not None:
        return fallback, None
    return RoutingLabel.SIMPLE, None


def _agent_part_fallback(conn: sqlite3.Connection, session_id: str) -> Optional[RoutingLabel]:
    rows = conn.execute(
        """
        SELECT json_extract(p.data, '$.name') as agent_name
        FROM part p
        WHERE p.session_id = ?
          AND json_extract(p.data, '$.type') = 'agent'
        ORDER BY p.time_created ASC
        LIMIT 5
        """,
        (session_id,),
    ).fetchall()

    for row in rows:
        name = row["agent_name"]
        if name in SUBAGENT_MAP:
            return SUBAGENT_MAP[name]
    return None


def extract_dataset(
    db_path: str | None = None, output_path: str | None = None
) -> list[SessionRecord]:
    """Estrae il dataset storico dal DB e lo esporta in JSONL."""
    db_path = db_path or str(DB_PATH)
    output_path = output_path or str(OUTPUT_PATH)

    conn = _connect_readonly(db_path)
    records: list[SessionRecord] = []

    try:
        session_rows = conn.execute(
            """
            SELECT DISTINCT m.session_id, s.title, s.agent, s.model, s.time_created
            FROM message m
            JOIN session s ON s.id = m.session_id
            WHERE json_extract(m.data, '$.role') = 'user'
            ORDER BY s.time_created ASC
            """
        ).fetchall()

        for srow in session_rows:
            sid = srow["session_id"]
            user_query, truncated = _get_session_user_query(conn, sid)
            if not user_query:
                continue
            actual, subagent = _get_session_routing(conn, sid)
            records.append(
                SessionRecord(
                    session_id=sid,
                    title=srow["title"] or "",
                    agent=srow["agent"] or "",
                    model=srow["model"] or "",
                    time_created=srow["time_created"] or 0,
                    user_query=user_query,
                    actual_routing=actual,
                    actual_subagent=subagent,
                    query_truncated=truncated,
                )
            )
    finally:
        conn.close()

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.model_dump_json() + "\n")

    return records


if __name__ == "__main__":
    recs = extract_dataset()
    print(f"Extracted {len(recs)} session records → {OUTPUT_PATH}")
    labels = {}
    for r in recs:
        labels[r.actual_routing.value] = labels.get(r.actual_routing.value, 0) + 1
    for k, v in sorted(labels.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
