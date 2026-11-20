#!/usr/bin/env python3
"""Compatibility entry point: run install.sh, the single installer.

The installer is install.sh (bash, no Python packages). This wrapper keeps
`python3 install.py` working on a new machine: it maps the old flags and runs
install.sh.

    python3 install.py              ->  ./install.sh
    python3 install.py --dry-run    ->  ./install.sh --dry-run
    python3 install.py --force      ->  ./install.sh --force
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# Old flags without an equivalent: the installer ignores them now.
IGNORED_FLAGS = {"-v", "--verbose", "--skip-alphavantage", "--skip-config"}


def translate(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    """Map old install.py flags to install.sh flags and environment values."""
    args: list[str] = []
    env: dict[str, str] = {}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--config-dir" and index + 1 < len(argv):
            env["OPENCODE_CONFIG_DIR"] = str(Path(argv[index + 1]).expanduser())
            index += 2
            continue
        if arg.startswith("--config-dir="):
            env["OPENCODE_CONFIG_DIR"] = str(Path(arg.split("=", 1)[1]).expanduser())
        elif arg in IGNORED_FLAGS:
            print(f"install.py: {arg} has no effect now; install.sh does not use it", file=sys.stderr)
        else:
            args.append(arg)
        index += 1
    return args, env


def main(argv: list[str] | None = None) -> int:
    """Run install.sh with the translated arguments."""
    bash = shutil.which("bash")
    if bash is None:
        print("install.py: bash not found; run install.sh with a POSIX shell", file=sys.stderr)
        return 1
    args, env = translate(sys.argv[1:] if argv is None else argv)
    os.execve(bash, [bash, str(REPO_ROOT / "install.sh"), *args], {**os.environ, **env})
    return 0


if __name__ == "__main__":
    sys.exit(main())
