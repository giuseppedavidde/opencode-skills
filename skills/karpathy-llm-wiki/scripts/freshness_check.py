#!/usr/bin/env python3
"""Check knowledge freshness of wiki articles.

Evaluates each article's knowledge freshness based on source age, time since
last update, and whether newer sources exist on the same topic. Assigns a
freshness score (0-100) and tier: Fresh, Stale, or Rotten.

Usage:
    python3 freshness_check.py --wiki-root /path/to/wiki
    python3 freshness_check.py --wiki-root /path/to/wiki --article path/to/article.md
    python3 freshness_check.py --wiki-root /path/to/wiki --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class FreshnessResult(BaseModel):
        """Freshness evaluation for a single article."""
        article_path: str
        article_title: str
        freshness_score: int
        tier: str  # "Fresh", "Stale", "Rotten"
        oldest_source_date: Optional[str] = None
        oldest_source_days: Optional[int] = None
        last_updated_date: Optional[str] = None
        last_updated_days: Optional[int] = None
        issues: list[str] = Field(default_factory=list)

    class FreshnessReport(BaseModel):
        """Complete freshness report."""
        wiki_root: str
        checked_at: str
        article_count: int
        results: list[FreshnessResult] = Field(default_factory=list)
        summary: dict[str, int] = Field(default_factory=dict)
else:
    from dataclasses import dataclass, field, asdict

    @dataclass
    class FreshnessResult:
        """Freshness evaluation for a single article."""
        article_path: str
        article_title: str
        freshness_score: int
        tier: str  # "Fresh", "Stale", "Rotten"
        oldest_source_date: Optional[str] = None
        oldest_source_days: Optional[int] = None
        last_updated_date: Optional[str] = None
        last_updated_days: Optional[int] = None
        issues: list[str] = field(default_factory=list)

    @dataclass
    class FreshnessReport:
        """Complete freshness report."""
        wiki_root: str
        checked_at: str
        article_count: int
        results: list[FreshnessResult] = field(default_factory=list)
        summary: dict[str, int] = field(default_factory=dict)

        def model_dump(self) -> dict:
            """Serialize the dataclass to a dict (Pydantic-compatible interface)."""
            return asdict(self)


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Age penalty thresholds
OLDEST_SOURCE_365_DAYS = 365
OLDEST_SOURCE_730_DAYS = 730
LAST_UPDATE_90_DAYS = 90
LAST_UPDATE_180_DAYS = 180
NEWER_SOURCE_PENALTY = 15


def _extract_metadata(filepath: Path) -> dict[str, Any]:
    """Extract metadata from a wiki article.

    Returns dict with keys: title, source_dates (list of date strings),
    updated_date (str or None), raw_links (list), and content_lines (list).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Warning: Could not read {filepath}: {exc}", file=sys.stderr)
        return {"title": "", "source_dates": [], "updated_date": None,
                "raw_links": [], "content_lines": []}

    title = ""
    source_dates: list[str] = []
    updated_date: Optional[str] = None
    raw_links: list[str] = []
    content_lines: list[str] = []
    past_metadata = False

    for line in text.split("\n"):
        stripped = line.strip()

        # Title
        if not title and stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            continue

        if not past_metadata:
            # Sources line: > Sources: Author1, YYYY-MM-DD; Author2, YYYY-MM-DD
            if stripped.startswith("> Sources:") or stripped.startswith("> Sources "):
                dates = DATE_RE.findall(stripped)
                source_dates.extend(dates)

            # Updated line: > Updated: YYYY-MM-DD
            elif stripped.startswith("> Updated:") or stripped.startswith("> Updated "):
                match = DATE_RE.search(stripped)
                if match:
                    updated_date = match.group(1)

            # Archived line: > Archived: YYYY-MM-DD
            elif stripped.startswith("> Archived:") or stripped.startswith("> Archived "):
                match = DATE_RE.search(stripped)
                if match:
                    updated_date = match.group(1)

            # Raw line: > Raw: [text](path); [text](path)
            elif stripped.startswith("> Raw:") or stripped.startswith("> Raw "):
                links = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", stripped)
                raw_links.extend(link[1] for link in links)

            # End of metadata block
            elif stripped == "" or stripped.startswith("> "):
                if stripped == "" and source_dates:
                    past_metadata = True
                continue
            elif not stripped.startswith(">"):
                past_metadata = True
                content_lines.append(line)
        else:
            content_lines.append(line)

    return {
        "title": title,
        "source_dates": source_dates,
        "updated_date": updated_date,
        "raw_links": raw_links,
        "content_lines": content_lines,
    }


