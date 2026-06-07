#!/usr/bin/env python3
"""Semantic search across wiki articles using pre-built TF-IDF embeddings.

Loads embeddings from wiki/.embeddings/ (built by build_embeddings.py),
vectorizes the query, computes cosine similarity, and returns top N results.

Usage:
    python3 search_wiki.py --wiki-root /path/to/wiki "Wyckoff accumulation phases"
    python3 search_wiki.py --wiki-root /path/to/wiki "volume profile" --top 5 --json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class SearchResult(BaseModel):
        """A single search result."""
        rank: int
        title: str
        path: str
        relevance: float

    class SearchOutput(BaseModel):
        """Complete search output."""
        query: str
        results: list[SearchResult]
        elapsed_seconds: float = 0.0
else:
    from dataclasses import dataclass, field, asdict

    @dataclass
    class SearchResult:
        """A single search result."""
        rank: int
        title: str
        path: str
        relevance: float

    @dataclass
    class SearchOutput:
        """Complete search output."""
        query: str
        results: list[SearchResult] = field(default_factory=list)
        elapsed_seconds: float = 0.0

        def model_dump(self) -> dict:
            """Serialize the dataclass to a dict (Pydantic-compatible interface)."""
            return asdict(self)


STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "not", "no", "nor",
    "so", "if", "then", "than", "that", "this", "these", "those", "it",
    "its", "he", "she", "they", "we", "you", "i", "my", "your", "his",
    "her", "our", "their", "me", "him", "us", "them", "as", "into",
    "also", "very", "too", "just", "about", "over", "more", "some",
    "such", "only", "other", "new", "all", "any", "each", "every",
    "both", "few", "most", "own", "same",
}

TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


def _tokenize(text: str) -> list[str]:
    """Tokenize text: lowercase, extract word tokens >= 2 chars, remove stop words."""
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def _vectorize_query(
    query: str,
    vocabulary: dict[str, int],
    idf: list[float],
    n_features: int,
) -> list[float]:
    """Vectorize a query string using the same vocabulary/IDF as the corpus.

    Returns a dense L2-normalized vector.
    """
    tokens = _tokenize(query)
    if not tokens:
        return [0.0] * n_features

    total_terms = len(tokens)
    tf_counts: dict[str, int] = {}
    for token in tokens:
        tf_counts[token] = tf_counts.get(token, 0) + 1

    vec = [0.0] * n_features
    for term, count in tf_counts.items():
        idx = vocabulary.get(term)
        if idx is not None:
            tf = count / total_terms
            vec[idx] = tf * idf[idx]

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]

    return vec


def _load_embeddings(embeddings_dir: Path) -> tuple[dict[str, Any], Any, Optional["np.ndarray"]]:
    """Load embeddings index and vectors from disk.

    Returns:
        (index_dict, sparse_vectors, dense_array): index metadata, sparse vectors
        (list of dicts or None), and dense numpy array (or None).
    """
    index_path = embeddings_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"Embeddings not found at {embeddings_dir}. "
            f"Run build_embeddings.py first."
        )

    with open(index_path, encoding="utf-8") as fh:
        index_data = json.load(fh)

    sparse_vectors: list[dict[int, float]] = []
    dense_array: Optional["np.ndarray"] = None

    npy_path = embeddings_dir / "embeddings.npy"
    json_emb_path = embeddings_dir / "embeddings.json"

    if HAS_NUMPY and npy_path.exists():
        dense_array = np.load(str(npy_path))
    elif json_emb_path.exists():
        with open(json_emb_path, encoding="utf-8") as fh:
            raw_vectors = json.load(fh)
        for vec_dict in raw_vectors:
            sparse_vectors.append({int(k): float(v) for k, v in vec_dict.items()})
    else:
        raise FileNotFoundError(
            f"No embeddings file found (.npy or .json) in {embeddings_dir}"
        )

    return index_data, sparse_vectors, dense_array


def _cosine_similarity_numpy(
    query_vec: list[float], dense_matrix: "np.ndarray"
) -> list[float]:
    """Compute cosine similarity using numpy matmul."""
    qv = np.array(query_vec, dtype=np.float32)
    scores = np.dot(dense_matrix, qv)
    return [float(s) for s in scores]


def _cosine_similarity_sparse(
    query_vec: list[float],
    sparse_vectors: list[dict[int, float]],
) -> list[float]:
    """Compute cosine similarity between dense query and sparse doc vectors."""
    scores: list[float] = []
    for doc_vec in sparse_vectors:
        dot = sum(query_vec[idx] * val for idx, val in doc_vec.items() if idx < len(query_vec))
        scores.append(dot)
    return scores


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


def search_wiki(
    wiki_root: Path,
    query: str,
    top_n: int = 10,
) -> SearchOutput:
    """Search wiki articles semantically using TF-IDF cosine similarity.

    Args:
        wiki_root: Path to wiki/ directory.
        query: Search query string.
        top_n: Number of results to return.

    Returns:
        SearchOutput with ranked results.
    """
    embeddings_dir = wiki_root / ".embeddings"
    index_data, sparse_vectors, dense_array = _load_embeddings(embeddings_dir)

    files: list[str] = index_data["files"]
    vocabulary: dict[str, int] = {str(k): int(v) for k, v in index_data["vocabulary"].items()}
    idf: list[float] = [float(v) for v in index_data["idf"]]
    n_features: int = int(index_data["n_features"])

    # Vectorize query
    query_vec = _vectorize_query(query, vocabulary, idf, n_features)

    # Compute cosine similarity
    if dense_array is not None and HAS_NUMPY:
        scores = _cosine_similarity_numpy(query_vec, dense_array)
    else:
        scores = _cosine_similarity_sparse(query_vec, sparse_vectors)

    # Rank results
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    results: list[SearchResult] = []
    for rank, (doc_idx, score) in enumerate(ranked[:top_n], start=1):
        if score <= 0.0:
            continue
        rel_path = files[doc_idx] if doc_idx < len(files) else ""
        article_path = wiki_root / rel_path if rel_path else None
        title = ""
        if article_path and article_path.exists():
            title = _extract_title(article_path)
        if not title:
            title = Path(rel_path).stem.replace("-", " ").title() if rel_path else "Unknown"

        if HAS_PYDANTIC:
            results.append(SearchResult(
                rank=rank,
                title=title,
                path=rel_path,
                relevance=round(score, 4),
            ))
        else:
            results.append(SearchResult(
                rank=rank,
                title=title,
                path=rel_path,
                relevance=round(score, 4),
            ))

    if HAS_PYDANTIC:
        return SearchOutput(query=query, results=results)
    return SearchOutput(query=query, results=results)


def _format_results_text(output: SearchOutput) -> str:
    """Format search results as human-readable text."""
    if not output.results:
        return f"No results found for: \"{output.query}\""

    lines = [f'Results for: "{output.query}"', "-" * 50]
    for result in output.results:
        lines.append(
            f"{result.rank}. [{result.title}]({result.path}) "
            f"— relevance: {result.relevance:.4f}"
        )
    return "\n".join(lines)


def main() -> None:
    """Entry point for search_wiki script."""
    parser = argparse.ArgumentParser(
        description="Semantic search across wiki articles using TF-IDF embeddings.",
    )
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        default="",
        help="Search query string",
    )
    parser.add_argument(
        "--wiki-root",
        type=str,
        default=os.environ.get("KARPATHY_WIKI_ROOT", ""),
        help="Path to wiki/ directory (default: $KARPATHY_WIKI_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of results to return (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        print("\nError: query argument is required.", file=sys.stderr)
        sys.exit(1)

    wiki_root = _resolve_wiki_root(args.wiki_root)

    start_time = time.time()

    try:
        output = search_wiki(wiki_root, args.query, top_n=args.top)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output.elapsed_seconds = round(time.time() - start_time, 3)

    if args.json:
        if HAS_PYDANTIC:
            print(output.model_dump_json(indent=2))
        else:
            print(json.dumps(output.model_dump(), indent=2, default=str))
    else:
        print(_format_results_text(output))


if __name__ == "__main__":
    main()
