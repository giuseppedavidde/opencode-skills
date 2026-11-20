"""The agent docs must not claim a model that differs from the `model` field of that agent."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AGENTS = REPO / "agents"
MODEL_ID_RE = re.compile(
    r"\b(?:deepseek-v[\w.]+(?:-[a-z]+)*|glm-[\d.]+(?:-flash)?|gemini-[\w.]+-[a-z]+|kimi-[\w.]+|"
    r"qwen[\w.]+-[a-z]+|minimax-[\w.]+|mimo-[\w.]+-[a-z]+|gpt-[\w.]+-[a-z]+|claude-[\w-]+-\d+-\d+)\b"
)
MENTION_RE = re.compile(r"@([a-z][\w-]*)")
# "- **@trade**: <model> — ..." names its subject first.
BULLET_RE = re.compile(r"^\s*- \*\*@([a-z][\w-]*)\*\*:")


def bare_model(raw: str) -> str:
    return str(raw).split("#", 1)[0].rpartition("/")[2]


def agent_models() -> dict[str, str]:
    models: dict[str, str] = {}
    for path in AGENTS.glob("*.md"):
        frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
        match = re.search(r"^model:\s*[\"']?([^\"'\s]+)", frontmatter, re.M)
        if match:
            models[path.stem] = bare_model(match.group(1))
    config = json.loads((REPO / "config" / "opencode.json").read_text(encoding="utf-8"))
    for name, spec in (config.get("agent") or {}).items():
        if isinstance(spec, dict) and spec.get("model"):
            models.setdefault(name, bare_model(spec["model"]))
    models.setdefault("router", bare_model(config.get("model", "")))
    return models


def body_lines(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        start = next(i for i in range(1, len(lines)) if lines[i].strip() == "---") + 1
    return [(number + 1, line) for number, line in enumerate(lines) if number >= start]


DOCS = sorted(AGENTS.glob("*.md")) + [REPO / "config" / "AGENTS.md"]


@pytest.mark.parametrize("path", DOCS, ids=lambda path: path.name)
def test_model_claims_match_the_agent_frontmatter(path: Path) -> None:
    models = agent_models()
    own = path.stem if path.parent == AGENTS else None
    problems: list[str] = []
    for number, line in body_lines(path):
        claimed = MODEL_ID_RE.findall(line)
        if not claimed:
            continue
        mentioned = sorted({name for name in MENTION_RE.findall(line) if name in models})
        bullet = BULLET_RE.match(line)
        if bullet:
            mentioned = [bullet.group(1)]
        if "Router (agent router)" in line:
            mentioned = ["router"]
        if len(mentioned) > 1:
            problems.append(f"{path.name}:{number}: names several agents and a model id")
            continue
        subject = mentioned[0] if mentioned else own
        if subject is None:
            continue
        wrong = [model for model in claimed if model != models[subject]]
        if wrong:
            problems.append(f"{path.name}:{number}: says {subject} uses {wrong}, frontmatter says {models[subject]}")
    assert not problems, "\n".join(problems)
