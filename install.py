#!/usr/bin/env python3
"""Install opencode skills into the user's opencode config directory."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class InstallOptions(BaseModel):
    """Options for the installation process."""

    config_dir: Path = Field(
        default=Path("~/.config/opencode").expanduser(),
        description="Opencode config directory",
    )
    dry_run: bool = Field(default=False, description="Print actions without copying")
    force: bool = Field(default=False, description="Overwrite existing files")
    skip_config: bool = Field(default=False, description="Skip config files")
    verbose: bool = Field(default=False, description="Show detailed output")


class FileAction(BaseModel):
    """A single file copy action in the install plan."""

    source: Path
    dest: Path
    category: str = "skill"
    reason: str = ""


class InstallPlan(BaseModel):
    """Full install plan listing all actions."""

    options: InstallOptions
    actions: list[FileAction] = Field(default_factory=list)

    @property
    def file_count(self) -> int:
        """Number of files in the plan."""
        return len(self.actions)

    @property
    def skipped_count(self) -> int:
        """Number of files skipped (already exist)."""
        return sum(1 for a in self.actions if a.reason == "exists")


def discover_skill_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Walk skills/ directory returning (source, relative_path) pairs."""
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return []
    result: list[tuple[Path, str]] = []
    for path in skills_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(skills_dir)
            result.append((path, str(rel)))
    return result


def discover_plugin_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Walk plugins/ directory returning (source, relative_path) pairs."""
    plugins_dir = repo_root / "plugins"
    if not plugins_dir.is_dir():
        return []
    result: list[tuple[Path, str]] = []
    for path in plugins_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(plugins_dir)
            result.append((path, str(rel)))
    return result


def discover_config_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Walk config/ directory returning (source, relative_path) pairs."""
    config_dir = repo_root / "config"
    if not config_dir.is_dir():
        return []
    result: list[tuple[Path, str]] = []
    for path in config_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(config_dir)
            result.append((path, str(rel)))
    return result


def build_plan(options: InstallOptions) -> InstallPlan:
    """Build an InstallPlan based on the given options."""
    repo_root = Path(__file__).parent.resolve()
    actions: list[FileAction] = []

    for source, rel in discover_skill_files(repo_root):
        dest = options.config_dir / "skills" / rel
        action = FileAction(source=source, dest=dest, category="skill")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    for source, rel in discover_plugin_files(repo_root):
        dest = options.config_dir / ".opencode" / "plugins" / rel
        action = FileAction(source=source, dest=dest, category="plugin")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    if not options.skip_config:
        for source, rel in discover_config_files(repo_root):
            dest = options.config_dir / rel
            action = FileAction(source=source, dest=dest, category="config")
            if dest.exists() and not options.force:
                action.reason = "exists"
            actions.append(action)

    return InstallPlan(options=options, actions=actions)


def execute_plan(plan: InstallPlan) -> None:
    """Execute or print the actions in the install plan."""
    for action in plan.actions:
        if action.reason == "exists":
            if plan.options.verbose:
                print(f"  SKIP  {action.dest}  (already exists)")
            continue

        if plan.options.dry_run:
            symbol = "LINK" if action.category == "plugin" else "COPY"
            print(f"  {symbol}  {action.source}  →  {action.dest}")
            continue

        action.dest.parent.mkdir(parents=True, exist_ok=True)
        if action.dest.exists() or action.dest.is_symlink():
            action.dest.unlink()
        os.symlink(action.source, action.dest)
        if plan.options.verbose:
            print(f"  LINK  {action.source}  →  {action.dest}")


def print_summary(plan: InstallPlan) -> None:
    """Print a human-readable summary of the install plan."""
    skipped = plan.skipped_count
    copied = plan.file_count - skipped
    print()
    if plan.options.dry_run:
        print(f"Dry run: {copied} files would be copied")
        if skipped:
            print(f"         {skipped} files already exist (use --force to overwrite)")
    else:
        print(f"Installed: {copied} files to {plan.options.config_dir}")
        if skipped:
            print(f"Skipped:  {skipped} files (already exist, use --force to overwrite)")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Install opencode skills into ~/.config/opencode/",
    )
    parser.add_argument(
        "--config-dir",
        default=str(Path("~/.config/opencode").expanduser()),
        help="Target opencode config directory (default: ~/.config/opencode)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print actions without copying any files",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="Do not install config/ files (AGENTS.md, opencode.json)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed output for each file",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    options = InstallOptions(
        config_dir=Path(args.config_dir).expanduser().resolve(),
        dry_run=args.dry_run,
        force=args.force,
        skip_config=args.skip_config,
        verbose=args.verbose,
    )
    plan = build_plan(options)
    execute_plan(plan)
    print_summary(plan)
    return 0 if plan.file_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
