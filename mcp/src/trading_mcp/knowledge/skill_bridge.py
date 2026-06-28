"""Bridge to read skill knowledge from SKILL.md files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class SkillBridge:
    """Reads SKILL.md files from the skills directory."""

    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir)
        if not self.skills_dir.exists():
            raise ValueError(f"Skills directory not found: {self.skills_dir}")

    def list_skills(self) -> list[dict[str, str]]:
        """List all available skills with metadata."""
        skills = []
        for skill_md in self.skills_dir.rglob("SKILL.md"):
            try:
                meta = self._parse_frontmatter(skill_md)
                skills.append({
                    "name": meta.get("name", skill_md.parent.name),
                    "description": str(meta.get("description", "")),
                    "path": str(skill_md.parent),
                })
            except (ValueError, OSError):
                continue
        return skills

    def get_skill_content(self, skill_name: str) -> str:
        """Get full SKILL.md content for a skill by name."""
        path = self._find_skill_path(skill_name)
        if path is None:
            raise ValueError(f"Skill '{skill_name}' not found")
        return (path / "SKILL.md").read_text(encoding="utf-8")

    def get_skill_files(self, skill_name: str) -> list[str]:
        """List all files in a skill directory."""
        path = self._find_skill_path(skill_name)
        if path is None:
            raise ValueError(f"Skill '{skill_name}' not found")
        files: list[str] = []
        for file_path in path.rglob("*"):
            if file_path.is_file():
                files.append(str(file_path.relative_to(path)))
        return sorted(files)

    def _find_skill_path(self, skill_name: str) -> Path | None:
        for skill_md in self.skills_dir.rglob("SKILL.md"):
            meta = self._parse_frontmatter(skill_md)
            if meta.get("name") == skill_name:
                return skill_md.parent
        return None

    def _parse_frontmatter(self, skill_md_path: Path) -> dict[str, Any]:
        content = skill_md_path.read_text(encoding="utf-8")
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}
