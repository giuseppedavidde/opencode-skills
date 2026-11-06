"""Versioned calibration artifacts with a verifiable fingerprint.

A threshold is only trustworthy if you can prove which calibrated file produced
it. This module pairs a calibration JSON with a lock file::

    thresholds.json        # the artifact itself
    thresholds.lock.json   # {"fingerprint": sha256, "version": ..., "file": ...}

The fingerprint is the SHA-256 of the canonical JSON payload, so any edit to
the thresholds changes it. Payloads that depend on the calibration cite the
fingerprint via ``EvidenceBlock``; a mismatch with the lock is surfaced as
``verified=False`` instead of silently producing numbers from an unverified
file.

Usage
-----
    python -m trading_mcp.calibration research/breakout_calibration/output/thresholds.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CalibrationArtifact(BaseModel):
    """A calibration file plus its verification state."""

    model_config = ConfigDict(extra="allow")

    name: str
    version: str
    created_at: str | None = None
    source: str = "unknown"
    fingerprint: str
    verified: bool = False
    verification_note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CalibrationLock(BaseModel):
    """The recorded fingerprint for one artifact."""

    model_config = ConfigDict(extra="allow")

    fingerprint: str
    version: str | None = None
    file: str | None = None


def canonical_json(payload: Any) -> str:
    """Canonical form used for hashing (sorted keys, compact separators)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(payload: Any) -> str:
    """SHA-256 of the canonical JSON payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def lock_path(artifact_path: Path) -> Path:
    """Sidecar lock path for an artifact (``thresholds.json`` -> ``thresholds.lock.json``)."""
    return artifact_path.with_suffix(".lock.json")


def write_lock(artifact_path: Path) -> CalibrationLock:
    """Record the current fingerprint of ``artifact_path`` in its lock file."""
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    lock = CalibrationLock(
        fingerprint=fingerprint(payload),
        version=str(payload.get("version", "")),
        file=artifact_path.name,
    )
    lock_path(artifact_path).write_text(
        json.dumps(lock.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock


def load_artifact(
    artifact_path: Path,
    *,
    name: str | None = None,
    source: str = "unknown",
) -> CalibrationArtifact | None:
    """Load and verify an artifact against its lock file.

    Returns ``None`` when the artifact is missing. A missing lock, a malformed
    lock or a fingerprint mismatch yields ``verified=False`` with a reason: the
    caller can still use the payload, but must report it as unverified.
    """
    if not artifact_path.exists():
        return None
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    current = fingerprint(payload)
    artifact = CalibrationArtifact(
        name=name or artifact_path.stem,
        version=str(payload.get("version", "")),
        created_at=payload.get("generated_at"),
        source=source,
        fingerprint=current,
        payload=payload,
    )

    lock_file = lock_path(artifact_path)
    if not lock_file.exists():
        artifact.verification_note = f"lock file missing: {lock_file.name}"
        return artifact
    try:
        lock = CalibrationLock.model_validate(
            json.loads(lock_file.read_text(encoding="utf-8"))
        )
    except (ValueError, json.JSONDecodeError) as exc:
        artifact.verification_note = f"lock file invalid: {exc}"
        return artifact

    if lock.fingerprint != current:
        artifact.verification_note = "fingerprint mismatch: artifact edited after lock"
        return artifact
    artifact.verified = True
    return artifact


def evidence_block(artifact: CalibrationArtifact | None) -> dict[str, Any]:
    """Fields a payload cites to make its calibration traceable."""
    if artifact is None:
        return {
            "artifact_version": None,
            "artifact_fingerprint": None,
            "artifact_verified": None,
            "calibration_as_of": None,
        }
    return {
        "artifact_version": artifact.version or None,
        "artifact_fingerprint": artifact.fingerprint,
        "artifact_verified": artifact.verified,
        "calibration_as_of": artifact.created_at,
    }


def main(argv: list[str] | None = None) -> int:
    """Write the lock file for an artifact."""
    parser = argparse.ArgumentParser(description="Lock a calibration artifact")
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)

    if not args.artifact.exists():
        print(f"artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    lock = write_lock(args.artifact)
    print(f"locked {args.artifact.name}: {lock.fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
