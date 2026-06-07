#!/usr/bin/env python3
"""
Temporal knowledge graph builder for graphify.

Enriches graph.json with temporal metadata (timestamps for nodes and edges)
derived from git history of the source files. Enables time-aware queries
like "what did we know about X on June 1 2025?"

Usage:
    python3 temporal_graph.py graph.json --source-dir /path/to/source
    python3 temporal_graph.py graph.json --source-dir /path/to/source --output temporal_graph.json
    python3 temporal_graph.py graph.json --source-dir /path/to/source --query "X" --time 2025-06-01
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def get_file_first_commit(source_dir: str, filepath: str) -> Optional[str]:
    """Get the first commit date for a file using git log."""
    try:
        result = subprocess.run(
            ["git", "-C", source_dir, "log", "--diff-filter=A", "--follow",
             "--format=%aI", "--", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Last line is the first commit
            lines = result.stdout.strip().split("\n")
            return lines[-1]
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_file_last_modified(source_dir: str, filepath: str) -> Optional[str]:
    """Get the last modification date for a file using git log."""
    try:
        result = subprocess.run(
            ["git", "-C", source_dir, "log", "-1", "--format=%aI", "--", filepath],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def build_temporal_cache(source_dir: str, files: set[str]) -> dict[str, dict]:
    """Build a cache of git timestamps for all source files."""
    cache: dict[str, dict] = {}
    source_path = Path(source_dir)

    for file_rel in files:
        full_path = source_path / file_rel
        if not full_path.exists():
            continue

        # Try to resolve the path relative to the git root
        try:
            result = subprocess.run(
                ["git", "-C", source_dir, "ls-files", "--", file_rel],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                file_rel = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        created = get_file_first_commit(source_dir, file_rel)
        modified = get_file_last_modified(source_dir, file_rel)

        if created or modified:
            cache[file_rel] = {
                "created": created,
                "last_modified": modified or created,
            }

    return cache


def enrich_graph(graph: dict, temporal_cache: dict[str, dict]) -> dict:
    """Add temporal metadata to all nodes and edges."""
    result = dict(graph)

    # Enrich nodes
    enriched_nodes = []
    for node in result.get("nodes", []):
        node = dict(node)
        source_file = node.get("source", node.get("file", ""))
        if source_file and source_file in temporal_cache:
            node["created_at"] = temporal_cache[source_file]["created"]
            node["last_modified_at"] = temporal_cache[source_file]["last_modified"]
        enriched_nodes.append(node)
    result["nodes"] = enriched_nodes

    # Enrich edges: use the minimum timestamp of the two connected nodes
    node_timestamps = {}
    for node in enriched_nodes:
        node_id = node.get("id", "")
        created = node.get("created_at")
        if node_id and created:
            node_timestamps[node_id] = created

    enriched_edges = []
    for edge in result.get("edges", []):
        edge = dict(edge)
        source_ts = node_timestamps.get(edge.get("source", ""))
        target_ts = node_timestamps.get(edge.get("target", ""))

        # Edge timestamp = max of source/target (edge exists only when both nodes exist)
        if source_ts and target_ts:
            edge["created_at"] = max(source_ts, target_ts)
        elif source_ts:
            edge["created_at"] = source_ts
        elif target_ts:
            edge["created_at"] = target_ts

        enriched_edges.append(edge)
    result["edges"] = enriched_edges

    return result


def query_at_time(graph: dict, concept: str, cutoff: str) -> list[dict]:
    """Query what was known about a concept at a specific point in time."""
    results = []

    # Find nodes matching the concept
    for node in graph.get("nodes", []):
        node_id = node.get("id", "")
        node_labels = node.get("labels", node.get("label", []))
        if isinstance(node_labels, str):
            node_labels = [node_labels]

        matches = concept.lower() in node_id.lower()
        if not matches:
            for label in node_labels:
                if concept.lower() in label.lower():
                    matches = True
                    break

        if not matches:
            continue

        created = node.get("created_at", "")
        if created and created > cutoff:
            continue  # Node didn't exist yet

        # Find edges connected to this node at or before cutoff
        relevant_edges = []
        for edge in graph.get("edges", []):
            if edge.get("source") == node_id or edge.get("target") == node_id:
                edge_created = edge.get("created_at", "")
                if not edge_created or edge_created <= cutoff:
                    relevant_edges.append({
                        "source": edge.get("source"),
                        "target": edge.get("target"),
                        "relation": edge.get("relation", edge.get("label", "")),
                        "created_at": edge.get("created_at"),
                    })

        results.append({
            "node": node_id,
            "labels": node_labels,
            "created_at": created,
            "related_edges": relevant_edges,
        })

    return results


def print_timeline(graph: dict, out_path: str | None = None) -> str:
    """Generate a simple text timeline of concept introductions."""
    nodes = graph.get("nodes", [])
    nodes_with_dates = [n for n in nodes if n.get("created_at")]

    if not nodes_with_dates:
        return "No temporal data available. Run git init on the source directory first."

    # Group by date
    by_date: dict[str, list[str]] = {}
    for node in nodes_with_dates:
        date = node["created_at"][:10]  # YYYY-MM-DD
        by_date.setdefault(date, []).append(node.get("id", "unknown"))

    lines = ["# Concept Timeline\n"]
    for date in sorted(by_date):
        concepts = by_date[date]
        lines.append(f"## {date} ({len(concepts)} concepts)")
        for concept in concepts[:20]:
            lines.append(f"- {concept}")
        if len(concepts) > 20:
            lines.append(f"- ... and {len(concepts) - 20} more")
        lines.append("")

    result = "\n".join(lines)
    if out_path:
        Path(out_path).write_text(result, encoding="utf-8")
    return result


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Temporal knowledge graph builder")
    parser.add_argument("graph_path", help="Path to graph.json")
    parser.add_argument("--source-dir", required=True,
                        help="Directory containing source files (git-managed)")
    parser.add_argument("--output", "-o", type=str, help="Output path for enriched graph")
    parser.add_argument("--query", type=str, help="Concept to query")
    parser.add_argument("--time", type=str, help="Cutoff date (YYYY-MM-DD) for --query")
    parser.add_argument("--timeline", type=str, help="Generate timeline report to file")
    args = parser.parse_args()

    graph_path = Path(args.graph_path)
    if not graph_path.exists():
        print(f"Error: Graph file not found: {args.graph_path}", file=sys.stderr)
        sys.exit(1)

    with open(graph_path, encoding="utf-8") as f:
        graph = json.load(f)

    # Collect all source files from nodes
    source_files = set()
    for node in graph.get("nodes", []):
        src = node.get("source", node.get("file", ""))
        if src:
            # Make relative to source_dir
            try:
                src = str(Path(src).relative_to(args.source_dir))
            except ValueError:
                pass
            source_files.add(src)

    # Build temporal cache
    temporal_cache = build_temporal_cache(args.source_dir, source_files)
    print(f"Found git timestamps for {len(temporal_cache)}/{len(source_files)} source files")

    # Query mode
    if args.query:
        if not args.time:
            print("Error: --time required with --query", file=sys.stderr)
            sys.exit(1)
        enriched = enrich_graph(graph, temporal_cache)
        results = query_at_time(enriched, args.query, args.time)
        print(f"\nKnowledge about '{args.query}' as of {args.time}:")
        print(f"Found {len(results)} matching concepts\n")
        for r in results:
            print(f"  Node: {r['node']} (created: {r.get('created_at', '?')})")
            print(f"  Labels: {r['labels']}")
            print(f"  Related edges at that time: {len(r['related_edges'])}")
            for e in r["related_edges"][:5]:
                print(f"    → {e['relation']}: {e['source']} ↔ {e['target']}")
            print()
        return

    # Enrichment mode
    enriched = enrich_graph(graph, temporal_cache)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(enriched, f, indent=2, ensure_ascii=False)
        print(f"Temporal graph written to {args.output}")

    if args.timeline:
        print_timeline(enriched, args.timeline)
        print(f"Timeline report written to {args.timeline}")
    elif not args.output:
        print(print_timeline(enriched))


if __name__ == "__main__":
    main()
