#!/usr/bin/env python3
"""
Merge multiple book-to-skill generated skills into one unified skill.

Algorithm:
  1. Read SKILL.md from each source skill at ~/.config/opencode/skills/<slug>/
  2. Extract frontmatter, Core Frameworks, Chapter Index, Topic Index
  3. Create unified SKILL.md with merged content
  4. Copy chapter files from sources with source-slug prefix
  5. Copy glossary/patterns/cheatsheet from the PRIMARY (first) skill
  6. Generate cross_references.md mapping shared concepts across skills

Usage:
  python3 merge_skills.py --skills wyckoff-2-0 volume-profile volume-price-analysis --output wyckoff-complete
  python3 merge_skills.py --skills trading-against-the-crowd --output contrarian-trading --json
"""

import argparse
import json
import os
import re
import shutil
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SKILLS_HOME = Path.home() / ".config" / "opencode" / "skills"

FRAMEWORK_SIMILARITY_THRESHOLD = 0.8


def similarity(a: str, b: str) -> float:
    """Compute string similarity using SequenceMatcher (0.0 to 1.0)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse YAML frontmatter manually with regex."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    body = match.group(1)
    result: dict[str, Any] = {}
    key: str | None = None
    list_values: list[str] = []
    for line in body.split("\n"):
        stripped = line.rstrip()
        list_match = re.match(r"^\s*-\s+(.*)", stripped)
        if list_match:
            list_values.append(list_match.group(1).strip())
            continue
        if list_values and key is not None:
            result[key] = list_values
            list_values = []
            key = None
        key_match = re.match(r"^(\w[\w-]*)\s*:\s*(.*)", stripped)
        if key_match:
            key = key_match.group(1)
            value = key_match.group(2).strip().strip('"').strip("'")
            if value:
                result[key] = value
                key = None
            else:
                list_values = []
    if list_values and key is not None:
        result[key] = list_values
    return result


def render_frontmatter(fm: dict[str, Any]) -> str:
    """Render a dict as YAML frontmatter string."""
    lines: list[str] = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                formatted = f'"{item}"' if " " in item or ":" in item else item
                lines.append(f"  - {formatted}")
        elif isinstance(value, str):
            if "\n" in value or '"' in value:
                lines.append(f'{key}: >-')
                for vline in value.split("\n"):
                    lines.append(f"  {vline.strip()}")
            else:
                lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def extract_section(text: str, heading: str) -> str:
    """Extract the content under a ## heading until the next ## heading."""
    pattern = rf"^## {re.escape(heading)}"
    lines = text.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            start = i + 1
            break
    if start == -1:
        return ""
    content_lines: list[str] = []
    for line in lines[start:]:
        if re.match(r"^##\s", line):
            break
        content_lines.append(line)
    return "\n".join(content_lines).strip()


def extract_core_frameworks(text: str) -> str:
    """Extract the Core Frameworks section from SKILL.md content."""
    return extract_section(text, "Core Frameworks")


def extract_chapter_index(text: str) -> list[dict[str, str]]:
    """Extract chapter index entries from the Chapter Index table."""
    chapters: list[dict[str, str]] = []
    in_table = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Chapter Index"):
            in_table = True
            continue
        if in_table and stripped.startswith("##") and "Chapter" not in stripped:
            break
        if in_table:
            if stripped.startswith("|---") or stripped.startswith("| #"):
                continue
            if stripped.startswith("|"):
                parts = [p.strip() for p in stripped.split("|")[1:-1]]
                if len(parts) >= 3:
                    chapters.append({
                        "num": parts[0],
                        "title": parts[1],
                        "frameworks": parts[2] if len(parts) > 2 else "",
                    })
    return chapters


def extract_topic_index(text: str) -> str:
    """Extract the Topic Index section."""
    return extract_section(text, "Topic Index")


def deduplicate_frameworks(
    all_frameworks: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    Deduplicate frameworks by name similarity.
    Returns unique frameworks with their source.
    """
    merged: list[tuple[str, str, str]] = []
    for _name, source, content in all_frameworks:  # type: ignore[assignment]
        found_similar = False
        for existing_name, existing_source, _ in merged:
            if similarity(_name, existing_name) > FRAMEWORK_SIMILARITY_THRESHOLD:
                found_similar = True
                break
        if not found_similar:
            merged.append((_name, source, content))
    return [(n, s) for n, s, _ in merged]


def resolve_output_dir(output_slug: str) -> Path:
    """Resolve output directory, handling collisions."""
    target = SKILLS_HOME / output_slug
    if not target.exists():
        return target
    counter = 2
    while True:
        candidate = SKILLS_HOME / f"{output_slug}-{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def read_skill(slug: str) -> dict[str, Any] | None:
    """Read a skill's SKILL.md and return structured data."""
    skill_path = SKILLS_HOME / slug
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"WARNING: Skill not found: {skill_path}", file=sys.stderr)
        return None
    text = skill_md.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    chapters_path = skill_path / "chapters"
    chapter_files: list[str] = []
    if chapters_path.exists():
        chapter_files = sorted(
            f.name for f in chapters_path.iterdir() if f.suffix == ".md"
        )
    return {
        "slug": slug,
        "path": skill_path,
        "text": text,
        "frontmatter": frontmatter,
        "chapters_index": extract_chapter_index(text),
        "chapter_files": chapter_files,
    }


