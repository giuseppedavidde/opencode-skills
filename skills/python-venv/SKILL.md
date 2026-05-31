---
name: python-venv
description: "CRITICAL: Always use Python virtual environments. Never install packages with pip directly on the system Python. Every Python project must use a venv."
orchestrator:
  parallel: false
  type: kb
---

# Python Virtual Environment Mandatory Rule

CRITICAL: You MUST NEVER use `pip install` on the system Python. Always create and use a virtual environment.

## When to create a venv

Any time you need to:
- Install a Python package (`pip install ...`)
- Run a Python script that uses external dependencies
- Execute `python -m graphify` or any CLI tool that requires Python packages

## How to create and use

```bash
# Create venv in the project directory
python3 -m venv .venv

# Activate it
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install packages inside the venv
pip install graphifyy

# When done, deactivate
deactivate
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