def _find_articles(wiki_root: Path, specific_article: Optional[str] = None) -> list[Path]:
    """Find wiki articles, optionally filtering to a specific one."""
    if specific_article:
        candidate = wiki_root / specific_article
        if candidate.exists() and candidate.suffix == ".md":
            return [candidate]
        # Try matching filename
        matches = list(wiki_root.rglob(specific_article))
        if len(matches) == 1:
            return [matches[0]]
        print(f"Error: Article '{specific_article}' not found uniquely.", file=sys.stderr)
        sys.exit(1)

    articles: list[Path] = []
    if not wiki_root.is_dir():
        return articles
    for filepath in wiki_root.rglob("*.md"):
        if filepath.name in ("index.md", "log.md"):
            continue
        articles.append(filepath)
    return sorted(articles)


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a YYYY-MM-DD date string."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _days_ago(date_str: Optional[str]) -> Optional[int]:
    """Calculate days between a date string and now."""
    if not date_str:
        return None
    dt = _parse_date(date_str)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return (now - dt).days


def _has_newer_sources_on_topic(
    article_path: Path,
    article_metadata: dict[str, Any],
    all_metadata: dict[str, dict[str, Any]],
    wiki_root: Path,
) -> bool:
    """Check if any article on the same topic has newer source dates.

    Two articles are on the "same topic" if they share keywords in their
    content or are in the same wiki subdirectory.
    """
    article_dir = article_path.parent.relative_to(wiki_root)
    article_dates = [d for d in article_metadata.get("source_dates", []) if d]

    # Extract keywords from article content
    article_content = " ".join(article_metadata.get("content_lines", []))
    article_keywords = set(
        re.findall(r"\b[a-zA-Z]{4,}\b", article_content.lower())
    )

    latest_own_date: Optional[str] = None
    if article_dates:
        latest_own_date = max(article_dates)

    for other_path, other_meta in all_metadata.items():
        if other_path == article_path:
            continue

        other_dir = other_path.parent.relative_to(wiki_root)
        other_dates = [d for d in other_meta.get("source_dates", []) if d]

        if not other_dates:
            continue

        other_latest = max(other_dates)

        # Skip if other article is not newer
        if latest_own_date and other_latest <= latest_own_date:
            continue

        # Check same directory
        if other_dir == article_dir:
            return True

        # Check keyword overlap
        other_content = " ".join(other_meta.get("content_lines", []))
        other_keywords = set(
            re.findall(r"\b[a-zA-Z]{4,}\b", other_content.lower())
        )
        common = article_keywords & other_keywords
        # Consider same topic if >= 20% keyword overlap
        if article_keywords and len(common) >= max(1, len(article_keywords) * 0.2):
            return True

    return False


def _compute_freshness(
    metadata: dict[str, Any],
    filepath: Path,
    wiki_root: Path,
    all_metadata: dict[str, dict[str, Any]],
) -> FreshnessResult:
    """Compute freshness score and tier for a single article."""
    score = 100
    issues: list[str] = []

    rel_path = str(filepath.relative_to(wiki_root))
    title = metadata.get("title", "") or filepath.stem.replace("-", " ").title()

    # 1. Age of oldest source
    source_dates: list[str] = metadata.get("source_dates", [])
    oldest_source_date: Optional[str] = None
    oldest_source_days: Optional[int] = None

    if source_dates:
        sorted_dates = sorted(source_dates)
        oldest_source_date = sorted_dates[0]
        oldest_source_days = _days_ago(oldest_source_date)

        if oldest_source_days is not None:
            if oldest_source_days > OLDEST_SOURCE_730_DAYS:
                score -= 40
                issues.append(
                    f"Oldest source ({oldest_source_date}) is over 730 days old "
                    f"({oldest_source_days} days) — penalty: -40"
                )
            elif oldest_source_days > OLDEST_SOURCE_365_DAYS:
                score -= 20
                issues.append(
                    f"Oldest source ({oldest_source_date}) is over 365 days old "
                    f"({oldest_source_days} days) — penalty: -20"
                )
    else:
        # No source dates found - moderate penalty
        score -= 10
        issues.append("No source dates found in metadata — penalty: -10")

    # 2. Time since last update
    updated_date: Optional[str] = metadata.get("updated_date")
    if not updated_date:
        # Fall back to file modification time
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
            updated_date = mtime.strftime("%Y-%m-%d")
        except OSError:
            pass

    last_updated_days = _days_ago(updated_date) if updated_date else None

    if last_updated_days is not None:
        if last_updated_days > LAST_UPDATE_180_DAYS:
            score -= 25
            issues.append(
                f"Last updated {last_updated_days} days ago "
                f"({updated_date}) — penalty: -25"
            )
        elif last_updated_days > LAST_UPDATE_90_DAYS:
            score -= 10
            issues.append(
                f"Last updated {last_updated_days} days ago "
                f"({updated_date}) — penalty: -10"
            )

    # 3. Newer sources available on same topic
    if _has_newer_sources_on_topic(filepath, metadata, all_metadata, wiki_root):
        score -= NEWER_SOURCE_PENALTY
        issues.append(
            "Other articles on the same topic have newer sources — penalty: -15"
        )

    # Clamp score to 0-100
    score = max(0, min(100, score))

    # Assign tier
    if score >= 80:
        tier = "Fresh"
    elif score >= 50:
        tier = "Stale"
    else:
        tier = "Rotten"

    if HAS_PYDANTIC:
        return FreshnessResult(
            article_path=rel_path,
            article_title=title,
            freshness_score=score,
            tier=tier,
            oldest_source_date=oldest_source_date,
            oldest_source_days=oldest_source_days,
            last_updated_date=updated_date,
            last_updated_days=last_updated_days,
            issues=issues,
        )
    return FreshnessResult(
        article_path=rel_path,
        article_title=title,
        freshness_score=score,
        tier=tier,
        oldest_source_date=oldest_source_date,
        oldest_source_days=oldest_source_days,
        last_updated_date=updated_date,
        last_updated_days=last_updated_days,
        issues=issues,
    )