def merge_skills(slugs: list[str], output_slug: str) -> dict[str, Any]:
    """Merge multiple skills into one unified skill."""
    if len(slugs) < 1:
        print("ERROR: At least one skill must be specified.", file=sys.stderr)
        sys.exit(1)

    skills = []
    for slug in slugs:
        data = read_skill(slug)
        if data:
            skills.append(data)

    if not skills:
        print("ERROR: No valid skills found.", file=sys.stderr)
        sys.exit(1)

    target_dir = resolve_output_dir(output_slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir = target_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)

    merged_description_parts = []
    merged_allowed_tools: set[str] = set()
    merged_core_frameworks_parts: list[str] = []
    merged_chapters: list[dict[str, str]] = []
    merged_topics_parts: list[str] = []
    all_frameworks: list[tuple[str, str, str]] = []

    for skill in skills:
        fm = skill["frontmatter"]
        desc = fm.get("description", "")
        if desc:
            merged_description_parts.append(f"[{skill['slug']}] {desc}")
        tools = fm.get("allowed-tools", [])
        if isinstance(tools, list):
            merged_allowed_tools.update(tools)

        core_text = extract_core_frameworks(skill["text"])
        if core_text:
            merged_core_frameworks_parts.append(
                f"### From {skill['slug']}\n{core_text}"
            )

        for ch in skill["chapters_index"]:
            merged_chapters.append({
                "num": ch["num"],
                "title": ch["title"],
                "frameworks": ch.get("frameworks", ""),
                "source": skill["slug"],
            })

        topics_text = extract_topic_index(skill["text"])
        if topics_text:
            merged_topics_parts.append(
                f"<!-- from {skill['slug']} -->\n{topics_text}"
            )

        fw_lines = core_text.split("\n")
        for line in fw_lines:
            fw_match = re.match(r"^###?\s+(.+)", line)
            if fw_match:
                all_frameworks.append((
                    fw_match.group(1).strip(),
                    skill["slug"],
                    "",
                ))

    merged_description = "Merged skill from: " + ", ".join(slugs) + ". "
    for part in merged_description_parts:
        merged_description += part + " "

    allowed_tools_list = sorted(merged_allowed_tools)
    if "read" not in allowed_tools_list:
        allowed_tools_list.insert(0, "read")
    if "grep" not in allowed_tools_list:
        allowed_tools_list.append("grep")

    unique_frameworks = deduplicate_frameworks(all_frameworks)

    frontmatter = {
        "name": output_slug,
        "description": merged_description.strip(),
        "allowed-tools": allowed_tools_list,
    }

    renamed_chapters: list[dict[str, str]] = []
    for ch in merged_chapters:
        new_num = ch["num"]
        renamed_chapters.append({
            "num": new_num,
            "title": ch["title"],
            "frameworks": ch["frameworks"],
            "source": ch["source"],
        })

    cross_refs: list[str] = []
    concepts: dict[str, set[str]] = {}
    for skill in skills:
        topics = extract_topic_index(skill["text"])
        for line in topics.split("\n"):
            link_match = re.match(r"^\s*-\s*\*\*(.+?)\*\*", line)
            if link_match:
                concept = link_match.group(1).strip()
                if concept not in concepts:
                    concepts[concept] = set()
                concepts[concept].add(skill["slug"])

    shared = {c: s for c, s in concepts.items() if len(s) > 1}
    if shared:
        cross_refs.append("## Shared Concepts Across Skills")
        cross_refs.append("")
        for concept, sources in sorted(shared.items()):
            cross_refs.append(
                f"- **{concept}** — covered in: {', '.join(sorted(sources))}"
            )
    else:
        cross_refs.append("## Shared Concepts Across Skills")
        cross_refs.append("")
        cross_refs.append("No significant concept overlap detected across merged skills.")

    primary = skills[0]
    for filename in ["glossary.md", "patterns.md", "cheatsheet.md"]:
        src = primary["path"] / filename
        dst = target_dir / filename
        if src.exists():
            shutil.copy2(src, dst)

    copied_files: list[str] = []
    for skill in skills:
        chapters_src = skill["path"] / "chapters"
        if not chapters_src.exists():
            continue
        for ch_file in sorted(chapters_src.iterdir()):
            if ch_file.suffix != ".md":
                continue
            new_name = f"{skill['slug']}_{ch_file.name}"
            dst = chapters_dir / new_name
            counter = 1
            while dst.exists():
                counter += 1
                base, ext = os.path.splitext(new_name)
                new_name_candidate = f"{base}_{counter}{ext}"
                if new_name_candidate == ch_file.name:
                    continue
                base_part = f"{skill['slug']}_{os.path.splitext(ch_file.name)[0]}"
                new_name = f"{base_part}_{counter}{ch_file.suffix}"
                dst = chapters_dir / new_name
            shutil.copy2(ch_file, dst)
            copied_files.append(str(dst.relative_to(target_dir)))

    skill_md_content = _build_merged_skill_md(
        frontmatter=frontmatter,
        output_slug=output_slug,
        sources=slugs,
        core_frameworks=merged_core_frameworks_parts,
        chapters=renamed_chapters,
        unique_frameworks=unique_frameworks,
        topics_parts=merged_topics_parts,
        copied_files=copied_files,
    )
    (target_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")

    cross_refs_path = target_dir / "cross_references.md"
    cross_refs_path.write_text("\n".join(cross_refs) + "\n", encoding="utf-8")

    return {
        "output_dir": str(target_dir),
        "output_slug": output_slug,
        "sources": slugs,
        "chapters_merged": len(renamed_chapters),
        "frameworks_merged": len(unique_frameworks),
        "files_copied": len(copied_files),
    }


def _build_merged_skill_md(
    *,
    frontmatter: dict[str, Any],
    output_slug: str,
    sources: list[str],
    core_frameworks: list[str],
    chapters: list[dict[str, str]],
    unique_frameworks: list[tuple[str, str]],
    topics_parts: list[str],
    copied_files: list[str],
) -> str:
    """Build the merged SKILL.md content."""
    lines: list[str] = []
    lines.append(render_frontmatter(frontmatter))
    lines.append("")
    lines.append(f"# Merged Skill: {output_slug}")
    lines.append(
        f"**Sources**: {', '.join(sources)} | "
        f"**Chapters**: {len(chapters)} | "
        f"**Generated**: merged from {len(sources)} skills"
    )
    lines.append("")
    lines.append("## How to Use This Skill")
    lines.append("- **Without arguments** — load core frameworks from all merged skills")
    lines.append(
        "- **With a topic** — find and read the relevant chapter across sources"
    )
    lines.append("- **With chapter** — e.g. `ch05` to load that chapter")
    lines.append('- **Cross-references** — see [cross_references.md](cross_references.md)')
    lines.append("")
    lines.append("## Core Frameworks & Mental Models")
    lines.append("")

    if unique_frameworks:
        lines.append("### Deduplicated Framework List")
        for fw, src in sorted(unique_frameworks, key=lambda x: x[0].lower()):
            lines.append(f"- **{fw}** `[{src}]`")
        lines.append("")

    for fw_section in core_frameworks:
        lines.append(fw_section)
        lines.append("")

    lines.append("## Chapter Index")
    lines.append("| # | Title | Key Frameworks | Source |")
    lines.append("|---|---|---|---|")
    for i, ch in enumerate(chapters, 1):
        fw = ch.get("frameworks", "")
        src = ch.get("source", "")
        file_ref = ""
        for cf in copied_files:
            if cf.startswith(f"{src}_ch{int(ch['num']):02d}-") or cf.startswith(f"{src}_ch{ch['num']}-"):
                file_ref = f"[{ch['num']}]({cf})"
                break
        if not file_ref:
            file_ref = ch["num"]
        lines.append(f"| {file_ref} | {ch['title']} | {fw} | [{src}] |")
    lines.append("")

    lines.append("## Topic Index")
    for topic_section in topics_parts:
        lines.append(topic_section)
        lines.append("")

    lines.append("## Supporting Files")
    lines.append("- [glossary.md](glossary.md)")
    lines.append("- [patterns.md](patterns.md)")
    lines.append("- [cheatsheet.md](cheatsheet.md)")
    lines.append("- [cross_references.md](cross_references.md)")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge multiple book-to-skill skills into one unified skill."
    )
    parser.add_argument(
        "--skills",
        nargs="+",
        required=True,
        help="List of skill slugs to merge (e.g. wyckoff-2-0 volume-profile)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output skill slug (e.g. wyckoff-complete)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    result = merge_skills(args.skills, args.output)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Merge complete: {result['output_dir']}")
        print(f"  Sources merged: {', '.join(result['sources'])}")
        print(f"  Chapters: {result['chapters_merged']}")
        print(f"  Frameworks (deduplicated): {result['frameworks_merged']}")
        print(f"  Files copied: {result['files_copied']}")
        print(f"  Output: {result['output_dir']}")


if __name__ == "__main__":
    main()
