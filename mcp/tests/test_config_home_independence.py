"""Tests: config dirs resolve without depending on ``$HOME``.

Le risoluzioni avvengono a import-time, quindi i test girano in subprocess
con un ambiente controllato per verificare i fallback HOME-independent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _run_config_probe(env: dict[str, str]) -> dict[str, str]:
    """Importa trading_mcp.config in un subprocess e ritorna le dir risolte."""
    code = (
        "import json, sys;"
        f"sys.path.insert(0, {str(SRC)!r});"
        "from trading_mcp.config import SKILLS_DIR, TICKERS_DIR;"
        "print(json.dumps({'skills': str(SKILLS_DIR), 'tickers': str(TICKERS_DIR)}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_config_explicit_env_wins() -> None:
    """TRADING_SKILLS_DIR/TICKERS_DIR espliciti sono usati così come sono."""
    env = dict(os.environ)
    env["TRADING_SKILLS_DIR"] = "/custom/skills"
    env["TRADING_TICKERS_DIR"] = "/custom/tickers"
    resolved = _run_config_probe(env)
    assert resolved["skills"] == "/custom/skills"
    assert resolved["tickers"] == "/custom/tickers"


def test_config_resolves_with_empty_home() -> None:
    """Con HOME vuoto, la risoluzione non crasha e produce path assoluti."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": "",
        "PYTHONPATH": str(SRC),
    }
    resolved = _run_config_probe(env)
    assert resolved["skills"].startswith("/")
    assert resolved["tickers"].startswith("/")
    assert ".config/opencode/skills" in resolved["skills"]


def test_config_resolves_without_home_key() -> None:
    """Senza la variabile HOME, la risoluzione non crasha."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "PYTHONPATH": str(SRC),
    }
    resolved = _run_config_probe(env)
    assert resolved["skills"].startswith("/")
    assert resolved["tickers"].startswith("/")


def test_tickers_dir_is_under_skills_dir_without_env() -> None:
    """Senza env, TICKERS_DIR deriva da SKILLS_DIR."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": "",
        "PYTHONPATH": str(SRC),
    }
    resolved = _run_config_probe(env)
    assert resolved["tickers"].startswith(resolved["skills"].rstrip("/"))


def test_weights_config_resolves_without_home() -> None:
    """weights_config risolve un path senza dipendere da HOME."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": "",
        "PYTHONPATH": str(SRC),
    }
    code = (
        "import json, sys;"
        f"sys.path.insert(0, {str(SRC)!r});"
        "from trading_mcp.weights_config import DEFAULT_WEIGHTS_PATH;"
        "print(json.dumps({'p': str(DEFAULT_WEIGHTS_PATH)}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    path = json.loads(result.stdout.strip().splitlines()[-1])["p"]
    assert path.startswith("/")
