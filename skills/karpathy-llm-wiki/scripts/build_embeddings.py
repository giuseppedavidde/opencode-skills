#!/usr/bin/env python3
"""Build embedding vectors for wiki articles to enable semantic search.

Walks through wiki/ directory, finds all .md files (excluding index.md and log.md),
extracts title and content, computes TF-IDF vectors, and stores embeddings
in wiki/.embeddings/.

Usage:
    python3 build_embeddings.py --wiki-root /path/to/wiki/root
    python3 build_embeddings.py --wiki-root /path/to/wiki/root --update
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class EmbeddingIndex(BaseModel):
        """Schema for the embedding index stored in index.json."""
        files: list[str] = Field(default_factory=list)
        vocabulary: dict[str, int] = Field(default_factory=dict)
        idf: list[float] = Field(default_factory=list)
        n_features: int = 0
        mtimes: dict[str, float] = Field(default_factory=dict)
        built_at: str = ""
        doc_count: int = 0
else:
    from dataclasses import dataclass, field, asdict

    @dataclass
    class EmbeddingIndex:
        """Schema for the embedding index stored in index.json."""
        files: list[str] = field(default_factory=list)
        vocabulary: dict[str, int] = field(default_factory=dict)
        idf: list[float] = field(default_factory=list)
        n_features: int = 0
        mtimes: dict[str, float] = field(default_factory=dict)
        built_at: str = ""
        doc_count: int = 0

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

# Regex pattern matching sklearn's default token_pattern: word characters, 2+ length
TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


def _tokenize(text: str) -> list[str]:
    """Tokenize text: lowercase, extract word tokens >= 2 chars, remove stop words."""
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def _extract_article_info(filepath: Path) -> tuple[str, str]:
    """Extract title and content from a wiki article file.

    Returns:
        (title, content): Title from first # heading, content is everything
        after metadata lines (lines starting with '>').
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Warning: Could not read {filepath}: {exc}", file=sys.stderr)
        return ("", "")

    title = ""
    content_lines: list[str] = []
    past_metadata = False

    for line in text.split("\n"):
        stripped = line.strip()
        if not title and stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            continue
        if not past_metadata:
            if stripped.startswith(">"):
                continue
            if stripped == "":
                continue
            past_metadata = True
        if past_metadata:
            content_lines.append(line)

    content = "\n".join(content_lines).strip()
    return (title, content)


