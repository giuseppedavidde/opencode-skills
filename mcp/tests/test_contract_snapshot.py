"""Contract snapshot freshness and versioning.

The snapshot is the reviewable diff of the wire contract. These tests mirror
what CI runs, so a schema change cannot land without either a version bump or
a regenerated snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_contract import (
    DEFAULT_OUTPUT,
    DEFAULT_SKILLS,
    build_document,
    check,
)

pytestmark = pytest.mark.skipif(
    not DEFAULT_SKILLS.exists(), reason="skills directory not available"
)


def _snapshot() -> dict:
    return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))


def test_snapshot_is_fresh() -> None:
    """The committed snapshot matches the live server."""
    current = build_document(
        DEFAULT_SKILLS, DEFAULT_SKILLS / "market-accumulation-scanner" / "data"
    )
    problems = check(DEFAULT_OUTPUT, current)
    assert not problems, "\n".join(problems)


def test_snapshot_records_every_tool() -> None:
    """Every tool is present with a non-empty output schema."""
    document = _snapshot()
    assert len(document["tools"]) == 17
    for name, tool in document["tools"].items():
        assert tool["output_schema"], f"{name} has no output_schema"
        assert tool["output_schema"].get("properties"), f"{name} has an empty schema"


def test_snapshot_is_deterministic() -> None:
    """No timestamps or unstable ordering in the committed document."""
    text = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert "generated_at" not in text
    assert parsed["contract_version"]
    assert list(parsed["tools"]) == sorted(parsed["tools"])


def test_check_detects_version_drift_without_schema_change(tmp_path: Path) -> None:
    """A version change alone still requires a regenerated snapshot."""
    document = _snapshot()
    tampered = {**document, "contract_version": "0.0.1"}
    path = tmp_path / "tools.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    problems = check(path, document)
    assert problems and "CONTRACT_VERSION" in problems[0]


def test_check_detects_schema_drift_without_version_bump(tmp_path: Path) -> None:
    """A schema change without a version bump is reported as such."""
    document = _snapshot()
    changed = json.loads(json.dumps(document))
    changed["tools"]["analyze_stock"]["output_schema"]["properties"]["new_field"] = {
        "type": "string"
    }
    path = tmp_path / "tools.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    problems = check(path, document)
    assert problems and "without bumping" in problems[0]


def test_check_reports_missing_snapshot(tmp_path: Path) -> None:
    """A missing snapshot tells the author how to create it."""
    problems = check(tmp_path / "missing.json", _snapshot())
    assert problems and "missing snapshot" in problems[0]
