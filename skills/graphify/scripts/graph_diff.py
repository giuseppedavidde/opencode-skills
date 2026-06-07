#!/usr/bin/env python3
"""
Graph state differ for graphify.

Compares two graph.json snapshots and produces a structured diff report
showing new/removed/modified nodes and edges, plus community shifts.

Usage:
    python3 graph_diff.py old_graph.json new_graph.json
    python3 graph_diff.py old_graph.json new_graph.json --json
    python3 graph_diff.py old_graph.json new_graph.json --report diff_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_graph(path: str) -> dict:
    """Load a graphify graph.json file."""
    graph_path = Path(path)
    if not graph_path.exists():
        print(f"Error: Graph file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(graph_path, encoding="utf-8") as f:
        return json.load(f)


def diff_graphs(old_graph: dict, new_graph: dict) -> dict:
    """Compute the difference between two graph snapshots."""
    old_nodes = {n["id"]: n for n in old_graph.get("nodes", [])}
    new_nodes = {n["id"]: n for n in new_graph.get("nodes", [])}
    old_node_ids = set(old_nodes)
    new_node_ids = set(new_nodes)

    old_edges = old_graph.get("edges", [])
    new_edges = new_graph.get("edges", [])

    # Edge identity by source+target+relation
    def _edge_key(e: dict) -> tuple:
        return (e.get("source", ""), e.get("target", ""), e.get("relation", ""))

    old_edge_map = {_edge_key(e): e for e in old_edges}
    new_edge_map = {_edge_key(e): e for e in new_edges}
    old_edge_keys = set(old_edge_map)
    new_edge_keys = set(new_edge_map)

    # Node changes
    added_nodes = sorted(new_node_ids - old_node_ids)
    removed_nodes = sorted(old_node_ids - new_node_ids)

    modified_nodes = []
    for node_id in old_node_ids & new_node_ids:
        old_n = old_nodes[node_id]
        new_n = new_nodes[node_id]
        if old_n != new_n:
            changes = {}
            for key in set(old_n) | set(new_n):
                if old_n.get(key) != new_n.get(key):
                    changes[key] = {"old": old_n.get(key), "new": new_n.get(key)}
            if changes:
                modified_nodes.append({"id": node_id, "changes": changes})

    # Edge changes
    added_edges = sorted(new_edge_keys - old_edge_keys)
    removed_edges = sorted(old_edge_keys - new_edge_keys)

    modified_edges = []
    for key in old_edge_keys & new_edge_keys:
        old_e = old_edge_map[key]
        new_e = new_edge_map[key]
        if old_e != new_e:
            changes = {}
            for k in set(old_e) | set(new_e):
                if old_e.get(k) != new_e.get(k):
                    changes[k] = {"old": old_e.get(k), "new": new_e.get(k)}
            if changes:
                modified_edges.append({"key": key, "changes": changes})

    # Community changes
    old_communities = old_graph.get("communities", {})
    new_communities = new_graph.get("communities", {})

    community_changes = []
    all_community_ids = set(old_communities) | set(new_communities)
    for comm_id in sorted(all_community_ids):
        old_members = set(old_communities.get(comm_id, {}).get("nodes", old_communities.get(comm_id, [])))
        new_members = set(new_communities.get(comm_id, {}).get("nodes", new_communities.get(comm_id, [])))
        if old_members != new_members:
            community_changes.append({
                "community_id": comm_id,
                "added_nodes": sorted(new_members - old_members),
                "removed_nodes": sorted(old_members - new_members),
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "old_graph_nodes": len(old_nodes),
        "new_graph_nodes": len(new_nodes),
        "old_graph_edges": len(old_edges),
        "new_graph_edges": len(new_edges),
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "modified_nodes": modified_nodes,
        "added_edges": [list(k) for k in added_edges],
        "removed_edges": [list(k) for k in removed_edges],
        "modified_edges": modified_edges,
        "community_changes": community_changes,
    }


def format_diff_report(diff: dict, old_path: str, new_path: str) -> str:
    """Format the diff as a markdown report."""
    lines = [
        "# Graph Diff Report",
        f"Generated: {diff['generated_at']}",
        f"Old: `{old_path}` ({diff['old_graph_nodes']} nodes, {diff['old_graph_edges']} edges)",
        f"New: `{new_path}` ({diff['new_graph_nodes']} nodes, {diff['new_graph_edges']} edges)",
        "",
    ]

    if diff["added_nodes"]:
        lines.append(f"## New Nodes (+{len(diff['added_nodes'])})")
        for node_id in diff["added_nodes"][:20]:
            lines.append(f"- {node_id}")
        if len(diff["added_nodes"]) > 20:
            lines.append(f"- ... and {len(diff['added_nodes']) - 20} more")
        lines.append("")

    if diff["removed_nodes"]:
        lines.append(f"## Removed Nodes (-{len(diff['removed_nodes'])})")
        for node_id in diff["removed_nodes"][:20]:
            lines.append(f"- {node_id}")
        if len(diff["removed_nodes"]) > 20:
            lines.append(f"- ... and {len(diff['removed_nodes']) - 20} more")
        lines.append("")

    if diff["modified_nodes"]:
        lines.append(f"## Modified Nodes ({len(diff['modified_nodes'])})")
        for mod in diff["modified_nodes"][:15]:
            lines.append(f"- **{mod['id']}**: {list(mod['changes'])}")
        lines.append("")

    if diff["added_edges"]:
        lines.append(f"## New Edges (+{len(diff['added_edges'])})")
        for edge in diff["added_edges"][:20]:
            lines.append(f"- {edge[0]} → {edge[1]} ({edge[2]})")
        if len(diff["added_edges"]) > 20:
            lines.append(f"- ... and {len(diff['added_edges']) - 20} more")
        lines.append("")

    if diff["removed_edges"]:
        lines.append(f"## Removed Edges (-{len(diff['removed_edges'])})")
        for edge in diff["removed_edges"][:20]:
            lines.append(f"- {edge[0]} → {edge[1]} ({edge[2]})")
        lines.append("")

    if diff["community_changes"]:
        lines.append(f"## Community Changes ({len(diff['community_changes'])})")
        for ch in diff["community_changes"][:10]:
            added = len(ch["added_nodes"])
            removed = len(ch["removed_nodes"])
            lines.append(f"- Community `{ch['community_id']}`: +{added} / -{removed} nodes")
        lines.append("")

    if not any([diff["added_nodes"], diff["removed_nodes"], diff["modified_nodes"],
                diff["added_edges"], diff["removed_edges"], diff["community_changes"]]):
        lines.append("✓ No changes detected between graph snapshots.")

    return "\n".join(lines)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Graph state differ")
    parser.add_argument("old_graph", help="Path to old graph.json")
    parser.add_argument("new_graph", help="Path to new graph.json")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--report", type=str, help="Write markdown report to file")
    args = parser.parse_args()

    old_graph = load_graph(args.old_graph)
    new_graph = load_graph(args.new_graph)

    diff = diff_graphs(old_graph, new_graph)

    if args.json:
        print(json.dumps(diff, indent=2, ensure_ascii=False))
    elif args.report:
        report = format_diff_report(diff, args.old_graph, args.new_graph)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(format_diff_report(diff, args.old_graph, args.new_graph))


if __name__ == "__main__":
    main()
