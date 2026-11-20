"""MCP tool registration: knowledge tools."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from trading_mcp.knowledge.skill_bridge import SkillBridge
from trading_mcp.responses import (
    typed,
    SkillKnowledgeResponse,
    error_payload,
)

logger = logging.getLogger(__name__)


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Split SKILL.md content into (heading, body) sections.

    Headings are markdown ``#`` / ``##`` / ``###`` lines. Content before the
    first heading is returned under the empty-heading key ``''``.
    """
    import re
    lines = content.split("\n")
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []
    heading_re = re.compile(r"^#{1,6}\s+(.*?)\s*$")
    for line in lines:
        m = heading_re.match(line)
        if m:
            if current_body or current_heading:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = m.group(1).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body or current_heading:
        sections.append((current_heading, "\n".join(current_body).strip()))
    return sections


def register_knowledge_tools(mcp_server: FastMCP, skills_dir: str) -> None:
    """Register knowledge tools with the MCP server."""

    skill_bridge = SkillBridge(skills_dir)

    @mcp_server.tool()
    @typed(SkillKnowledgeResponse)
    def get_skill_knowledge(
        skill_name: str, topic: str | None = None, section: str | None = None
    ) -> SkillKnowledgeResponse:
        """Get knowledge from a specific trading skill (SKILL.md).

        Retrieve trading framework definitions on-demand without loading
        entire skill files into context. Use this when you need a specific
        concept, pattern, or strategy definition.

        Args:
            skill_name: Skill name (e.g. 'wyckoff-2-0', 'volume-profile',
                        'options-playbook', 'trading-against-the-crowd', etc.)
            topic: Optional topic to filter (e.g. 'spring', 'vah', 'iron condor').
            section: Optional heading to return just that section (reduces tokens).

        Returns:
            Dictionary with skill metadata, section index (when applicable),
            and the relevant (section-capped) content.
        """
        SECTION_CAP = 3000
        try:
            content = skill_bridge.get_skill_content(skill_name)
            files = skill_bridge.get_skill_files(skill_name)

            sections = _split_sections(content)
            if section and sections:
                for heading, body in sections:
                    if section.lower() in heading.lower():
                        return {
                            "skill_name": skill_name,
                            "section": heading,
                            "sections": [h for h, _ in sections],
                            "content": (body[:SECTION_CAP] + "\n...") if len(body) > SECTION_CAP else body,
                            "files": files,
                            "truncated": len(body) > SECTION_CAP,
                        }
                return {
                    "skill_name": skill_name,
                    "error": f"section '{section}' not found",
                    "sections": [h for h, _ in sections],
                }

            matched = content
            if topic and topic.lower() in content.lower():
                lines = content.split("\n")
                relevant: list[str] = []
                capture = False
                for line in lines:
                    if topic.lower() in line.lower():
                        capture = True
                    if capture:
                        relevant.append(line)
                        if len(relevant) > 100:
                            break
                if relevant:
                    matched = "\n".join(relevant)
                    matched = f"(Filtered for '{topic}')\n\n{matched}"

            return {
                "skill_name": skill_name,
                "content": matched[:SECTION_CAP],
                "sections": [h for h, _ in sections] if sections else None,
                "files": files,
                "truncated": len(matched) > SECTION_CAP,
            }
        except ValueError as e:
            return error_payload(str(e), data_source="skill")
