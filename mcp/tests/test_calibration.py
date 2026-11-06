"""Calibration artifacts: fingerprints, lock verification, payload evidence."""

# pylint: disable=no-member  # pylint mis-infers pydantic Field() as FieldInfo

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trading_mcp.analysis.breakout_context import _THRESHOLDS_PATH, build_breakout_context
from trading_mcp.calibration import (
    evidence_block,
    fingerprint,
    load_artifact,
    lock_path,
    write_lock,
)


def _artifact(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_fingerprint_is_stable_and_content_sensitive() -> None:
    """Canonical hashing ignores key order but not content."""
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_lock_roundtrip_verifies(tmp_path: Path) -> None:
    """A freshly written lock verifies the artifact."""
    path = _artifact(tmp_path, {"version": "1.0.0", "x": 1})
    assert not lock_path(path).exists()
    write_lock(path)
    artifact = load_artifact(path)
    assert artifact is not None
    assert artifact.verified is True
    assert artifact.version == "1.0.0"


def test_tampered_artifact_is_unverified(tmp_path: Path) -> None:
    """Editing the artifact after locking is detected."""
    path = _artifact(tmp_path, {"version": "1.0.0", "x": 1})
    write_lock(path)
    path.write_text(json.dumps({"version": "1.0.0", "x": 2}), encoding="utf-8")
    artifact = load_artifact(path)
    assert artifact is not None
    assert artifact.verified is False
    assert "fingerprint mismatch" in artifact.verification_note


def test_missing_lock_is_unverified_not_fatal(tmp_path: Path) -> None:
    """A missing lock degrades to unverified, it does not raise."""
    path = _artifact(tmp_path, {"version": "1.0.0"})
    artifact = load_artifact(path)
    assert artifact is not None
    assert artifact.verified is False
    assert "lock file missing" in artifact.verification_note


def test_missing_artifact_returns_none(tmp_path: Path) -> None:
    """No artifact means no evidence, not a fabricated one."""
    assert load_artifact(tmp_path / "absent.json") is None
    assert evidence_block(None)["artifact_verified"] is None


def test_committed_thresholds_are_locked() -> None:
    """The shipped calibration must verify against its lock."""
    if not _THRESHOLDS_PATH.exists():
        pytest.skip("thresholds.json not present")
    artifact = load_artifact(_THRESHOLDS_PATH, name="breakout_thresholds")
    assert artifact is not None
    assert artifact.verified is True, artifact.verification_note
    assert artifact.version


def test_breakout_evidence_cites_artifact() -> None:
    """The payload names the calibration file that produced its thresholds."""
    if not _THRESHOLDS_PATH.exists():
        pytest.skip("thresholds.json not present")
    n = 320
    close = pd.Series(np.linspace(10.0, 40.0, n))
    hist = pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.001,
            "Low": close * 0.999,
            "Close": close,
            "Volume": pd.Series([1e6] * n),
        }
    )
    context = build_breakout_context("TEST", hist, include_gex=False)
    evidence = context.evidence
    assert evidence.artifact_fingerprint
    assert evidence.artifact_verified is True
    assert evidence.artifact_version
    assert evidence.calibration_as_of
