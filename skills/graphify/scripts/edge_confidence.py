#!/usr/bin/env python3
"""
Edge confidence scorer for graphify knowledge graphs.

Assigns a numeric confidence score (0.0-1.0) to every edge in a graph,
based on evidence source type, quantity, and co-occurrence frequency.

Usage:
    python3 edge_confidence.py graph.json
    python3 edge_confidence.py graph.json --output graph_scored.json
    python3 edge_confidence.py graph.json --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Source type base confidence
SOURCE_BASE = {
    "EXTRACTED_AST": 1.0,
    "EXTRACTED": 0.9,
    "INFERRED": 0.6,
    "AMBIGUOUS": 0.3,
}
DEFAULT_BASE = 0.5


def calculate_confidence(edge: dict, evidence_count: dict | None = None) -> float:
    """Calculate confidence score for a single edge.

    Factors:
    - Source type (EXTRACTED=0.9, INFERRED=0.6, AMBIGUOUS=0.3)
    - Evidence count (each source file supporting the edge adds up to 0.2)
    - Co-occurrence frequency (nodes appearing in same context)
    """
    source_type = edge.get("source_type", edge.get("type", ""))
    base = SOURCE_BASE.get(source_type, DEFAULT_BASE)

    # Evidence boost
    evidence = edge.get("evidence", [])
    if isinstance(evidence, list):
        evidence_boost = min(len(evidence) * 0.05, 0.20)
    else:
        evidence_boost = 0.0

    # Co-occurrence bonus
    co_occur = edge.get("co_occurrence_count", edge.get("weight", 0))
    if isinstance(co_occur, (int, float)) and co_occur > 3:
        co_occur_bonus = min((co_occur - 3) * 0.02, 0.10)
    else:
        co_occur_bonus = 0.0

    confidence = min(base + evidence_boost + co_occur_bonus, 1.0)
    return round(confidence, 4)


def compute_co_occurrence(graph: dict) -> dict[tuple, int]:
    """Count how many times node pairs appear in the same source files."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Build node → source files mapping
    node_sources: dict[str, set[str]] = {}
    for node in nodes:
        node_id = node.get("id", "")
        source = node.get("source", node.get("file", ""))
        if node_id and source:
            node_sources.setdefault(node_id, set()).add(source)

    # Count co-occurrences
    co_occur: dict[tuple[str, str], int] = {}
    node_ids = list(node_sources)
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            a, b = node_ids[i], node_ids[j]
            shared = node_sources[a] & node_sources[b]
            if shared:
                co_occur[(a, b)] = len(shared)
                co_occur[(b, a)] = len(shared)

    return co_occur


def score_graph(graph: dict) -> dict:
    """Add confidence scores to all edges in the graph."""
    co_occur = compute_co_occurrence(graph)

    scored_edges = []
    for edge in graph.get("edges", []):
        source = edge.get("source", "")
        target = edge.get("target", "")

        # Add co-occurrence count to edge if available
        co_count = co_occur.get((source, target), co_occur.get((target, source), 0))
        if co_count:
            edge = dict(edge)
            edge["co_occurrence_count"] = co_count

        confidence = calculate_confidence(edge)
        scored_edge = dict(edge, confidence=confidence)
        scored_edges.append(scored_edge)

    result = dict(graph)
    result["edges"] = scored_edges

    # Summary stats
    confidences = [e.get("confidence", 0) for e in scored_edges]
    if confidences:
        result["confidence_stats"] = {
            "mean": round(sum(confidences) / len(confidences), 4),
            "min": round(min(confidences), 4),
            "max": round(max(confidences), 4),
            "high_confidence_edges": len([c for c in confidences if c >= 0.8]),
            "medium_confidence_edges": len([c for c in confidences if 0.5 <= c < 0.8]),
            "low_confidence_edges": len([c for c in confidences if c < 0.5]),
        }

    return result


def print_stats(graph: dict) -> None:
    """Print confidence statistics for a graph."""
    stats = graph.get("confidence_stats", {})
    if not stats:
        print("No confidence statistics available.")
        return

    print("Edge Confidence Statistics")
    print(f"  Total edges: {len(graph.get('edges', []))}")
    print(f"  Mean confidence: {stats.get('mean', 0):.3f}")
    print(f"  Range: {stats.get('min', 0):.3f} – {stats.get('max', 0):.3f}")
    print(f"  High (≥0.8): {stats.get('high_confidence_edges', 0)}")
    print(f"  Medium (0.5–0.8): {stats.get('medium_confidence_edges', 0)}")
    print(f"  Low (<0.5): {stats.get('low_confidence_edges', 0)}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Edge confidence scorer for graphify")
    parser.add_argument("graph_path", help="Path to graph.json")
    parser.add_argument("--output", "-o", type=str, help="Output path for scored graph")
    parser.add_argument("--json", action="store_true", help="Output scored graph as JSON")
    args = parser.parse_args()

    graph_path = Path(args.graph_path)
    if not graph_path.exists():
        print(f"Error: Graph file not found: {args.graph_path}", file=sys.stderr)
        sys.exit(1)

    with open(graph_path, encoding="utf-8") as f:
        graph = json.load(f)

    scored = score_graph(graph)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(scored, f, indent=2, ensure_ascii=False)
        print(f"Scored graph written to {args.output}")
    elif args.json:
        print(json.dumps(scored, indent=2, ensure_ascii=False))
    else:
        print_stats(scored)


if __name__ == "__main__":
    main()
