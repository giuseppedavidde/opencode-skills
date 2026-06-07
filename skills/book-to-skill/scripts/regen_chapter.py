#!/usr/bin/env python3
"""
Regenerate a single chapter of an existing skill without touching others.

Usage:
  python3 regen_chapter.py --skill wyckoff-2-0 --chapter 5
  python3 regen_chapter.py --skill wyckoff-2-0 --chapter 5 --source /path/to/book.pdf
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

SKILLS_HOME = Path.home() / ".config" / "opencode" / "skills"
WORKDIR_BASE = Path(
    os.environ.get(
        "BOOK_SKILL_WORKDIR",
        str(Path(tempfile.gettempdir()) / "book_skill_work"),
    )
)
STANDARD_TEMPLATE_SECTIONS = [
    "## Core Idea",
    "## Frameworks Introduced",
    "## Key Concepts",
    "## Anti-patterns",
    "## Key Takeaways",
]

CHAPTER_HEADING_RE = re.compile(
    r"^\s*(?:Chapter|CHAPTER|ch\.?)\s*(\d+)",
    re.IGNORECASE,
)


def find_skill_dir(skill_slug: str) -> Path:
    """Find the skill directory, trying multiple possible locations."""
    candidates = [
        SKILLS_HOME / skill_slug,
        Path.cwd() / skill_slug,
        Path(skill_slug).resolve(),
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "SKILL.md").exists():
            return cand
    print(
        f"ERROR: Skill '{skill_slug}' not found in any known location.",
        file=sys.stderr,
    )
    sys.exit(1)


def find_chapter_file(skill_dir: Path, chapter_num: int) -> Path | None:
    """Find the chapter file matching the given chapter number."""
    chapters_dir = skill_dir / "chapters"
    if not chapters_dir.exists():
        return None
    patterns = [
        f"ch{chapter_num:02d}-",
        f"ch{chapter_num:02d}_",
        f"ch{chapter_num}-",
        f"ch{chapter_num}_",
        f"chapter_{chapter_num:02d}",
        f"chapter-{chapter_num:02d}",
    ]
    for f in sorted(chapters_dir.iterdir()):
        if f.suffix != ".md":
            continue
        for pat in patterns:
            if f.name.lower().startswith(pat.lower()):
                return f
    for f in sorted(chapters_dir.iterdir()):
        if f.suffix == ".md" and CHAPTER_HEADING_RE.match(f.name):
            match = CHAPTER_HEADING_RE.match(f.name)
            if match and int(match.group(1)) == chapter_num:
                return f
    return None


def find_full_text_path(skill_slug: str) -> Path | None:
    """Find the stored full_text.txt for the skill."""
    candidates = [
        WORKDIR_BASE / skill_slug / "full_text.txt",
        WORKDIR_BASE / "full_text.txt",
        Path(tempfile.gettempdir()) / "book_skill_work" / skill_slug / "full_text.txt",
        Path(tempfile.gettempdir()) / "book_skill_work" / "full_text.txt",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def find_chapter_boundaries(
    full_text: str, chapter_num: int
) -> tuple[int, int] | None:
    """
    Find the start and end line numbers for a given chapter in the full text.
    Searches for 'Chapter N' or equivalent headings.
    """
    lines = full_text.split("\n")
    chapter_start = -1
    chapter_end = len(lines)

    for i, line in enumerate(lines):
        match = CHAPTER_HEADING_RE.match(line.strip())
        if match:
            found_num = int(match.group(1))
            if found_num == chapter_num:
                chapter_start = i
            elif found_num > chapter_num and chapter_start >= 0:
                chapter_end = i
                break
            elif found_num == chapter_num + 1 and chapter_start >= 0:
                chapter_end = i
                break
            elif found_num > chapter_num and chapter_start < 0:
                continue

    if chapter_start < 0:
        return None
    return (chapter_start, chapter_end)


def extract_chapter_text(
    skill_slug: str, chapter_num: int
) -> tuple[str | None, str]:
    """Extract chapter text from the stored full_text.txt."""
    full_text_path = find_full_text_path(skill_slug)
    if full_text_path is None:
        return None, f"No full_text.txt found for skill '{skill_slug}'"
    full_text = full_text_path.read_text(encoding="utf-8", errors="replace")
    boundaries = find_chapter_boundaries(full_text, chapter_num)
    if boundaries is None:
        return None, (
            f"Chapter {chapter_num} not found in full_text.txt "
            f"({full_text_path})"
        )
    start, end = boundaries
    lines = full_text.split("\n")
    chapter_text = "\n".join(lines[start:end])
    if not chapter_text.strip():
        return None, f"Chapter {chapter_num} text is empty"
    return chapter_text, ""


def update_skill_md_chapter_title(
    skill_dir: Path, chapter_num: int, old_title: str, new_title: str
) -> bool:
    """Update the chapter title in SKILL.md's Chapter Index table."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False
    text = skill_md.read_text(encoding="utf-8")
    if old_title == new_title:
        return False

    old_title_escaped = re.escape(old_title)
    pattern = re.compile(
        rf"^(\|\s*{chapter_num}\s*\|\s*){old_title_escaped}(\s*\|)",
        re.MULTILINE,
    )
    new_text, count = pattern.subn(rf"\g<1>{new_title}\g<2>", text)
    if count > 0:
        skill_md.write_text(new_text, encoding="utf-8")
        return True
    return False


