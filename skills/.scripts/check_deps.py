#!/usr/bin/env python3
"""
Check version compatibility of OpenCode skills.

Usage:
    python3 check_deps.py                    # Check ALL skills
    python3 check_deps.py stock-crypto-analysis  # Check one skill
    python3 check_deps.py --upgrade          # Show which skills have newer deps available
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"
MANIFEST_PATH = SKILLS_DIR / ".skill-versions.json"


def load_manifest() -> dict:
    """Load the skill versions manifest."""
    if not MANIFEST_PATH.exists():
        print("Error: .skill-versions.json not found. Run build first.", file=sys.stderr)
        sys.exit(1)
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def check_skill(slug: str, manifest: dict, verbose: bool = True) -> int:
    """Check a single skill's dependencies. Returns number of issues found."""
    if slug not in manifest:
        print(f"[UNKNOWN] Skill '{slug}' not in manifest")
        return 1

    entry = manifest[slug]
    deps = entry.get("depends_on", {})
    issues = 0

    if not deps:
        if verbose:
            print(f"[OK] {slug} v{entry['version']} — no dependencies")
        return 0

    # Check each dependency
    for dep_slug, expected_version in deps.items():
        if dep_slug not in manifest:
            print(f"[MISSING] {slug} depends on '{dep_slug}' — NOT INSTALLED")
            issues += 1
            continue

        dep_entry = manifest[dep_slug]
        actual_version = dep_entry.get("version", "unknown")

        if actual_version != expected_version:
            print(
                f"[VERSION MISMATCH] {slug} expects {dep_slug} v{expected_version} "
                f"— installed: v{actual_version}"
            )
            issues += 1
        else:
            if verbose:
                print(f"  ✓ {dep_slug} v{actual_version}")

    if issues == 0:
        if verbose:
            print(f"[OK] {slug} v{entry['version']} — all {len(deps)} dependencies satisfied")
    else:
        print(f"[ISSUES] {slug}: {issues} dependency problem(s)")

    return issues


def check_all(manifest: dict) -> None:
    """Check all skills in the manifest."""
    total_issues = 0
    for slug in sorted(manifest):
        total_issues += check_skill(slug, manifest, verbose=False)

    print(f"\n--- Summary ---")
    print(f"Skills checked: {len(manifest)}")
    print(f"Dependency issues: {total_issues}")

    if total_issues == 0:
        print("✓ All dependencies match.")


def find_dependents(target: str, manifest: dict) -> list[str]:
    """Find all skills that depend on the given skill."""
    dependents = []
    for slug, entry in manifest.items():
        if target in entry.get("depends_on", {}):
            dependents.append(slug)
    return dependents


def show_upgrade_impact(manifest: dict) -> None:
    """Show which skills would need attention if dependencies were upgraded."""
    print("Upgrade Impact Analysis\n")
    for slug in sorted(manifest):
        deps = manifest[slug].get("depends_on", {})
        if not deps:
            continue

        upstream = []
        for dep_slug in deps:
            dep_manifest_entry = manifest.get(dep_slug, {})
            expected = deps[dep_slug]
            actual = dep_manifest_entry.get("version", "unknown")
            if actual != expected:
                upstream.append(f"{dep_slug} (expects {expected}, has {actual})")

        if upstream:
            print(f"[{slug}] needs updates for:")
            for item in upstream:
                print(f"  → {item}")


def main() -> None:
    """Entry point."""
    manifest = load_manifest()

    if len(sys.argv) == 1:
        check_all(manifest)
    elif sys.argv[1] == "--upgrade":
        show_upgrade_impact(manifest)
    elif sys.argv[1] == "--dependents":
        if len(sys.argv) < 3:
            print("Usage: check_deps.py --dependents <skill-slug>", file=sys.stderr)
            sys.exit(1)
        target = sys.argv[2]
        dependents = find_dependents(target, manifest)
        if dependents:
            print(f"Skills depending on {target}:")
            for d in dependents:
                print(f"  - {d}")
        else:
            print(f"No skills depend on {target}")
    else:
        slug = sys.argv[1]
        issues = check_skill(slug, manifest)
        sys.exit(min(issues, 1))


if __name__ == "__main__":
    main()
