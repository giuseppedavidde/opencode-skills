"""Versioned calibration artifacts with a verifiable fingerprint and acceptance gates.

A threshold or a probability is only trustworthy when you can prove which
file, which code and which data produced it. This module pairs a
calibration JSON with a lock file::

    thresholds.json        # the artifact itself
    thresholds.lock.json   # fingerprint (+ optional code and data digests)

Lock fields:

- ``fingerprint``: SHA-256 of the canonical JSON payload (any edit changes it).
- ``code_sha256`` + ``code_files``: digest of the code that produced the
  artifact (paths relative to ``code_root``). When present, the current files
  must give the same digest, otherwise the artifact is unverified ("code
  changed after the calibration").
- ``data_sha256`` + ``data_manifest``: digest of the data snapshot (for
  example the sorted list of ``symbol,first_date,last_date,rows``).

``provenance`` says what the lock proves: ``payload_only`` (legacy locks),
``payload+code``, ``payload+data`` or ``payload+code+data``.

Acceptance (SIG-19): callers must not use an artifact that is missing,
unverified, or (for probability artifacts) worse than the naive base rate or
not validated walk-forward. :func:`accept_probability_artifact` applies
those gates and returns the reason of a rejection.

Usage
-----
    python -m trading_mcp.calibration ARTIFACT [--code FILE ...] [--code-root DIR]
                                      [--data-sha256 HEX --data-manifest TEXT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

ACCEPTED_VALIDATION_METHODS = ("walk_forward", "purged_walk_forward", "nested_walk_forward")


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
    provenance: str = "none"
    code_sha256: str | None = None
    data_sha256: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CalibrationLock(BaseModel):
    """The recorded fingerprint (and optional code and data digests) of one artifact."""

    model_config = ConfigDict(extra="allow")

    fingerprint: str
    version: str | None = None
    file: str | None = None
    code_sha256: str | None = None
    code_files: list[str] = Field(default_factory=list)
    data_sha256: str | None = None
    data_manifest: str | None = None


def canonical_json(payload: Any) -> str:
    """Canonical form used for hashing (sorted keys, compact separators)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(payload: Any) -> str:
    """SHA-256 of the canonical JSON payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def digest_files(files: Iterable[str], root: Path) -> str | None:
    """SHA-256 over ``(relative path, content)`` of ``files``; ``None`` when one is missing."""
    digest = hashlib.sha256()
    for relative in sorted(set(files)):
        path = root / relative
        if not path.is_file():
            return None
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def lock_path(artifact_path: Path) -> Path:
    """Sidecar lock path for an artifact (``thresholds.json`` -> ``thresholds.lock.json``)."""
    return artifact_path.with_suffix(".lock.json")


def write_lock(
    artifact_path: Path,
    *,
    code_files: Iterable[str] | None = None,
    code_root: Path | None = None,
    data_sha256: str | None = None,
    data_manifest: str | None = None,
) -> CalibrationLock:
    """Record the fingerprint of ``artifact_path`` (and the code/data digests) in its lock file.

    Call it from the job that produced the artifact, so the code digest is the
    one of the code that ran.
    """
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    files = sorted(set(code_files or []))
    root = code_root or artifact_path.parent
    lock = CalibrationLock(
        fingerprint=fingerprint(payload),
        version=str(payload.get("version", "")),
        file=artifact_path.name,
        code_sha256=digest_files(files, root) if files else None,
        code_files=files,
        data_sha256=data_sha256,
        data_manifest=data_manifest,
    )
    lock_path(artifact_path).write_text(
        json.dumps(lock.model_dump(exclude_none=True), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock


def _provenance(lock: CalibrationLock) -> str:
    parts = ["payload"]
    if lock.code_sha256:
        parts.append("code")
    if lock.data_sha256:
        parts.append("data")
    return "+".join(parts) if len(parts) > 1 else "payload_only"


def load_artifact(
    artifact_path: Path,
    *,
    name: str | None = None,
    source: str = "unknown",
    code_root: Path | None = None,
) -> CalibrationArtifact | None:
    """Load and verify an artifact against its lock file.

    Returns ``None`` when the artifact is missing. A missing lock, a malformed
    lock, a fingerprint mismatch or a code-digest mismatch yields
    ``verified=False`` with a reason: the caller must then reject it (or
    report it as unverified).
    """
    if not artifact_path.exists():
        return None
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return CalibrationArtifact(
            name=name or artifact_path.stem, version="", source=source, fingerprint="",
            verification_note=f"artifact unreadable: {type(exc).__name__}",
        )
    if not isinstance(payload, dict):
        payload = {"_payload": payload}
    current = fingerprint(payload)
    artifact = CalibrationArtifact(
        name=name or artifact_path.stem,
        version=str(payload.get("version", "")),
        created_at=payload.get("generated_at") or payload.get("created_at"),
        source=source,
        fingerprint=current,
        payload=payload,
    )

    lock_file = lock_path(artifact_path)
    if not lock_file.exists():
        artifact.verification_note = f"lock file missing: {lock_file.name}"
        return artifact
    try:
        lock = CalibrationLock.model_validate(json.loads(lock_file.read_text(encoding="utf-8")))
    except (ValueError, json.JSONDecodeError) as exc:
        artifact.verification_note = f"lock file invalid: {exc}"
        return artifact

    artifact.provenance = _provenance(lock)
    artifact.code_sha256 = lock.code_sha256
    artifact.data_sha256 = lock.data_sha256
    if lock.fingerprint != current:
        artifact.verification_note = "fingerprint mismatch: artifact edited after lock"
        return artifact
    if lock.code_sha256:
        root = code_root or artifact_path.parent
        now = digest_files(lock.code_files, root)
        if now != lock.code_sha256:
            artifact.verification_note = "code digest mismatch: the producing code changed after the calibration"
            return artifact
    artifact.verified = True
    if artifact.provenance == "payload_only":
        artifact.verification_note = "payload fingerprint verified; the lock records no code or data digest"
    return artifact


def _metric(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        node: Any = payload
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        try:
            value = float(node)
        except (TypeError, ValueError):
            continue
        return value
    return None


def accept_probability_artifact(artifact: CalibrationArtifact | None) -> tuple[bool, str]:
    """Gate for artifacts that publish probabilities (hit rates).

    Accepted only when the artifact exists, is verified, was validated
    walk-forward (``validation.method``) and its out-of-sample Brier score is
    strictly better than the naive base-rate Brier score.
    """
    if artifact is None:
        return False, "no artifact"
    if not artifact.verified:
        return False, f"unverified artifact: {artifact.verification_note or 'no lock'}"
    payload = artifact.payload
    method = str((payload.get("validation") or {}).get("method") or "")
    if method not in ACCEPTED_VALIDATION_METHODS:
        return False, "no walk-forward validation recorded (validation.method)"
    model = _metric(payload, "metrics.brier_oos", "brier_isotonic", "brier_oos")
    naive = _metric(payload, "metrics.brier_naive_oos", "brier_naive", "brier_naive_oos")
    if model is None or naive is None:
        return False, "out-of-sample Brier scores missing"
    if model >= naive:
        return False, f"out-of-sample Brier {model:.4f} is not better than naive {naive:.4f}"
    return True, f"walk-forward ({method}); Brier {model:.4f} < naive {naive:.4f}"


def evidence_block(artifact: CalibrationArtifact | None) -> dict[str, Any]:
    """Fields a payload cites to make its calibration traceable."""
    if artifact is None:
        return {
            "artifact_version": None,
            "artifact_fingerprint": None,
            "artifact_verified": None,
            "calibration_as_of": None,
            "artifact_provenance": None,
        }
    return {
        "artifact_version": artifact.version or None,
        "artifact_fingerprint": artifact.fingerprint,
        "artifact_verified": artifact.verified,
        "calibration_as_of": artifact.created_at,
        "artifact_provenance": artifact.provenance,
    }


def main(argv: list[str] | None = None) -> int:
    """Write the lock file for an artifact."""
    parser = argparse.ArgumentParser(description="Lock a calibration artifact")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--code", nargs="*", default=[], help="Code files (relative to --code-root)")
    parser.add_argument("--code-root", type=Path, default=None)
    parser.add_argument("--data-sha256", default=None)
    parser.add_argument("--data-manifest", default=None)
    args = parser.parse_args(argv)

    if not args.artifact.exists():
        print(f"artifact not found: {args.artifact}", file=sys.stderr)
        return 2
    lock = write_lock(args.artifact, code_files=args.code, code_root=args.code_root,
                      data_sha256=args.data_sha256, data_manifest=args.data_manifest)
    print(f"locked {args.artifact.name}: {lock.fingerprint} ({_provenance(lock)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