class PurePythonTfidf:
    """Pure-Python TF-IDF vectorizer matching sklearn's default tokenization.

    Stores vocabulary and IDF for serialization, produces sparse (dict) vectors
    for efficient storage and cosine similarity computation.
    """

    def __init__(self, max_features: int = 5000, min_df: int = 1) -> None:
        self.max_features: int = max_features
        self.min_df: int = min_df
        self.vocabulary: dict[str, int] = {}
        self.idf_: list[float] = []
        self._fitted: bool = False

    def fit(self, documents: list[str]) -> None:
        """Build vocabulary and compute IDF from a corpus of documents."""
        n_docs = len(documents)
        doc_freq: Counter[str] = Counter()

        for doc in documents:
            tokens = set(_tokenize(doc))
            doc_freq.update(tokens)

        # Filter by min_df
        filtered = [(term, cnt) for term, cnt in doc_freq.items() if cnt >= self.min_df]
        # Sort by frequency desc, then alphabetically
        filtered.sort(key=lambda x: (-x[1], x[0]))

        # Limit to max_features
        if self.max_features and len(filtered) > self.max_features:
            filtered = filtered[: self.max_features]

        self.vocabulary = {term: idx for idx, (term, _) in enumerate(filtered)}

        # Compute IDF: log((1 + N) / (1 + df)) + 1  (smooth_idf=True, sklearn default)
        self.idf_ = [0.0] * len(self.vocabulary)
        for term, idx in self.vocabulary.items():
            df = doc_freq.get(term, 0)
            self.idf_[idx] = math.log((1 + n_docs) / (1 + df)) + 1

        self._fitted = True

    def transform(self, documents: list[str]) -> list[dict[int, float]]:
        """Transform documents to sparse TF-IDF vectors (dict of term_idx -> value)."""
        if not self._fitted:
            raise RuntimeError("Vectorizer not fitted. Call fit() first.")

        vectors: list[dict[int, float]] = []
        for doc in documents:
            tokens = _tokenize(doc)
            if not tokens:
                vectors.append({})
                continue
            tf_counter = Counter(tokens)
            total_terms = len(tokens)
            vec: dict[int, float] = {}
            for term, count in tf_counter.items():
                idx = self.vocabulary.get(term)
                if idx is not None:
                    tf = count / total_terms
                    vec[idx] = tf * self.idf_[idx]

            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec.values()))
            if norm > 0:
                vec = {k: v / norm for k, v in vec.items()}

            vectors.append(vec)

        return vectors

    def fit_transform(self, documents: list[str]) -> list[dict[int, float]]:
        """Fit on documents and return TF-IDF vectors."""
        self.fit(documents)
        return self.transform(documents)

    def to_dict(self) -> dict[str, Any]:
        """Serialize vectorizer state for storage."""
        return {
            "vocabulary": self.vocabulary,
            "idf": self.idf_,
            "max_features": self.max_features,
            "min_df": self.min_df,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PurePythonTfidf":
        """Reconstruct vectorizer from serialized state."""
        vec = cls(
            max_features=data.get("max_features", 5000),
            min_df=data.get("min_df", 1),
        )
        vec.vocabulary = data["vocabulary"]
        vec.idf_ = data["idf"]
        vec._fitted = True
        return vec


def _sparse_vec_to_dense(sparse_vec: dict[int, float], n_features: int) -> list[float]:
    """Convert a sparse dict vector to a dense list."""
    dense = [0.0] * n_features
    for idx, val in sparse_vec.items():
        dense[idx] = val
    return dense


def _find_articles(wiki_root: Path) -> list[Path]:
    """Walk wiki/ and find all .md files, excluding index.md and log.md."""
    articles: list[Path] = []
    if not wiki_root.is_dir():
        return articles
    for filepath in wiki_root.rglob("*.md"):
        if filepath.name in ("index.md", "log.md"):
            continue
        articles.append(filepath)
    return sorted(articles)


def _sklearn_fit_transform(
    documents: list[str],
) -> tuple[dict[str, int], list[float], "np.ndarray"]:
    """Use sklearn TfidfVectorizer for fitting and transforming."""
    vectorizer = TfidfVectorizer(
        max_features=5000,
        min_df=1,
        stop_words="english",
        token_pattern=r"(?u)\b\w\w+\b",
    )
    matrix = vectorizer.fit_transform(documents)
    vocab = {term: int(idx) for term, idx in vectorizer.vocabulary_.items()}
    idf = [float(v) for v in vectorizer.idf_]
    return vocab, idf, matrix.toarray() if HAS_NUMPY else matrix


def _serialize_embeddings(
    embeddings_dir: Path,
    index_data: EmbeddingIndex,
    sparse_vectors: list[dict[int, float]],
    dense_vectors: Optional["np.ndarray"],
) -> None:
    """Write embeddings and index to disk."""
    embeddings_dir.mkdir(parents=True, exist_ok=True)

    # Write index.json
    index_dict = index_data.model_dump() if HAS_PYDANTIC else index_data.model_dump()
    index_path = embeddings_dir / "index.json"
    index_path.write_text(json.dumps(index_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write embeddings
    if HAS_NUMPY and dense_vectors is not None:
        np.save(str(embeddings_dir / "embeddings.npy"), dense_vectors)
        # Also remove any old embeddings.json
        json_path = embeddings_dir / "embeddings.json"
        if json_path.exists():
            json_path.unlink()
    else:
        formatted = [{str(k): v for k, v in vec.items()} for vec in sparse_vectors]
        json_path = embeddings_dir / "embeddings.json"
        json_path.write_text(json.dumps(formatted, indent=2, ensure_ascii=False), encoding="utf-8")
        # Remove old .npy
        npy_path = embeddings_dir / "embeddings.npy"
        if npy_path.exists():
            npy_path.unlink()


def build_embeddings(wiki_root: Path, update_only: bool = False) -> dict[str, Any]:
    """Build or update embeddings for all wiki articles.

    Args:
        wiki_root: Path to wiki/ directory.
        update_only: If True, only re-embed articles with newer modification
            time than the last build.

    Returns:
        Summary dict with counts.
    """
    embeddings_dir = wiki_root / ".embeddings"
    articles = _find_articles(wiki_root)

    if not articles:
        print("No articles found in wiki directory.", file=sys.stderr)
        return {"total": 0, "new": 0, "skipped": 0}

    # Load previous index if updating
    prev_index: Optional[EmbeddingIndex] = None
    if update_only and (embeddings_dir / "index.json").exists():
        try:
            prev_data = json.loads((embeddings_dir / "index.json").read_text(encoding="utf-8"))
            if HAS_PYDANTIC:
                prev_index = EmbeddingIndex(**prev_data)
            else:
                prev_index = EmbeddingIndex(**prev_data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"Warning: Could not load previous index: {exc}", file=sys.stderr)
            prev_index = None

    # Determine which articles need embedding
    if update_only and prev_index is not None:
        prev_mtimes = prev_index.mtimes or {}
        to_embed: list[Path] = []
        skipped: list[Path] = []
        for article in articles:
            current_mtime = article.stat().st_mtime
            rel_path = str(article.relative_to(wiki_root))
            prev_mtime = prev_mtimes.get(rel_path, 0)
            if current_mtime > prev_mtime:
                to_embed.append(article)
            else:
                skipped.append(article)
        # Also include new articles not in prev_index
        prev_files = set(prev_index.files)
        for article in articles[:]:  # iterate a copy to allow mutation
            if str(article.relative_to(wiki_root)) not in prev_files and article not in to_embed:
                to_embed.append(article)
                if article in skipped:
                    skipped.remove(article)
    else:
        to_embed = list(articles)
        skipped = []

    if not to_embed:
        print("All articles are up to date.")
        return {"total": len(articles), "new": 0, "skipped": len(articles)}

    # Extract article info and content
    all_articles = articles  # all articles for full rebuild
    doc_paths: list[str] = []
    doc_contents: list[str] = []
    doc_mtimes: dict[str, float] = {}

    for article in all_articles:
        title, content = _extract_article_info(article)
        if not content.strip():
            continue
        rel_path = str(article.relative_to(wiki_root))
        doc_paths.append(rel_path)
        # Combine title and content for embedding
        doc_contents.append(f"{title} {content}")
        doc_mtimes[rel_path] = article.stat().st_mtime

    if not doc_contents:
        print("No content found in any articles.", file=sys.stderr)
        return {"total": 0, "new": 0, "skipped": 0}

    # Build TF-IDF vectors
    n_features: int
    vocabulary: dict[str, int]
    idf_values: list[float]

    if HAS_SKLEARN:
        print("Using sklearn TfidfVectorizer")
        vocab, idf_values, dense = _sklearn_fit_transform(doc_contents)
        vocabulary = vocab
        n_features = len(vocab)

        # Build sparse vectors for storage
        if HAS_NUMPY:
            sparse_vectors: list[dict[int, float]] = []
            for i in range(dense.shape[0]):
                vec: dict[int, float] = {}
                for j in range(dense.shape[1]):
                    val = float(dense[i, j])
                    if val != 0.0:
                        vec[int(j)] = val
                # L2 normalize
                norm = math.sqrt(sum(v * v for v in vec.values()))
                if norm > 0:
                    vec = {k: v / norm for k, v in vec.items()}
                sparse_vectors.append(vec)
            dense_array: Optional["np.ndarray"] = np.array(
                [_sparse_vec_to_dense(v, n_features) for v in sparse_vectors],
                dtype=np.float32,
            )
        else:
            sparse_vectors = []
            for i in range(dense.shape[0]):
                vec = {
                    int(j): float(dense[i, j])
                    for j in range(dense.shape[1]) if dense[i, j] != 0
                }
                norm = math.sqrt(sum(v * v for v in vec.values()))
                if norm > 0:
                    vec = {k: v / norm for k, v in vec.items()}
                sparse_vectors.append(vec)
            dense_array = None
    else:
        print("Using pure-Python TF-IDF vectorizer")
        vectorizer = PurePythonTfidf(max_features=5000, min_df=1)
        sparse_vectors = vectorizer.fit_transform(doc_contents)
        vocabulary = vectorizer.vocabulary
        idf_values = vectorizer.idf_
        n_features = len(vocabulary)
        if HAS_NUMPY:
            dense_array = np.array(
                [_sparse_vec_to_dense(v, n_features) for v in sparse_vectors],
                dtype=np.float32,
            )
        else:
            dense_array = None

    # Build index
    if HAS_PYDANTIC:
        index_data = EmbeddingIndex(
            files=doc_paths,
            vocabulary=vocabulary,
            idf=idf_values,
            n_features=n_features,
            mtimes=doc_mtimes,
            built_at=datetime.now(timezone.utc).isoformat(),
            doc_count=len(doc_paths),
        )
    else:
        index_data = EmbeddingIndex(
            files=doc_paths,
            vocabulary=vocabulary,
            idf=idf_values,
            n_features=n_features,
            mtimes=doc_mtimes,
            built_at=datetime.now(timezone.utc).isoformat(),
            doc_count=len(doc_paths),
        )

    # Serialize
    _serialize_embeddings(embeddings_dir, index_data, sparse_vectors, dense_array)

    new_count = len(to_embed)
    skipped_count = len(skipped)
    print(f"Embedded {len(doc_paths)} articles ({new_count} new, {skipped_count} skipped)")
    return {"total": len(doc_paths), "new": new_count, "skipped": skipped_count}


def main() -> None:
    """Entry point for build_embeddings script."""
    parser = argparse.ArgumentParser(
        description="Build TF-IDF embedding vectors for wiki articles.",
    )
    parser.add_argument(
        "--wiki-root",
        type=str,
        default=os.environ.get("KARPATHY_WIKI_ROOT", ""),
        help="Path to wiki/ directory (default: $KARPATHY_WIKI_ROOT or auto-detect)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Only re-embed files with newer modification time",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    wiki_root = _resolve_wiki_root(args.wiki_root)

    start_time = time.time()
    result = build_embeddings(wiki_root, update_only=args.update)
    elapsed = time.time() - start_time

    if args.json:
        result["elapsed_seconds"] = round(elapsed, 2)
        print(json.dumps(result, indent=2))
    else:
        summary = (
            f"Embedded {result['total']} articles "
            f"({result['new']} new, {result['skipped']} skipped) "
            f"in {elapsed:.1f}s"
        )
        print(summary)


def _resolve_wiki_root(arg_path: str) -> Path:
    """Resolve wiki root from argument, env var, or auto-detection."""
    if arg_path:
        candidate = Path(arg_path).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        print(f"Warning: {candidate} not found, trying auto-detection", file=sys.stderr)

    # Try common locations
    env_root = os.environ.get("KARPATHY_WIKI_ROOT", "")
    search_paths = [
        Path.cwd() / "wiki",
        Path(env_root).expanduser().resolve() if env_root else None,
    ]
    for sp in search_paths:
        if sp and sp.is_dir():
            return sp

    # Default fallback
    fallback = Path("/home/giuseppe/Progetti/Github/wiki")
    if fallback.is_dir():
        return fallback

    print(
        "Error: Could not find wiki/ directory. "
        "Set KARPATHY_WIKI_ROOT or pass --wiki-root.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
