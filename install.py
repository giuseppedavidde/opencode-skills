#!/usr/bin/env python3
"""Install opencode skills, agents, commands, plugins, and config into ~/.config/opencode/.

Full portable installation — clones on any machine with `./install.py` to get
the complete opencode configuration (agents, config, commands, MCP, plugins, skills).
"""

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
    skip_alphavantage: bool = Field(default=False, description="Skip alphavantage bootstrap")
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


def check_submodules(repo_root: Path) -> bool:
    """Verify git submodules are initialized. Returns True if all ok."""
    submodule_dirs = [
        "skills/graphify-src",
        "skills/karpathy-llm-wiki-src",
        "skills/book-to-skill-src",
        "skills/quant-mind-src",
    ]
    empty_dirs = [
        d for d in submodule_dirs
        if (repo_root / d).is_dir() and not list((repo_root / d).iterdir())
    ]
    missing_dirs = [
        d for d in submodule_dirs
        if not (repo_root / d).is_dir()
    ]
    if empty_dirs or missing_dirs:
        print("ATTENZIONE: Submodule git non inizializzati!")
        for d in empty_dirs:
            print(f"  VUOTO: {d}")
        for d in missing_dirs:
            print(f"  ASSENTE: {d}")
        print()
        print("Esegui: git submodule update --init --recursive")
        print()
        return False
    return True


def discover_files(base_dir: Path) -> list[tuple[Path, str]]:
    """Walk base_dir recursively returning (source, relative_path) pairs."""
    if not base_dir.is_dir():
        return []
    result: list[tuple[Path, str]] = []
    for path in base_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(base_dir)
            result.append((path, str(rel)))
    return result


def build_plan(options: InstallOptions) -> InstallPlan:
    """Build an InstallPlan based on the given options."""
    repo_root = Path(__file__).parent.resolve()
    actions: list[FileAction] = []

    # ── Skills ──
    for source, rel in discover_files(repo_root / "skills"):
        dest = options.config_dir / "skills" / rel
        action = FileAction(source=source, dest=dest, category="skill")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    # ── Agents ──
    for source, rel in discover_files(repo_root / "agents"):
        dest = options.config_dir / "agents" / rel
        action = FileAction(source=source, dest=dest, category="agent")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    # ── Commands ──
    for source, rel in discover_files(repo_root / "command"):
        dest = options.config_dir / "command" / rel
        action = FileAction(source=source, dest=dest, category="command")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    # ── Plugins (auto-discovery via .opencode/plugins) ──
    for source, rel in discover_files(repo_root / "plugins"):
        dest = options.config_dir / ".opencode" / "plugins" / rel
        action = FileAction(source=source, dest=dest, category="plugin")
        if dest.exists() and not options.force:
            action.reason = "exists"
        actions.append(action)

    # ── Config (AGENTS.md, opencode.json) ──
    if not options.skip_config:
        for source, rel in discover_files(repo_root / "config"):
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
            print(f"  LINK  {action.source}  →  {action.dest}")
            continue

        action.dest.parent.mkdir(parents=True, exist_ok=True)
        if action.dest.exists() or action.dest.is_symlink():
            action.dest.unlink()
        os.symlink(action.source, action.dest)
        if plan.options.verbose:
            print(f"  LINK  {action.source}  →  {action.dest}")


def install_alphavantage(options: InstallOptions, repo_root: Path) -> None:
    """Install alphavantage-mcp.sh into $HOME/.local/bin/."""
    src = repo_root / "scripts" / "alphavantage-mcp.sh"
    if not src.is_file():
        print("  SKIP  alphavantage-mcp.sh (non trovato in scripts/)")
        return
    dest_dir = Path.home() / ".local" / "bin"
    dest = dest_dir / "alphavantage-mcp.sh"
    if dest.exists() and not options.force:
        print("  SKIP  alphavantage-mcp.sh (already exists)")
        return
    if options.dry_run:
        print(f"  COPY  {src}  →  {dest}  (chmod +x)")
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    os.symlink(src, dest)
    os.chmod(src, 0o755)
    if options.verbose:
        print(f"  LINK  {src}  →  {dest}")


def print_summary(plan: InstallPlan) -> None:
    """Print a human-readable summary of the install plan."""
    by_category: dict[str, int] = {}
    skipped_by_category: dict[str, int] = {}
    for action in plan.actions:
        cat = action.category
        by_category[cat] = by_category.get(cat, 0) + 1
        if action.reason == "exists":
            skipped_by_category[cat] = skipped_by_category.get(cat, 0) + 1

    print()
    if plan.options.dry_run:
        print(f"Dry run: {plan.file_count} files would be installed")
    else:
        print(f"Installati: {plan.file_count - plan.skipped_count} file"
              f" in {plan.options.config_dir}")
    for cat, total in sorted(by_category.items()):
        skipped = skipped_by_category.get(cat, 0)
        installed = total - skipped
        status = f"{installed}/{total}"
        if skipped:
            status += f" (saltati {skipped})"
        print(f"  {cat}: {status}")


def print_next_steps(repo_root: Path) -> None:
    """Print post-install instructions for the user."""
    steps = []
    steps.append("PROSSIMI PASSI:")
    steps.append("")
    steps.append("1. Headroom (compressione token):")
    steps.append("   ./setup-headroom.sh")
    steps.append("")
    steps.append("2. Trading MCP (analisi mercati):")
    steps.append("   ./setup-trading-mcp.sh")
    steps.append("")
    steps.append("3. Alphavantage API key:")
    steps.append("   echo 'YOUR_KEY' > ~/.config/opencode/alpha_vantage_key.txt")
    steps.append("   oppure: export ALPHA_VANTAGE_API_KEY='YOUR_KEY'")
    steps.append("")
    steps.append("4. Segreti (FMP, altre chiavi):")
    steps.append("   ./scripts/decrypt_secrets.sh")
    steps.append("   oppure crea: ~/.config/opencode/fmp_api_key.txt")
    steps.append("")
    steps.append("5. Riavvia opencode per applicare la configurazione")
    steps.append("")
    steps.append("NOTA: routing-stats richiede routing-eval clonato separatamente:")
    steps.append("  git clone https://github.com/giuseppedavidde/routing-eval.git \\")
    steps.append("    ~/Progetti/Github/routing-eval")
    steps.append("  pip install -r ~/Progetti/Github/routing-eval/requirements.txt")
    steps.append("  export ROUTING_EVAL_DIR=\"$HOME/Progetti/Github/routing-eval\"")
    steps.append("")
    if repo_root != Path("~/Progetti/Github/opencode-skills").expanduser():
        repo = repo_root
    else:
        repo = repo_root
    steps.append(f"Se sposti la repo, rilancia da: {repo}")
    steps.append("  python3 install.py --force --config-dir ~/.config/opencode")

    print("\n".join(steps))


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
        "--skip-alphavantage",
        action="store_true",
        help="Do not install alphavantage bootstrap script",
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
    repo_root = Path(__file__).parent.resolve()

    # Check submodules early
    check_submodules(repo_root)

    options = InstallOptions(
        config_dir=Path(args.config_dir).expanduser().resolve(),
        dry_run=args.dry_run,
        force=args.force,
        skip_config=args.skip_config,
        skip_alphavantage=args.skip_alphavantage,
        verbose=args.verbose,
    )

    plan = build_plan(options)
    execute_plan(plan)
    print_summary(plan)

    # Alphavantage bootstrap
    if not options.skip_alphavantage:
        print()
        print("Alphavantage bootstrap:")
        install_alphavantage(options, repo_root)

    print_next_steps(repo_root)
    return 0 if plan.file_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