def _format_results_text(report: FreshnessReport) -> str:
    """Format freshness report as human-readable table."""
    if not report.results:
        return "No articles found to check."

    lines = [
        f"Freshness Report — {report.checked_at}",
        f"Wiki: {report.wiki_root}",
        f"Articles checked: {report.article_count}",
        "",
        f"{'Path':<50} {'Score':>6} {'Tier':<8} Issues",
        "-" * 100,
    ]

    for result in report.results:
        path_display = result.article_path
        if len(path_display) > 49:
            path_display = "..." + path_display[-46:]
        issue_count = len(result.issues)
        lines.append(
            f"{path_display:<50} {result.freshness_score:>6} "
            f"{result.tier:<8} {issue_count} issue(s)"
        )
        for issue in result.issues:
            lines.append(f"  → {issue}")

    lines.append("")
    lines.append("Summary:")
    for tier, count in sorted(report.summary.items()):
        lines.append(f"  {tier}: {count}")

    return "\n".join(lines)


def check_freshness(
    wiki_root: Path,
    specific_article: Optional[str] = None,
) -> FreshnessReport:
    """Check knowledge freshness of wiki articles.

    Args:
        wiki_root: Path to wiki/ directory.
        specific_article: Optional path to a specific article to check.

    Returns:
        FreshnessReport with per-article results and summary.
    """
    articles = _find_articles(wiki_root, specific_article)
    now = datetime.now(timezone.utc)

    if not articles:
        if HAS_PYDANTIC:
            return FreshnessReport(
                wiki_root=str(wiki_root),
                checked_at=now.isoformat(),
                article_count=0,
                results=[],
                summary={},
            )
        return FreshnessReport(
            wiki_root=str(wiki_root),
            checked_at=now.isoformat(),
            article_count=0,
            results=[],
            summary={},
        )

    # Extract metadata for all articles
    all_metadata: dict[Path, dict[str, Any]] = {}
    for filepath in articles:
        all_metadata[filepath] = _extract_metadata(filepath)

    # Compute freshness for each article
    results: list[FreshnessResult] = []
    for filepath in articles:
        result = _compute_freshness(
            all_metadata[filepath], filepath, wiki_root, all_metadata
        )
        results.append(result)

    # Build summary
    summary: dict[str, int] = {}
    for result in results:
        summary[result.tier] = summary.get(result.tier, 0) + 1

    if HAS_PYDANTIC:
        return FreshnessReport(
            wiki_root=str(wiki_root),
            checked_at=now.isoformat(),
            article_count=len(articles),
            results=sorted(results, key=lambda r: r.freshness_score),
            summary=summary,
        )
    return FreshnessReport(
        wiki_root=str(wiki_root),
        checked_at=now.isoformat(),
        article_count=len(articles),
        results=sorted(results, key=lambda r: r.freshness_score),
        summary=summary,
    )


def _resolve_wiki_root(arg_path: str) -> Path:
    """Resolve wiki root from argument, env var, or auto-detection."""
    if arg_path:
        candidate = Path(arg_path).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        print(f"Warning: {candidate} not found, trying auto-detection", file=sys.stderr)

    env_root = os.environ.get("KARPATHY_WIKI_ROOT", "")
    search_paths = [
        Path.cwd() / "wiki",
        Path(env_root).expanduser().resolve() if env_root else None,
    ]
    for sp in search_paths:
        if sp and sp.is_dir():
            return sp

    fallback = Path("/home/giuseppe/Progetti/Github/wiki")
    if fallback.is_dir():
        return fallback

    print(
        "Error: Could not find wiki/ directory. "
        "Set KARPATHY_WIKI_ROOT or pass --wiki-root.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    """Entry point for freshness_check script."""
    parser = argparse.ArgumentParser(
        description="Check knowledge freshness of wiki articles.",
    )
    parser.add_argument(
        "--wiki-root",
        type=str,
        default=os.environ.get("KARPATHY_WIKI_ROOT", ""),
        help="Path to wiki/ directory (default: $KARPATHY_WIKI_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--article",
        type=str,
        default=None,
        help="Check only a specific article (relative path from wiki root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    wiki_root = _resolve_wiki_root(args.wiki_root)

    report = check_freshness(wiki_root, specific_article=args.article)

    if args.json:
        if HAS_PYDANTIC:
            print(report.model_dump_json(indent=2))
        else:
            print(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        print(_format_results_text(report))


if __name__ == "__main__":
    main()
