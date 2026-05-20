# opencode-skills

Custom skills and configuration for [opencode](https://opencode.ai).

## Structure

```
opencode-skills/
├── install.py               # Python install script (recommended)
├── install.sh               # Shell install script (quick alternative)
├── config/
│   ├── AGENTS.md            # Global rules referencing skills
│   └── opencode.json        # Provider/model configuration
└── skills/
    ├── karpathy-llm-wiki/   # LLM-powered wiki builder skill
    │   ├── SKILL.md
    │   └── references/      # Template files
    └── python-pydantic/     # Python/Pydantic coding standards
        └── SKILL.md
```

## Install

### Python (recommended)

```bash
python install.py            # copy skills, skip existing
python install.py --force    # overwrite existing files
python install.py --dry-run  # preview without copying
python install.py -v         # verbose output
```

### Shell (quick)

```bash
./install.sh                 # copy skills, skip existing
./install.sh --force         # overwrite existing files
```

## Contents

| Skill | Description |
|-------|-------------|
| `karpathy-llm-wiki` | Build and maintain a personal LLM-powered knowledge base |
| `python-pydantic` | Python coding standards with Pydantic, type hints, and pylint |
| `config/AGENTS.md` | Global rules that load skills automatically |
| `config/opencode.json` | Provider/model configuration (modify before installing) |

## Requires

- [opencode](https://opencode.ai) CLI installed
- Python 3.10+ (for `install.py`)
