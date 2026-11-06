# pylint: disable=import-outside-toplevel
"""A/B outcome harness: does the MCP answer stay the same across runs?

The token benchmark measures what *enters* the context. This harness measures
the other half: whether the same question produces the same *decision* when the
answer comes from a cold cache and from a warm one. A cache must change speed,
never semantics.

Scope and honesty
-----------------
This executes the deterministic, tool-only side. The full A/B — model with MCP
vs model without MCP — needs the agent runtime (see README.md): run the same
tasks there, record the decision fields, and compare them against the reference
values captured here. Building the runtime comparison into CI would assert
something about a model, not about this repository.

Usage
-----
    python -m research.ab_outcome.harness --record   # live cold/warm + fixtures
    python -m research.ab_outcome.harness            # replay fixtures (no network)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
TASKS_PATH = MODULE_DIR / "tasks.json"
FIXTURES_DIR = MODULE_DIR / "fixtures"
REPORT_JSON = MODULE_DIR / "report.json"
REPORT_MD = MODULE_DIR / "report.md"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_tasks(path: Path = TASKS_PATH) -> list[dict[str, Any]]:
    """Read the task definitions."""
    return json.loads(path.read_text(encoding="utf-8"))["tasks"]


def dig(payload: Any, path: str) -> Any:
    """Resolve ``a.b[0].c`` against a JSON payload; ``None`` when absent."""
    current = payload
    for part in path.split("."):
        match = re.fullmatch(r"([^\[]+)((?:\[\d+\])*)", part)
        if not match:
            return None
        key, indexes = match.group(1), match.group(2)
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
        for index in re.findall(r"\[(\d+)\]", indexes):
            if not isinstance(current, list) or int(index) >= len(current):
                return None
            current = current[int(index)]
    return current


def extract(payload: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    """Extract the decision fields from a tool payload."""
    return {path: dig(payload, path) for path in paths}


def compare(cold: dict[str, Any], warm: dict[str, Any]) -> list[str]:
    """Return the decision fields that differ between cold and warm runs."""
    return sorted(path for path in cold if cold[path] != warm.get(path))


def _call(server: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call one tool through the real MCP client."""

    async def _run() -> dict[str, Any]:
        from fastmcp import Client  # local import: replay mode needs no server

        async with Client(server) as client:
            result = await client.call_tool(tool, args)
            return result.structured_content or {}

    return asyncio.run(_run())


def run_task(server: Any, task: dict[str, Any]) -> dict[str, Any]:
    """Run one task cold and warm, then compare the decision fields."""
    from trading_mcp.data.result_cache import result_cache

    result_cache.clear_all()
    cold_payload = _call(server, task["tool"], task.get("args", {}))
    warm_payload = _call(server, task["tool"], task.get("args", {}))

    cold = extract(cold_payload, task["decision_fields"])
    warm = extract(warm_payload, task["decision_fields"])
    diffs = compare(cold, warm)
    fixture = FIXTURES_DIR / f"{task['name']}.json"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(
        json.dumps(cold_payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return {
        "name": task["name"],
        "tool": task["tool"],
        "status": "ok",
        "stable": not diffs,
        "diffs": diffs,
        "cold": cold,
        "warm": warm,
        "fixture": str(fixture.relative_to(PROJECT_ROOT)),
    }


def replay_task(task: dict[str, Any]) -> dict[str, Any]:
    """Validate a recorded fixture without claiming a stability result."""
    fixture = FIXTURES_DIR / f"{task['name']}.json"
    if not fixture.exists():
        return {
            "name": task["name"],
            "tool": task["tool"],
            "status": "skipped",
            "stable": None,
            "diffs": [],
            "note": "no fixture; run with --record",
        }
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    return {
        "name": task["name"],
        "tool": task["tool"],
        "status": "recorded",
        "stable": None,
        "diffs": [],
        "cold": extract(payload, task["decision_fields"]),
        "warm": None,
        "note": "replay only; run with --record to compare cold vs warm",
    }


def build_report(records: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Summarise stability across tasks."""
    executed = [row for row in records if row["status"] == "ok"]
    stable = [row for row in executed if row["stable"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "tasks": records,
        "summary": {
            "tasks_total": len(records),
            "tasks_executed": len(executed),
            "tasks_stable": len(stable),
            "stability_pct": round(100.0 * len(stable) / len(executed), 1) if executed else None,
        },
        "limitations": [
            "This harness executes the deterministic tool path, not a model.",
            "The with-MCP vs without-MCP comparison requires the agent runtime (see README.md).",
            "Cold means the result cache was cleared; upstream data caches are untouched.",
            "Volatile fields (timestamps, elapsed time) are excluded via decision_fields.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable report."""
    summary = report["summary"]
    lines = [
        "# A/B outcome — cold vs warm determinism",
        "",
        f"Generated: {report['generated_at']} (mode: `{report['mode']}`)",
        "",
        f"Stable: **{summary['tasks_stable']}/{summary['tasks_executed']}** tasks"
        + (
            f" ({summary['stability_pct']}%)"
            if summary["stability_pct"] is not None
            else ""
        ),
        "",
        "| Task | Tool | Status | Stable | Decision fields |",
        "|---|---|---|---|---|",
    ]
    for row in report["tasks"]:
        values = json.dumps(row.get("cold"), ensure_ascii=False)
        stable = "—" if row["stable"] is None else ("yes" if row["stable"] else "no")
        lines.append(
            f"| {row['name']} | `{row['tool']}` | {row['status']} | {stable} | `{values}` |"
        )
    lines += ["", "## Limitations", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run or replay the A/B harness."""
    parser = argparse.ArgumentParser(description="A/B outcome harness")
    parser.add_argument("--record", action="store_true", help="execute live and save fixtures")
    parser.add_argument("--tasks", type=Path, default=TASKS_PATH)
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    records: list[dict[str, Any]] = []

    if args.record:
        from trading_mcp.mcp import initialize_mcp

        skills = Path.home() / ".config" / "opencode" / "skills"
        if not skills.exists():
            skills = PROJECT_ROOT.parent / "skills"
        server = initialize_mcp(str(skills), str(skills / "market-accumulation-scanner" / "data"))
        for task in tasks:
            try:
                record = run_task(server, task)
            except Exception as exc:  # pylint: disable=broad-except
                record = {
                    "name": task["name"],
                    "tool": task["tool"],
                    "status": "error",
                    "stable": None,
                    "diffs": [],
                    "note": f"{type(exc).__name__}: {exc}",
                }
                print(f"  ERROR {task['name']}: {record['note']}", file=sys.stderr)
            records.append(record)
            print(f"  {record['name']}: {record['status']} stable={record['stable']}")
    else:
        records = [replay_task(task) for task in tasks]

    report = build_report(records, mode="live" if args.record else "replay")
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"wrote {REPORT_JSON} and {REPORT_MD}")

    if args.record and report["summary"]["tasks_executed"]:
        unstable = [row for row in records if row.get("stable") is False]
        if unstable:
            print(f"unstable tasks: {[row['name'] for row in unstable]}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
