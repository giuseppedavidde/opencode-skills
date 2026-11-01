---
description: "Python standards from the opencode-skills workflow: mandatory virtual environment, Pydantic models, type hints, and pylint. Use when editing or running Python."
applyTo: "**/*.py"
---

# Python standards

## Virtual environment (mandatory)

- Before ANY Python install, run, or test, load the `python-venv` skill
  (`{{SKILLS_DIR}}/python-venv/SKILL.md`).
- Never `pip install` into the system Python.
- Temporary non-trading work: `/tmp/opencode/.venv`.
- Trading/market-data work: reuse `~/.local/share/opencode/trading-mcp-venv`
  (pandas, yfinance, lightgbm, scikit-learn are already installed).
- Never create duplicate venvs.

## Code

- Use Pydantic `BaseModel` for structured data, API payloads, and config.
- Type hints everywhere: function signatures, class attributes, module
  constants.
- PEP 8 and idiomatic Python.
- Run `pylint` on changed files before proposing code; fix errors and warnings.

## Verify

- Run the relevant tests (`pytest`) or at least
  `python -m compileall <changed files>`.
- Report the exact commands and outcomes in the `## VERIFICA` section when
  acting as a subagent.
