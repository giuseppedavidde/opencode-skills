#!/usr/bin/env python3
"""
aggregate.py — Merge risultati da N agenti paralleli.
Supporta mode: rank (sort + top_n), concat (merge arrays), json_merge (merge objects).
"""

import json
import argparse
import glob
from pathlib import Path


def load_results(input_pattern: str) -> list[dict]:
    """Load all chunk result files matching glob pattern."""
    files = sorted(glob.glob(input_pattern))
    if not files:
        print(f"⚠ No files matching: {input_pattern}")
        return []

    all_results = []
    errors = 0
    for f in files:
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_results.extend(data)
            elif isinstance(data, dict):
                all_results.append(data)
            else:
                print(f"  ⚠ Skipping {f}: unexpected type {type(data).__name__}")
                errors += 1
        except json.JSONDecodeError as e:
            print(f"  ⚠ Skipping {f}: invalid JSON ({e})")
            errors += 1
        except Exception as e:
            print(f"  ⚠ Skipping {f}: {e}")
            errors += 1

    if errors:
        print(f"  Loaded {len(all_results)} results from {len(files)} files ({errors} errors)")

    return all_results


def merge_rank(results: list[dict], key: str = "score", top_n: int = None) -> list[dict]:
    """Sort by key descending, return top N."""
    valid = [r for r in results if isinstance(r, dict) and key in r]
    if not valid:
        print(f"⚠ No results contain key '{key}'")
        return []

    sorted_results = sorted(valid, key=lambda x: x[key], reverse=True)

    if top_n and top_n < len(sorted_results):
        sorted_results = sorted_results[:top_n]
        print(f"  Ranked by '{key}', returned top {top_n}")

    return sorted_results


def merge_concat(results: list[dict]) -> list[dict]:
    """Simply return all results (deduplicated by symbol if present)."""
    seen = set()
    deduped = []
    for r in results:
        symbol = r.get("symbol") or r.get("id") or r.get("name")
        if symbol and symbol in seen:
            continue
        if symbol:
            seen.add(symbol)
        deduped.append(r)

    if len(deduped) < len(results):
        print(f"  Deduplicated: {len(results)} → {len(deduped)}")

    return deduped


def merge_json(files_pattern: str) -> dict:
    """Merge JSON objects (nodes+edges style). Loads all files fresh for full merge."""
    files = sorted(glob.glob(files_pattern))
    merged = {}
    keys_seen = set()

    for f in files:
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                print(f"  ⚠ Skipping {f}: not a JSON object")
                continue
            for k, v in data.items():
                if k not in merged:
                    keys_seen.add(k)
                    if isinstance(v, list):
                        merged[k] = list(v)
                    else:
                        merged[k] = v
                elif isinstance(v, list) and isinstance(merged[k], list):
                    merged[k].extend(v)
                elif isinstance(v, dict) and isinstance(merged[k], dict):
                    merged[k].update(v)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ⚠ Skipping {f}: {e}")

    return merged


def format_output(results, mode: str, format_type: str = "json"):
    """Format and print results."""
    if not results:
        print("(no results)")
        return

    if format_type == "json" or format_type == "json-compact":
        indent = None if format_type == "json-compact" else 2
        print(json.dumps(results, indent=indent, default=str))

    elif format_type == "table":
        if not isinstance(results, list) or not results:
            print(json.dumps(results, indent=2, default=str))
            return

        # Extract all keys from first result
        keys = list(results[0].keys())
        # Limit to readable columns
        display_keys = [k for k in keys if k not in (
            "wyckoff_detail", "volprof_detail", "pa_detail",
            "sentiment_detail", "fundamentals_detail"
        )][:8]

        # Header
        header = " | ".join(k.upper()[:10] for k in display_keys)
        print(header)
        print("-" * len(header))

        # Rows
        for r in results:
            row = " | ".join(str(r.get(k, ""))[:10] for k in display_keys)
            print(row)

    elif format_type == "summary":
        if isinstance(results, list):
            print(f"Total results: {len(results)}")
            if results and isinstance(results[0], dict):
                keys = list(results[0].keys())
                print(f"Keys: {', '.join(keys[:8])}")
                if "final_score" in results[0]:
                    scores = [r["final_score"] for r in results if isinstance(r, dict)]
                    if scores:
                        print(f"Score range: {min(scores):.1f} - {max(scores):.1f}")
                        print(f"Score avg: {sum(scores)/len(scores):.1f}")
        elif isinstance(results, dict):
            print(f"Merged object with keys: {', '.join(results.keys())}")
            for k, v in results.items():
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} items")
                else:
                    print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Aggregate results from parallel agents")
    parser.add_argument("--input", "-i", default="/tmp/orch_chunk_*.json",
                       help="Glob pattern for chunk result files")
    parser.add_argument("--mode", choices=["rank", "concat", "json_merge"], default="rank",
                       help="Merge mode")
    parser.add_argument("--key", default="final_score",
                       help="Sort key for rank mode")
    parser.add_argument("--top", type=int, default=None,
                       help="Top N for rank mode")
    parser.add_argument("--format", choices=["json", "json-compact", "table", "summary"],
                       default="summary",
                       help="Output format")
    parser.add_argument("--output", "-o", type=str, default=None,
                       help="Write merged result to file (JSON)")

    args = parser.parse_args()

    if args.mode == "json_merge":
        results = merge_json(args.input)
    else:
        results = load_results(args.input)
        if args.mode == "rank":
            results = merge_rank(results, key=args.key, top_n=args.top)
        elif args.mode == "concat":
            results = merge_concat(results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\n📄 Written to: {out_path}")

    print()
    format_output(results, args.mode, args.format)


if __name__ == "__main__":
    main()
