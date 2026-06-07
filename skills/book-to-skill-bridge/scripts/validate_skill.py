#!/usr/bin/env python3
"""
Validate the quality of a generated book-to-skill skill.

Checks:
  1. Chapter completeness: chapters/ contains a .md file for every chapter
     listed in SKILL.md's Chapter Index table.
  2. Link validity: every markdown link in SKILL.md points to an existing file
     (relative to the skill root).
  3. Token budget: estimate tokens per file (words * 1.3) and check against
     limits: SKILL.md < 4000, chapters 800-1200, glossary < 1500,
     patterns < 2000, cheatsheet < 1000.
  4. Frontmatter validity: YAML frontmatter has required fields
     (name, description, allowed-tools).
  5. Chapter format: each chapter file has at least 2 of these sections:
     "## Core Idea", "## Frameworks", "## Key Concepts", "## Key Takeaways".
  6. No orphan glossary terms: glossary terms reference valid chapters.

Outputs a quality report with line-by-line results, a quality score,
and separated warnings/errors.

Usage:
  python3 validate_skill.py ~/.config/opencode/skills/wyckoff-2-0/
  python3 validate_skill.py ~/.config/opencode/skills/volume-profile/ --json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SKILLS_HOME = Path.home() / ".config" / "opencode" / "skills"

TOKEN_LIMITS = {
    "SKILL.md": 4000,
    "chapter": (800, 1200),
    "glossary.md": 1500,
    "patterns.md": 2000,
    "cheatsheet.md": 1000,
}

REQUIRED_FRONTMATTER_FIELDS = {"name", "description", "allowed-tools"}

REQUIRED_CHAPTER_SECTIONS = {
    "## Core Idea",
    "## Frameworks",
    "## Key Concepts",
    "## Key Takeaways",
}

CHAPTER_INDEX_LINE_RE = re.compile(
    r"^\|\s*(?:Chapter\s*)?(\d+|[a-z]+\d+)\s*\|"
)
CHAPTER_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def estimate_tokens(text: str) -> int:
    """Estimate tokens using word count * 1.3 as a rough proxy."""
    return int(len(text.split()) * 1.3)


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter manually with regex (no yaml dependency)."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return None
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


def extract_chapters_from_skill_md(skill_path: Path) -> list[dict[str, str]]:
    """Extract chapter entries from the Chapter Index table in SKILL.md."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return []
    text = skill_md.read_text(encoding="utf-8")
    in_table = False
    chapters: list[dict[str, str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Chapter Index"):
            in_table = True
            continue
        if in_table and stripped.startswith("##") and not stripped.startswith("## Chapter"):
            break
        if in_table:
            if stripped.startswith("|---") or stripped.startswith("| #"):
                continue
            if stripped.startswith("|"):
                parts = [p.strip() for p in stripped.split("|")[1:-1]]
                if len(parts) >= 2:
                    chapters.append({
                        "num": parts[0],
                        "title": parts[1] if len(parts) > 1 else "",
                    })
    return chapters


def extract_links_from_skill_md(skill_path: Path) -> list[str]:
    """Extract all relative links from SKILL.md."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return []
    text = skill_md.read_text(encoding="utf-8")
    links: list[str] = []
    for match in CHAPTER_LINK_RE.finditer(text):
        url = match.group(2)
        if not url.startswith(("http://", "https://", "#")):
            links.append(url)
    return links


def extract_glossary_terms(skill_path: Path) -> list[dict[str, Any]]:
    """Extract glossary terms and their chapter references."""
    glossary_path = skill_path / "glossary.md"
    if not glossary_path.exists():
        return []
    text = glossary_path.read_text(encoding="utf-8")
    terms: list[dict[str, Any]] = []
    chapter_ref_re = re.compile(r"(?:Ch\.?|ch|Chapter)\s*(\d+)", re.IGNORECASE)
    for line in text.split("\n"):
        term_match = re.match(r"^\s*-\s*\*\*(.+?)\*\*\s*[:\-—]", line)
        if term_match:
            term = term_match.group(1).strip()
            ref_match = chapter_ref_re.search(line)
            chapter_ref = int(ref_match.group(1)) if ref_match else None
            terms.append({"term": term, "chapter_ref": chapter_ref})
    return terms


def check_1_chapter_completeness(
    skill_path: Path, chapters: list[dict[str, str]]
) -> tuple[bool, list[str], list[str]]:
    """Check that chapters/ has a .md file for every chapter in the index."""
    chapters_dir = skill_path / "chapters"
    errors: list[str] = []
    warnings: list[str] = []
    if not chapters or not chapters_dir.exists():
        return False, [], ["No chapters found in SKILL.md Chapter Index"]
    existing_files = set(
        f.name for f in chapters_dir.iterdir() if f.suffix == ".md"
    )
    for ch in chapters:
        found = any(
            f.startswith(f"ch{int(ch['num']):02d}-")
            or f.startswith(f"ch{ch['num']}-")
            for f in existing_files
        )
        if not found:
            errors.append(
                f"Chapter {ch['num']} ({ch['title']}) listed in index "
                f"but no matching file in chapters/"
            )
    orphan_files = []
    for fname in sorted(existing_files):
        matched = False
        for ch in chapters:
            num_str = ch["num"]
            try:
                num_padded = f"{int(num_str):02d}"
            except ValueError:
                num_padded = num_str
            if fname.startswith(f"ch{num_str}-") or fname.startswith(
                f"ch{num_padded}-"
            ):
                matched = True
                break
        if not matched:
            orphan_files.append(fname)
    if orphan_files:
        warnings.append(
            f"Orphan chapter files (not in index): {', '.join(orphan_files)}"
        )
    return len(errors) == 0, warnings, errors


def check_2_link_validity(
    skill_path: Path, links: list[str]
) -> tuple[bool, list[str], list[str]]:
    """Verify every markdown link in SKILL.md points to an existing file."""
    errors: list[str] = []
    for link in links:
        target = skill_path / link
        if not target.exists():
            errors.append(f"Broken link in SKILL.md: {link} (-> {target})")
    return len(errors) == 0, [], errors


def check_3_token_budgets(
    skill_path: Path, chapters: list[dict[str, str]]
) -> tuple[bool, list[str], list[str]]:
    """Estimate tokens per file and check against budget limits."""
    warnings: list[str] = []
    errors: list[str] = []
    chapters_dir = skill_path / "chapters"

    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        text = skill_md.read_text(encoding="utf-8")
        tokens = estimate_tokens(text)
        limit = TOKEN_LIMITS["SKILL.md"]
        if tokens > limit:
            warnings.append(
                f"SKILL.md: ~{tokens} tokens (limit: {limit})"
            )

    for file_name, limit, label in [
        ("glossary.md", TOKEN_LIMITS["glossary.md"], "glossary"),
        ("patterns.md", TOKEN_LIMITS["patterns.md"], "patterns"),
        ("cheatsheet.md", TOKEN_LIMITS["cheatsheet.md"], "cheatsheet"),
    ]:
        file_path = skill_path / file_name
        if file_path.exists():
            text = file_path.read_text(encoding="utf-8")
            tokens = estimate_tokens(text)
            if tokens > limit:
                warnings.append(
                    f"{file_name}: ~{tokens} tokens (limit: {limit})"
                )

    if chapters_dir.exists():
        ch_min, ch_max = TOKEN_LIMITS["chapter"]
        for f in chapters_dir.iterdir():
            if f.suffix == ".md":
                text = f.read_text(encoding="utf-8")
                tokens = estimate_tokens(text)
                if tokens > ch_max:
                    warnings.append(
                        f"chapters/{f.name}: ~{tokens} tokens "
                        f"(max: {ch_max})"
                    )
                elif tokens < ch_min:
                    warnings.append(
                        f"chapters/{f.name}: ~{tokens} tokens "
                        f"(min: {ch_min})"
                    )

    return len(errors) == 0, warnings, errors


def check_4_frontmatter(
    skill_path: Path,
) -> tuple[bool, list[str], list[str]]:
    """Check YAML frontmatter has required fields."""
    errors: list[str] = []
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, [], ["SKILL.md not found"]
    text = skill_md.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    if frontmatter is None:
        return False, [], ["No frontmatter found in SKILL.md"]
    missing = REQUIRED_FRONTMATTER_FIELDS - set(frontmatter.keys())
    if missing:
        errors.append(f"Missing frontmatter fields: {', '.join(sorted(missing))}")
    return len(errors) == 0, [], errors


def check_5_chapter_format(
    skill_path: Path,
) -> tuple[bool, list[str], list[str]]:
    """Check that each chapter has at least 2 required sections."""
    errors: list[str] = []
    chapters_dir = skill_path / "chapters"
    if not chapters_dir.exists():
        return False, [], ["chapters/ directory not found"]
    for f in sorted(chapters_dir.iterdir()):
        if f.suffix != ".md":
            continue
        text = f.read_text(encoding="utf-8")
        present = 0
        missing_sections: list[str] = []
        for section in REQUIRED_CHAPTER_SECTIONS:
            if section in text:
                present += 1
            else:
                missing_sections.append(section)
        if present < 2:
            errors.append(
                f"chapters/{f.name}: only {present}/4 required sections "
                f"found (missing: {', '.join(missing_sections)})"
            )
    return len(errors) == 0, [], errors


def check_6_orphan_glossary(
    skill_path: Path, chapters: list[dict[str, str]]
) -> tuple[bool, list[str], list[str]]:
    """Check that glossary terms reference valid chapters."""
    warnings: list[str] = []
    terms = extract_glossary_terms(skill_path)
    if not terms:
        return True, [], []
    chapter_nums = set()
    for ch in chapters:
        try:
            chapter_nums.add(int(ch["num"]))
        except ValueError:
            pass
    orphan_terms = []
    for term in terms:
        if term["chapter_ref"] is not None and term["chapter_ref"] not in chapter_nums:
            orphan_terms.append(
                f"{term['term']} (refs Ch {term['chapter_ref']}, "
                f"but skill has chapters: {sorted(chapter_nums)})"
            )
    if orphan_terms:
        warnings.append(
            f"Orphan glossary references: {len(orphan_terms)} term(s) "
            f"reference non-existent chapters"
        )
    return True, warnings, []


def run_all_checks(skill_path: Path) -> dict[str, Any]:
    """Run all quality checks and return a detailed report."""
    chapters = extract_chapters_from_skill_md(skill_path)
    links = extract_links_from_skill_md(skill_path)

    checks: list[dict[str, Any]] = []

    for name, func, args in [
        ("Chapter completeness", check_1_chapter_completeness, {"chapters": chapters}),
        ("Link validity", check_2_link_validity, {"links": links}),
        ("Token budgets", check_3_token_budgets, {"chapters": chapters}),
        ("Frontmatter validity", check_4_frontmatter, {}),
        ("Chapter format", check_5_chapter_format, {}),
        ("Orphan glossary terms", check_6_orphan_glossary, {"chapters": chapters}),
    ]:
        passed, warnings, errors = func(skill_path, **args)
        checks.append({
            "name": name,
            "passed": passed,
            "warnings": warnings,
            "errors": errors,
        })

    passed_count = sum(1 for c in checks if c["passed"] and not c["errors"])
    total = len(checks)
    score = round((passed_count / total) * 100, 1) if total > 0 else 0.0

    return {
        "skill_path": str(skill_path),
        "skill_name": skill_path.name,
        "checks": checks,
        "summary": {
            "total_checks": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "score": score,
            "total_errors": sum(len(c["errors"]) for c in checks),
            "total_warnings": sum(len(c["warnings"]) for c in checks),
        },
    }


def format_report_text(report: dict[str, Any]) -> str:
    """Format the quality report as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"  Quality Report: {report['skill_name']}")
    lines.append("=" * 60)
    lines.append("")

    for i, check in enumerate(report["checks"], 1):
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  {i}. {check['name']}: {status}")
        if check["errors"]:
            for err in check["errors"]:
                lines.append(f"     ERROR: {err}")
        if check["warnings"]:
            for warn in check["warnings"]:
                lines.append(f"     WARN:  {warn}")
        lines.append("")

    summary = report["summary"]
    lines.append("-" * 60)
    lines.append(f"  Quality Score: {summary['score']}% "
                 f"({summary['passed']}/{summary['total_checks']} checks passed)")
    lines.append(f"  Errors: {summary['total_errors']}  "
                 f"Warnings: {summary['total_warnings']}")
    lines.append("-" * 60)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the quality of a generated book-to-skill skill."
    )
    parser.add_argument(
        "skill_dir",
        help="Path to the skill directory (e.g. ~/.config/opencode/skills/wyckoff-2-0/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the report as JSON",
    )
    args = parser.parse_args()

    skill_path = Path(args.skill_dir).expanduser().resolve()
    if not skill_path.is_dir():
        print(f"ERROR: Not a directory: {skill_path}", file=sys.stderr)
        sys.exit(1)

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"ERROR: SKILL.md not found in {skill_path}", file=sys.stderr)
        sys.exit(1)

    report = run_all_checks(skill_path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report_text(report))

    summary = report["summary"]
    if summary["total_errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
