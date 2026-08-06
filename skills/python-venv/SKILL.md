---


name: python-venv
description: "CRITICAL: Always use Python virtual environments. Never install packages with pip directly on the system Python. Every Python project must use a venv."
---

# Python Virtual Environment Mandatory Rule

CRITICAL: You MUST NEVER use `pip install` on the system Python. Always create and use a virtual environment.

## When to create a venv

Any time you need to:
- Install a Python package (`pip install ...`)
- Run a Python script that uses external dependencies
- Execute `python -m graphify` or any CLI tool that requires Python packages

## REUSE FIRST — never create duplicate venvs

CRITICAL: Before creating any venv, ALWAYS check if one exists and reuse it.

### Priority 1: trading/market-data work → reuse trading-mcp-venv

```bash
# Questo venv esegue il server MCP "trading" e ha GIÀ tutte le dipendenze
# (pandas, yfinance, lightgbm, scikit-learn, scipy, numpy, pydantic, requests...).
VENV_TRADING="$HOME/.local/share/opencode/trading-mcp-venv"
if [ -f "$VENV_TRADING/bin/activate" ]; then
  source "$VENV_TRADING/bin/activate"
fi
```

Regola: se il task coinvolge trading/stock/options/market data → `trading-mcp-venv`.
Altrimenti (graphify, pdf, generico) → `/tmp/opencode/.venv` (Priority 2 sotto).

### Priority 2: generic/non-trading work → /tmp/opencode/.venv

```bash
# Check if shared venv exists in /tmp/opencode
ls /tmp/opencode/.venv/bin/activate 2>/dev/null && echo "EXISTS"

# If it exists, ACTIVATE IT (do NOT create a new one):
source /tmp/opencode/.venv/bin/activate

# Only if it does NOT exist, create it ONCE:
python3 -m venv /tmp/opencode/.venv
source /tmp/opencode/.venv/bin/activate
```

### Reuse rule for /tmp/opencode

- For trading/market-data Python work, reuse the MCP trading venv at `~/.local/share/opencode/trading-mcp-venv` (Priority 1 sopra).
- For generic/non-trading Python work, use a **single shared venv** at `/tmp/opencode/.venv` (Priority 2).
- Never create `pdf_venv`, `tensor_venv`, `tensor2_venv`, etc. — they all go in the appropriate existing venv.
- Before `pip install <pkg>`, check if already installed: `pip show <pkg> 2>/dev/null`

```bash
# Check if package exists before installing
pip show fpdf2 2>/dev/null || pip install fpdf2
```

### For project-specific work (outside /tmp/opencode)

```bash
# Create venv in the project directory
python3 -m venv .venv
source .venv/bin/activate
```

## Exceptions

The only exception is packages installed via the system package manager:
- `sudo apt install python3-xxx` (Debian/Ubuntu)
- `sudo pacman -S python-xxx` (Arch)

## Checking if a venv is active

```bash
# If this shows a path inside a venv, you're safe
python3 -c "import sys; print(sys.prefix != sys.base_prefix)"
# Returns True if inside a venv, False if on system Python
```
