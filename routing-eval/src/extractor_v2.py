"""Message-level extractor: pairs each user message with its routing outcome.

Solves the session-evolution artefact: a session might start SIMPLE
and later delegate to a subagent. This extractor attaches the routing
decision to the single user message that triggered it.
"""

# pylint: disable=duplicate-code

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from src.models import RoutingLabel, SUBAGENT_MAP

DB_PATH = Path.home() / ".local/share/opencode/opencode.db"
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "message_dataset.jsonl"
)
MAX_QUERY_CHARS = 500


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_user_messages(conn: sqlite3.Connection, sid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT m.id as msg_id, p.data as part_data, m.time_created
        FROM message m
        JOIN part p ON p.message_id = m.id
        WHERE m.session_id = ?
          AND json_extract(m.data, '$.role') = 'user'
          AND json_extract(p.data, '$.type') = 'text'
        ORDER BY m.time_created ASC, p.time_created ASC
        """,
        (sid,),
    ).fetchall()

    messages: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        msg_id = row["msg_id"]
        if msg_id in seen_ids:
            continue
        seen_ids.add(msg_id)
        try:
            part = json.loads(row["part_data"])
        except (json.JSONDecodeError, TypeError):
            continue
        text = part.get("text", "")
        if text:
            messages.append({
                "msg_id": msg_id,
                "text": text,
                "time": row["time_created"],
            })
    return messages


def _fetch_task_events(conn: sqlite3.Connection, sid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT json_extract(p.data, '$.state') as state_data,
               p.time_created
        FROM part p
        WHERE p.session_id = ?
          AND json_extract(p.data, '$.type') = 'tool'
          AND json_extract(p.data, '$.tool') = 'task'
        ORDER BY p.time_created ASC
        """,
        (sid,),
    ).fetchall()

    events: list[dict] = []
    for row in rows:
        try:
            state = json.loads(row["state_data"])
        except (json.JSONDecodeError, TypeError):
            continue
        inp = state.get("input", {}) if isinstance(state, dict) else {}
        subagent = inp.get("subagent_type") if isinstance(inp, dict) else None
        if subagent and isinstance(subagent, str):
            events.append({
                "subagent": subagent,
                "time": row["time_created"],
            })
    return events


def _fetch_agent_events(conn: sqlite3.Connection, sid: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT json_extract(p.data, '$.name') as agent_name,
               p.time_created
        FROM part p
        WHERE p.session_id = ?
          AND json_extract(p.data, '$.type') = 'agent'
        ORDER BY p.time_created ASC
        """,
        (sid,),
    ).fetchall()

    events: list[dict] = []
    for row in rows:
        name = row["agent_name"]
        if name in SUBAGENT_MAP:
            events.append({
                "agent": name,
                "time": row["time_created"],
            })
    return events


def _find_routing_after(
    msg_time: int,
    next_msg_time: Optional[int],
    tasks: list[dict],
    agents: list[dict],
) -> tuple[str, str]:
    for t in tasks:
        if t["time"] > msg_time:
            if next_msg_time is None or t["time"] < next_msg_time:
                subagent = t["subagent"]
                label = SUBAGENT_MAP.get(subagent, RoutingLabel.OTHER)
                return label.value, f"task:{subagent}"
            break

    for a in agents:
        if a["time"] > msg_time:
            if next_msg_time is None or a["time"] < next_msg_time:
                agent_name = a["agent"]
                label = SUBAGENT_MAP.get(agent_name, RoutingLabel.SIMPLE)
                return label.value, f"agent:{agent_name}"
            break

    return "SIMPLE", "no-task-after"


def _process_session(  # pylint: disable=too-many-locals
    conn: sqlite3.Connection, sid: str, start_idx: int
) -> tuple[list[dict], int]:
    user_msgs = _fetch_user_messages(conn, sid)
    if not user_msgs:
        return [], start_idx

    tasks = _fetch_task_events(conn, sid)
    agents = _fetch_agent_events(conn, sid)

    records: list[dict] = []
    idx = start_idx
    for i, um in enumerate(user_msgs):
        msg_time = um["time"]
        next_time = user_msgs[i + 1]["time"] if i + 1 < len(user_msgs) else None

        decision, reason = _find_routing_after(msg_time, next_time, tasks, agents)

        text = um["text"]
        truncated = False
        if len(text) > MAX_QUERY_CHARS:
            text = text[:MAX_QUERY_CHARS]
            truncated = True

        idx += 1
        records.append({
            "id": idx,
            "session_id": sid,
            "text": text,
            "actual_routing": decision,
            "reason": reason,
            "truncated": truncated,
        })
    return records, idx


def extract_message_dataset(
    db_path: str | None = None, output_path: str | None = None
) -> list[dict]:
    """Estrae messaggi utente con la decisione di routing immediatamente successiva."""
    db_path = db_path or str(DB_PATH)
    output_path = output_path or str(OUTPUT_PATH)

    conn = _connect_readonly(db_path)
    all_records: list[dict] = []

    try:
        session_rows = conn.execute(
            """
            SELECT DISTINCT m.session_id
            FROM message m
            WHERE json_extract(m.data, '$.role') = 'user'
            ORDER BY m.session_id
            """
        ).fetchall()

        msg_idx = 0
        for srow in session_rows:
            sid = srow["session_id"]
            records, msg_idx = _process_session(conn, sid, msg_idx)
            all_records.extend(records)
    finally:
        conn.close()

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return all_records


if __name__ == "__main__":
    recs = extract_message_dataset()
    print(f"Extracted {len(recs)} message-level records -> {OUTPUT_PATH}")
    labels: dict[str, int] = {}
    for r in recs:
        lbl = r["actual_routing"]
        labels[lbl] = labels.get(lbl, 0) + 1
    for k, v in sorted(labels.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