def extract_chapter_title_from_text(chapter_text: str) -> str:
    """Extract the chapter title from the first heading in the text."""
    for line in chapter_text.split("\n")[:10]:
        stripped = line.strip()
        match = re.match(r"^#\s*Chapter\s+\d+[:\-—]?\s*(.+)", stripped, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.match(r"^(?:Chapter\s+\d+|CHAPTER\s+\d+)[:\-—]?\s*(.+)", stripped)
        if match:
            return match.group(1).strip()
    return ""


def build_chapter_markdown(
    chapter_num: int, chapter_text: str, skill_slug: str, mode: str = "text"
) -> str:
    """Build a standard chapter markdown file from extracted text."""
    title = extract_chapter_title_from_text(chapter_text) or f"Chapter {chapter_num}"
    lines: list[str] = []
    lines.append(f"# Chapter {chapter_num}: {title}")
    lines.append("")

    for section in STANDARD_TEMPLATE_SECTIONS:
        if section == "## Anti-patterns" and mode not in ("technical",):
            continue
        lines.append(section)
        lines.append("")
        if section == "## Core Idea":
            first_sentence = chapter_text.split(".")[0].strip()
            lines.append(
                f"{first_sentence[:200]}."
                if len(first_sentence) > 200
                else first_sentence
            )
        else:
            lines.append("*[Regenerated — review and expand this section]*")
        lines.append("")

    return "\n".join(lines)


def run_extract_if_needed(
    source_path: str, skill_slug: str, chapter_num: int
) -> tuple[str | None, str]:
    """Try to re-extract chapter text from the source PDF."""
    extract_script = SKILLS_HOME / "book-to-skill" / "scripts" / "extract.py"
    if not extract_script.exists():
        return None, (
            f"extract.py not found at {extract_script}; "
            f"cannot re-extract from source"
        )

    full_text_path = find_full_text_path(skill_slug)
    if full_text_path is not None:
        return extract_chapter_text(skill_slug, chapter_num)

    return None, (
        f"No full_text.txt found for '{skill_slug}'. "
        f"Run extract.py on the source first."
    )


def regen_chapter(
    skill_slug: str,
    chapter_num: int,
    source_path: str | None = None,
) -> str:
    """Regenerate a single chapter file."""
    skill_dir = find_skill_dir(skill_slug)
    chapter_file = find_chapter_file(skill_dir, chapter_num)
    if chapter_file is None:
        print(
            f"ERROR: Chapter {chapter_num} file not found in "
            f"{skill_dir / 'chapters'}",
            file=sys.stderr,
        )
        sys.exit(1)

    if chapter_file is not None and source_path is None:
        current_content = chapter_file.read_text(encoding="utf-8")
        print(
            f"WARNING: No source provided to regenerate from. "
            f"Chapter left unchanged.\n"
            f"\nCurrent content of {chapter_file.name}:"
        )
        print("-" * 50)
        print(current_content[:2000])
        if len(current_content) > 2000:
            print(f"\n... ({len(current_content)} chars total, truncated)")
        return "Chapter left unchanged (no --source provided)"

    chapter_text, error = run_extract_if_needed(
        source_path if source_path else "", skill_slug, chapter_num
    )
    if chapter_text is None:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    if chapter_file is not None:
        old_content = chapter_file.read_text(encoding="utf-8")
        old_title_match = re.match(
            r"^#\s*Chapter\s+\d+[:\-—]?\s*(.+)",
            old_content.split("\n")[0],
            re.IGNORECASE,
        )
        old_title = old_title_match.group(1).strip() if old_title_match else ""
    else:
        old_title = ""

    new_content = build_chapter_markdown(
        chapter_num, chapter_text, skill_slug
    )
    new_title = extract_chapter_title_from_text(chapter_text) or old_title

    chapter_file.write_text(new_content, encoding="utf-8")

    if new_title and new_title != old_title:
        updated = update_skill_md_chapter_title(
            skill_dir, chapter_num, old_title, new_title
        )
        if updated:
            print(f"Updated chapter title in SKILL.md: '{old_title}' -> '{new_title}'")
        else:
            print(
                f"Note: Could not update title in SKILL.md "
                f"(old: '{old_title}', new: '{new_title}')"
            )

    return f"Chapter {chapter_file.name} regenerated successfully"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate a single chapter of an existing skill."
    )
    parser.add_argument(
        "--skill",
        required=True,
        help="Skill slug (e.g. wyckoff-2-0)",
    )
    parser.add_argument(
        "--chapter",
        type=int,
        required=True,
        help="Chapter number to regenerate (e.g. 5)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Optional path to the source PDF/book to re-extract from",
    )
    args = parser.parse_args()

    result = regen_chapter(args.skill, args.chapter, args.source)
    print(result)


if __name__ == "__main__":
    main()
