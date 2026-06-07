#!/usr/bin/env python3
"""Build a citation graph from wiki internal links.

Scans all wiki article files for markdown links [text](other_article.md) that
point to other wiki files. Builds a directed graph, computes in-degree,
out-degree, and PageRank metrics. Identifies orphan and bridge articles.

Usage:
    python3 citation_graph.py --wiki-root /path/to/wiki
    python3 citation_graph.py --wiki-root /path/to/wiki --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from pydantic import BaseModel, Field  # pylint: disable=unused-import
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class ArticleStats(BaseModel):
        """Citation statistics for a single article."""
        path: str
        title: str
        in_degree: int = 0
        out_degree: int = 0
        page_rank: float = 0.0

    class CitationReport(BaseModel):
        """Complete citation graph report."""
        wiki_root: str
        article_count: int
        edge_count: int
        most_influential: list[ArticleStats] = Field(default_factory=list)
        most_referenced: list[ArticleStats] = Field(default_factory=list)
        most_connected: list[ArticleStats] = Field(default_factory=list)
        orphan_articles: list[ArticleStats] = Field(default_factory=list)
        bridge_articles: list[ArticleStats] = Field(default_factory=list)
        all_articles: list[ArticleStats] = Field(default_factory=list)
else:
    from dataclasses import dataclass, field, asdict

    @dataclass
    class ArticleStats:
        """Citation statistics for a single article."""
        path: str
        title: str
        in_degree: int = 0
        out_degree: int = 0
        page_rank: float = 0.0

    @dataclass
    class CitationReport:
        """Complete citation graph report."""
        wiki_root: str
        article_count: int
        edge_count: int
        most_influential: list[ArticleStats] = field(default_factory=list)
        most_referenced: list[ArticleStats] = field(default_factory=list)
        most_connected: list[ArticleStats] = field(default_factory=list)
        orphan_articles: list[ArticleStats] = field(default_factory=list)
        bridge_articles: list[ArticleStats] = field(default_factory=list)
        all_articles: list[ArticleStats] = field(default_factory=list)

        def model_dump(self) -> dict:
            """Serialize the dataclass to a dict (Pydantic-compatible interface)."""
            return asdict(self)


# Regex for markdown links: [text](path.md)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")


def _extract_title(filepath: Path) -> str:
    """Extract the title (first # heading) from a wiki article."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return filepath.stem.replace("-", " ").title()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()

    return filepath.stem.replace("-", " ").title()


def _extract_internal_links(filepath: Path, wiki_root: Path) -> list[str]:
    """Extract wiki-internal markdown links from an article.

    Returns a list of resolved relative paths (from wiki root) for each link
    that points to another .md file within the wiki.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    links: list[str] = []
    article_dir = filepath.parent

    for match in MD_LINK_RE.finditer(text):
        link_target = match.group(2)

        # Resolve relative link
        resolved = (article_dir / link_target).resolve()

        # Check if target is within wiki_root
        try:
            resolved.relative_to(wiki_root.resolve())
        except ValueError:
            continue

        # Exclude index.md and log.md
        if resolved.name in ("index.md", "log.md"):
            continue

        # Check file exists and is .md
        if resolved.is_file() and resolved.suffix == ".md":
            rel_path = str(resolved.relative_to(wiki_root))
            links.append(rel_path)

    return links


def _find_articles(wiki_root: Path) -> list[Path]:
    """Find all wiki article .md files, excluding index.md and log.md."""
    articles: list[Path] = []
    if not wiki_root.is_dir():
        return articles
    for filepath in wiki_root.rglob("*.md"):
        if filepath.name in ("index.md", "log.md"):
            continue
        articles.append(filepath)
    return sorted(articles)


def _compute_pagerank(
    nodes: list[str],
    out_edges: dict[str, list[str]],
    in_edges: dict[str, list[str]],
    damping_factor: float = 0.85,
    iterations: int = 50,
) -> dict[str, float]:
    """Compute PageRank for a directed graph using the iterative algorithm.

    Args:
        nodes: List of node identifiers (relative paths).
        out_edges: Mapping from node to list of out-neighbors.
        in_edges: Mapping from node to list of in-neighbors.
        damping_factor: Teleport probability (default 0.85).
        iterations: Number of iterations.

    Returns:
        Mapping from node to PageRank score.
    """
    n = len(nodes)
    if n == 0:
        return {}

    pr = {node: 1.0 / n for node in nodes}

    for _ in range(iterations):
        new_pr: dict[str, float] = {}
        dangling_sum = 0.0

        # Handle dangling nodes (no out-edges)
        for node in nodes:
            if not out_edges.get(node):
                dangling_sum += pr[node]

        dangling_contrib = damping_factor * dangling_sum / n

        for node in nodes:
            rank = (1.0 - damping_factor) / n
            rank += dangling_contrib

            for in_node in in_edges.get(node, []):
                out_count = len(out_edges.get(in_node, []))
                if out_count > 0:
                    rank += damping_factor * pr[in_node] / out_count

            new_pr[node] = rank

        pr = new_pr

    return pr


def _compute_bridge_score(
    node: str,
    in_degree: int,
    out_degree: int,
    page_rank: float,
    max_page_rank: float,
) -> float:
    """Compute a simple bridge score for a node.

    Bridge articles are those with high connectivity (in+out degree) relative
    to their PageRank. They connect otherwise disconnected parts of the graph.

    Score = (in_degree + out_degree) * (1.0 - page_rank / max_page_rank)
    """
    _ = node  # part of signature for consistent callback interface
    if max_page_rank <= 0:
        return 0.0
    degree = in_degree + out_degree
    if degree == 0:
        return 0.0
    pr_ratio = page_rank / max_page_rank if max_page_rank > 0 else 1.0
    return degree * (1.0 - pr_ratio)


def build_citation_graph(wiki_root: Path) -> CitationReport:
    """Build citation graph from wiki internal links.

    Args:
        wiki_root: Path to wiki/ directory.

    Returns:
        CitationReport with graph metrics and statistics.
    """
    articles = _find_articles(wiki_root)

    if not articles:
        if HAS_PYDANTIC:
            return CitationReport(
                wiki_root=str(wiki_root),
                article_count=0,
                edge_count=0,
            )
        return CitationReport(
            wiki_root=str(wiki_root),
            article_count=0,
            edge_count=0,
        )

    # Build adjacency: relative path -> list of relative paths
    out_edges: dict[str, list[str]] = {}
    in_edges: dict[str, list[str]] = defaultdict(list)
    titles: dict[str, str] = {}

    for filepath in articles:
        rel_path = str(filepath.relative_to(wiki_root))
        titles[rel_path] = _extract_title(filepath)
        links = _extract_internal_links(filepath, wiki_root)
        out_edges[rel_path] = links
        for target in links:
            in_edges[target].append(rel_path)

    # Ensure all nodes have entries
    all_nodes = set()
    for article in articles:
        all_nodes.add(str(article.relative_to(wiki_root)))
    for links in out_edges.values():
        all_nodes.update(links)
    # Filter to only nodes that actually exist as files
    existing_nodes = [n for n in all_nodes if (wiki_root / n).is_file()]
    existing_set = set(existing_nodes)

    # Clean edges to only include existing nodes
    clean_out_edges: dict[str, list[str]] = {}
    clean_in_edges: dict[str, list[str]] = defaultdict(list)
    for src, targets in out_edges.items():
        clean_targets = [t for t in targets if t in existing_set]
        clean_out_edges[src] = clean_targets
        for t in clean_targets:
            clean_in_edges[t].append(src)
    for node in existing_nodes:
        if node not in clean_out_edges:
            clean_out_edges[node] = []

    clean_edge_count = sum(len(t) for t in clean_out_edges.values())

    # Compute PageRank
    page_ranks = _compute_pagerank(existing_nodes, clean_out_edges, clean_in_edges)

    # Build per-article stats
    stats_list: list[ArticleStats] = []
    for node in existing_nodes:
        in_deg = len(clean_in_edges.get(node, []))
        out_deg = len(clean_out_edges.get(node, []))
        pr = page_ranks.get(node, 0.0)
        title = titles.get(node, Path(node).stem.replace("-", " ").title())

        if HAS_PYDANTIC:
            stats_list.append(ArticleStats(
                path=node,
                title=title,
                in_degree=in_deg,
                out_degree=out_deg,
                page_rank=round(pr, 6),
            ))
        else:
            stats_list.append(ArticleStats(
                path=node,
                title=title,
                in_degree=in_deg,
                out_degree=out_deg,
                page_rank=round(pr, 6),
            ))

    # Sort for various rankings
    by_pagerank = sorted(stats_list, key=lambda s: s.page_rank, reverse=True)
    by_in_degree = sorted(stats_list, key=lambda s: s.in_degree, reverse=True)
    by_out_degree = sorted(stats_list, key=lambda s: s.out_degree, reverse=True)

    # Orphan articles: zero in-degree AND zero out-degree
    orphans = [s for s in stats_list if s.in_degree == 0 and s.out_degree == 0]

    # Bridge articles: high bridge score
    max_pr = max((s.page_rank for s in stats_list), default=1.0)
    bridge_candidates = []
    for s in stats_list:
        if s.in_degree == 0 and s.out_degree == 0:
            continue
        bridge_score = _compute_bridge_score(
            s.path, s.in_degree, s.out_degree, s.page_rank, max_pr
        )
        bridge_candidates.append((bridge_score, s))
    bridge_candidates.sort(key=lambda x: x[0], reverse=True)
    bridges = [s for _, s in bridge_candidates[:10]]

    top_n = min(10, len(stats_list))

    if HAS_PYDANTIC:
        return CitationReport(
            wiki_root=str(wiki_root),
            article_count=len(existing_nodes),
            edge_count=clean_edge_count,
            most_influential=by_pagerank[:top_n],
            most_referenced=by_in_degree[:top_n],
            most_connected=by_out_degree[:top_n],
            orphan_articles=orphans,
            bridge_articles=bridges,
            all_articles=sorted(stats_list, key=lambda s: s.path),
        )
    return CitationReport(
        wiki_root=str(wiki_root),
        article_count=len(existing_nodes),
        edge_count=clean_edge_count,
        most_influential=by_pagerank[:top_n],
        most_referenced=by_in_degree[:top_n],
        most_connected=by_out_degree[:top_n],
        orphan_articles=orphans,
        bridge_articles=bridges,
        all_articles=sorted(stats_list, key=lambda s: s.path),
    )


def _format_results_text(report: CitationReport) -> str:
    """Format citation report as human-readable text."""
    if report.article_count == 0:
        return "No articles found in wiki."

    lines = [
        f"Citation Graph Report — {report.wiki_root}",
        f"Articles: {report.article_count} | Edges: {report.edge_count}",
        "",
    ]

    # Most Influential (PageRank)
    lines.append("Most Influential Articles (PageRank):")
    header = f"  {'Rank':<6} {'Article':<45} {'PR':<12} {'In':<6} {'Out':<6}"
    lines.append(header)
    sep = f"  {'-'*4:<6} {'-'*43:<45} {'-'*10:<12} {'-'*4:<6} {'-'*4:<6}"
    lines.append(sep)
    for i, stat in enumerate(report.most_influential, 1):
        title_short = stat.title[:43] if len(stat.title) > 43 else stat.title
        lines.append(
            f"  {i:<6} {title_short:<45} {stat.page_rank:<12.6f} "
            f"{stat.in_degree:<6} {stat.out_degree:<6}"
        )
    lines.append("")

    # Most Referenced
    lines.append("Most Referenced Articles (In-Degree):")
    header2 = f"  {'Rank':<6} {'Article':<45} {'In':<6} {'Out':<6} {'PR':<12}"
    lines.append(header2)
    sep2 = f"  {'-'*4:<6} {'-'*43:<45} {'-'*4:<6} {'-'*4:<6} {'-'*10:<12}"
    lines.append(sep2)
    for i, stat in enumerate(report.most_referenced, 1):
        title_short = stat.title[:43] if len(stat.title) > 43 else stat.title
        lines.append(
            f"  {i:<6} {title_short:<45} {stat.in_degree:<6} "
            f"{stat.out_degree:<6} {stat.page_rank:<12.6f}"
        )
    lines.append("")

    # Bridge Articles
    if report.bridge_articles:
        lines.append("Bridge Articles (high connectivity, moderate PageRank):")
        lines.append(header)
        lines.append(sep)
        for i, stat in enumerate(report.bridge_articles, 1):
            title_short = stat.title[:43] if len(stat.title) > 43 else stat.title
            lines.append(
                f"  {i:<6} {title_short:<45} {stat.in_degree:<6} "
                f"{stat.out_degree:<6} {stat.page_rank:<12.6f}"
            )
        lines.append("")

    # Orphan Articles
    if report.orphan_articles:
        lines.append("Orphan Articles (no inbound or outbound links):")
        for stat in report.orphan_articles:
            lines.append(f"  - {stat.path}")
        lines.append("")

    return "\n".join(lines)


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
    """Entry point for citation_graph script."""
    parser = argparse.ArgumentParser(
        description="Build a citation graph from wiki internal links.",
    )
    parser.add_argument(
        "--wiki-root",
        type=str,
        default=os.environ.get("KARPATHY_WIKI_ROOT", ""),
        help="Path to wiki/ directory (default: $KARPATHY_WIKI_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    wiki_root = _resolve_wiki_root(args.wiki_root)

    report = build_citation_graph(wiki_root)

    if args.json:
        if HAS_PYDANTIC:
            print(report.model_dump_json(indent=2))
        else:
            print(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        print(_format_results_text(report))


if __name__ == "__main__":
    main()
