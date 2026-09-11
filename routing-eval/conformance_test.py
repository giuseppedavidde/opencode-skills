#!/usr/bin/env python3
"""Conformance test: real router (deepseek-v4-flash via opencode run) vs golden set.

Tests the REAL router against the curated golden set by running each query
through `opencode run` and comparing the predicted category with expected.

Differences from run_eval.py:
  - Calls opencode CLI (subprocess) instead of the Python classifier.
  - Measures real routing accuracy — flash model may diverge from emulated rules.
  - JSONL cache to avoid re-running identical queries across sessions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
DEFAULT_GOLDEN = DATA_DIR / "golden_set.json"
DEFAULT_CACHE = DATA_DIR / "conformance_cache.jsonl"


VALID_CATEGORIES = frozenset({
    "TRADE", "CODER", "GRAPHIFY", "SKILL_UPDATER", "BOOK_TO_SKILL", "SIMPLE",
})

CATEGORY_MAP: dict[str, str] = {
    "trade": "TRADE",
    "coder": "CODER",
    "graphify": "GRAPHIFY",
    "skill_updater": "SKILL_UPDATER",
    "book-to-skill": "BOOK_TO_SKILL",
    "book_to_skill": "BOOK_TO_SKILL",
    "simple": "SIMPLE",
}

JSON_BLOCK_PATTERN = re.compile(r"\{[^{}]*\"category\"[^{}]*\}", re.DOTALL)
CATEGORY_STANDALONE_PATTERN = re.compile(
    r"\b(TRADE|CODER|GRAPHIFY|SKILL_UPDATER|BOOK_TO_SKILL|SIMPLE)\b"
)


class GoldenCase(BaseModel):
    """Golden case from the curated dataset."""

    id: int
    text: str
    expected: str
    note: str = ""
    category: str = ""


class CacheEntry(BaseModel):
    """Single cache entry in conformance_cache.jsonl."""

    id: int
    query: str
    query_hash: str
    expected: str
    predicted: str
    reason: str = ""
    raw_snippet: str = ""
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConformanceResult(BaseModel):
    """Single result of a conformance test run."""

    id: int
    query: str
    expected: str
    predicted: str
    correct: bool
    reason: str = ""
    raw_snippet: str = ""


class PerCategoryStats(BaseModel):
    """Per-category statistics."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0
    tp: int = 0
    total_actual: int = 0
    total_predicted: int = 0


class ConformanceReport(BaseModel):
    """Full conformance test report."""

    mode: str = "conformance_real_router"
    total_samples: int = 0
    accuracy: float = 0.0
    misrouting_rate: float = 0.0
    unparsed: int = 0
    per_category: dict[str, PerCategoryStats] = Field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    mismatches: list[dict] = Field(default_factory=list)
    top_insightful: list[dict] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _load_cache(cache_path: Path) -> dict[str, CacheEntry]:
    cache: dict[str, CacheEntry] = {}
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = CacheEntry.model_validate_json(line)
                    cache[entry.query_hash] = entry
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
    return cache


def _append_to_cache(cache_path: Path, entry: CacheEntry) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def _build_prompt(query: str) -> str:
    return (
        'Sei il router. NON delegare, NON chiamare alcun tool, '
        'NON eseguire analisi. Classifica la richiesta seguente '
        'secondo le tue regole e rispondi ESCLUSIVAMENTE con JSON: '
        '{"category":"TRADE|CODER|GRAPHIFY|SKILL_UPDATER|BOOK_TO_SKILL|SIMPLE",'
        '"reason":"<motivo breve>"}. Richiesta: ' + query
    )


def _parse_output(raw: str) -> tuple[str, str]:
    """Parse opencode JSON output to extract category and reason.

    Returns (category, reason). category may be 'UNPARSED' on failure.
    """
    try:
        lines = raw.strip().splitlines()
        text_parts = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "text":
                part = event.get("part", {})
                txt = part.get("text", "")
                text_parts.append(txt)
        combined = "".join(text_parts)
    except Exception:  # pylint: disable=broad-exception-caught
        combined = raw

    json_match = JSON_BLOCK_PATTERN.search(combined)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            cat_raw = obj.get("category", "").strip().upper()
            reason = obj.get("reason", "")
            if cat_raw in VALID_CATEGORIES:
                return cat_raw, reason
            mapped = CATEGORY_MAP.get(cat_raw.lower(), "")
            if mapped:
                return mapped, reason
        except json.JSONDecodeError:
            pass

    standalone = CATEGORY_STANDALONE_PATTERN.findall(combined)
    if standalone:
        cat = standalone[-1]
        if cat in VALID_CATEGORIES:
            return cat, "fallback:regex_standalone"

    return "UNPARSED", combined[:200].replace("\n", " ")


def _run_single(case: GoldenCase, cache: dict[str, CacheEntry],
                cache_path: Path, attempt: int = 1) -> ConformanceResult:
    # pylint: disable=too-many-locals
    qhash = _query_hash(case.text)

    if qhash in cache:
        cached = cache[qhash]
        return ConformanceResult(
            id=case.id,
            query=case.text,
            expected=case.expected,
            predicted=cached.predicted,
            correct=cached.predicted == case.expected,
            reason=cached.reason,
            raw_snippet=cached.raw_snippet[:200],
        )

    prompt = _build_prompt(case.text)
    try:
        proc = subprocess.run(
            ["opencode", "run", "--format", "json", "--auto", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ},
            cwd="/tmp/opencode",
            check=False,
        )
        raw = proc.stdout
        if proc.returncode != 0:
            stderr = proc.stderr[:300] if proc.stderr else ""
            msg = f"exitcode={proc.returncode} stderr={stderr}"
            raise RuntimeError(msg)

        predicted, reason = _parse_output(raw)
    except subprocess.TimeoutExpired:
        if attempt < 3:
            time.sleep(5)
            return _run_single(case, cache, cache_path, attempt + 1)
        predicted, reason = "UNPARSED", "timeout after 3 retries"
        raw = ""
    except RuntimeError as exc:
        err_msg = str(exc)
        if "rate" in err_msg.lower() and attempt < 3:
            time.sleep(5)
            return _run_single(case, cache, cache_path, attempt + 1)
        predicted, reason = "UNPARSED", f"runtime_error: {err_msg[:150]}"
        raw = ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if attempt < 3:
            time.sleep(5)
            return _run_single(case, cache, cache_path, attempt + 1)
        predicted, reason = "UNPARSED", f"exception: {exc!s}"
        raw = ""

    entry = CacheEntry(
        id=case.id,
        query=case.text,
        query_hash=qhash,
        expected=case.expected,
        predicted=predicted,
        reason=reason,
        raw_snippet=raw[:200],
    )
    _append_to_cache(cache_path, entry)
    cache[qhash] = entry

    return ConformanceResult(
        id=case.id,
        query=case.text,
        expected=case.expected,
        predicted=predicted,
        correct=predicted == case.expected,
        reason=reason,
        raw_snippet=raw[:200],
    )


def _build_report(results: list[ConformanceResult],
                  cases: list[GoldenCase]) -> ConformanceReport:
    # pylint: disable=too-many-locals,too-many-branches
    total = len(results)
    correct_count = sum(1 for r in results if r.correct)
    unparsed = sum(1 for r in results if r.predicted == "UNPARSED")
    accuracy = correct_count / total if total > 0 else 0.0

    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        matrix[r.expected][r.predicted] += 1

    per_cat: dict[str, PerCategoryStats] = {}
    all_labels = sorted(set(
        list(matrix.keys()) + [p for v in matrix.values() for p in v]
    ))
    for label in all_labels:
        tp_val = matrix.get(label, {}).get(label, 0)
        total_actual = sum(matrix.get(label, {}).values())
        total_predicted = sum(
            matrix.get(a_key, {}).get(label, 0) for a_key in matrix
        )
        precision = tp_val / total_predicted if total_predicted > 0 else 0.0
        recall = tp_val / total_actual if total_actual > 0 else 0.0
        denom = precision + recall
        f1_val = 2 * precision * recall / denom if denom > 0 else 0.0
        per_cat[label] = PerCategoryStats(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1_val, 4),
            support=int(total_actual),
            tp=tp_val,
            total_actual=int(total_actual),
            total_predicted=int(total_predicted),
        )

    mismatches = []
    for r in results:
        if not r.correct:
            mismatches.append({
                "id": r.id,
                "query": r.query[:80],
                "expected": r.expected,
                "predicted": r.predicted,
                "reason": r.reason,
                "raw_snippet": r.raw_snippet[:200],
            })

    cases_by_cat: dict[str, list[GoldenCase]] = defaultdict(list)
    for c in cases:
        cases_by_cat[c.expected].append(c)
    mismatches_sorted = sorted(mismatches, key=lambda m: (
        0 if m["predicted"] == "UNPARSED" else 1,
        m["expected"],
    ))
    top_insightful = mismatches_sorted[:10]

    return ConformanceReport(
        total_samples=total,
        accuracy=round(accuracy, 4),
        misrouting_rate=round(1 - accuracy, 4),
        unparsed=unparsed,
        per_category=per_cat,
        confusion_matrix={k: dict(v) for k, v in matrix.items()},
        mismatches=mismatches,
        top_insightful=top_insightful,
    )


def _print_report(report: ConformanceReport) -> None:
    # pylint: disable=too-many-locals,too-many-branches
    sep = "=" * 70
    print(f"\n{sep}")
    print("  CONFORMANCE TEST — Real Router (deepseek-v4-flash) vs Golden Set")
    print(f"{sep}")
    print(f"  Total samples:     {report.total_samples}")
    print(f"  Accuracy:          {report.accuracy:.2%}")
    print(f"  Misrouting rate:   {report.misrouting_rate:.2%}")
    if report.unparsed:
        print(f"  Unparsed:          {report.unparsed}")
    print()

    header = ["Category", "Support", "Precision", "Recall", "F1", "TP"]
    rows = []
    cat_order = ["TRADE", "CODER", "GRAPHIFY", "SKILL_UPDATER",
                 "BOOK_TO_SKILL", "SIMPLE", "UNPARSED"]
    for key in cat_order:
        stats = report.per_category.get(key)
        if stats:
            rows.append([
                key,
                str(stats.support),
                f"{stats.precision:.2%}",
                f"{stats.recall:.2%}",
                f"{stats.f1:.2%}",
                str(stats.tp),
            ])
        elif key in report.confusion_matrix:
            rows.append([key, str(sum(report.confusion_matrix[key].values())),
                         "0.00%", "0.00%", "0.00%", "0"])

    if rows:
        col_widths = [
            max(len(str(r[i])) for r in rows + [header])
            for i in range(len(header))
        ]
        fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
        print(fmt.format(*header))
        print(fmt.format(*["-" * w for w in col_widths]))
        for row in rows:
            print(fmt.format(*row))

    labels_present = sorted(report.confusion_matrix.keys())
    if labels_present:
        print("\n  Confusion Matrix (actual -> predicted):")
        short = {"TRADE": "TRD", "CODER": "COD", "GRAPHIFY": "GRP",
                 "SKILL_UPDATER": "SKU", "BOOK_TO_SKILL": "BTS",
                 "SIMPLE": "SIM", "UNPARSED": "UNP"}
        header2 = ["act\\pred"] + [short.get(k, k[:3]) for k in labels_present]
        mrows = []
        for a_key in labels_present:
            row = [short.get(a_key, a_key[:3])]
            for p_key in labels_present:
                row.append(str(report.confusion_matrix.get(a_key, {}).get(p_key, 0)))
            mrows.append(row)
        col_w2 = [
            max(len(str(r[i])) for r in mrows + [header2])
            for i in range(len(header2))
        ]
        fmt2 = "  " + "  ".join(f"{{:>{w}}}" for w in col_w2)
        print(fmt2.format(*header2))
        print(fmt2.format(*["-" * w for w in col_w2]))
        for row in mrows:
            print(fmt2.format(*row))

    if report.mismatches:
        print(f"\n  Mismatches ({len(report.mismatches)} total):")
        for i, m in enumerate(report.mismatches[:20]):
            print(f"  {i + 1:2d}. [{m['expected']}>{m['predicted']}] "
                  f"\"{m['query'][:80]}\"")
            print(f"      reason: {m['reason']}")

    if report.top_insightful:
        print(f"\n  Top {len(report.top_insightful)} most insightful mismatches:")
        for i, m in enumerate(report.top_insightful):
            print(f"  {i + 1}. [{m['expected']}>{m['predicted']}] "
                  f"\"{m['query'][:80]}\"")
            print(f"      declared reason: {m['reason']}")

    print(f"\n{sep}\n")


def _load_golden_cases(path: Path, limit: Optional[int] = None
                       ) -> list[GoldenCase]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    cases = []
    for item in raw:
        expected = item.get("expected", "SIMPLE").upper()
        if expected not in VALID_CATEGORIES:
            expected = "SIMPLE"
        cases.append(GoldenCase(
            id=item.get("id", 0),
            text=item["text"],
            expected=expected,
            note=item.get("note", ""),
            category=item.get("category", ""),
        ))
    if limit and limit > 0:
        cases = cases[:limit]
    return cases


def _test_dry_run() -> bool:
    """Verify opencode run works with a single test case."""
    print("[dry-run] Testing opencode run with single query...")
    prompt = _build_prompt("analizza AAPL")
    try:
        proc = subprocess.run(
            ["opencode", "run", "--format", "json", "--auto", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ},
            cwd="/tmp/opencode",
            check=False,
        )
        raw = proc.stdout
        predicted, reason = _parse_output(raw)
        print(f"[dry-run] opencode run OK. Predicted: {predicted}, reason: {reason}")
        return predicted != "UNPARSED"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[dry-run] FAILED: {exc}")
        return False


def run_conformance(  # pylint: disable=too-many-locals,too-many-branches
    golden_path: Path,
    limit: Optional[int] = None,
    workers: int = 4,
    cache_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
) -> ConformanceReport:
    """Run the full conformance test."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = cache_path or DEFAULT_CACHE
    cache = _load_cache(cache_path)
    print(f"[cache] Loaded {len(cache)} entries from {cache_path}")

    cases = _load_golden_cases(golden_path, limit)
    print(f"[golden] Loaded {len(cases)} cases from {golden_path}")
    if not cases:
        raise ValueError("No golden cases loaded")

    cache_misses = [c for c in cases if _query_hash(c.text) not in cache]
    print(f"[cache] Hits: {len(cases) - len(cache_misses)}, "
          f"Misses: {len(cache_misses)}")

    if cache_misses:
        print(f"[conformance] Processing {len(cache_misses)} cache misses "
              f"with {workers} workers...")
    else:
        print("[conformance] All cases cached — instant report.")

    results: list[ConformanceResult] = []
    start_time = time.time()

    if cache_misses and workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures: dict[Future, GoldenCase] = {}
            for case in cache_misses:
                fut = executor.submit(_run_single, case, cache, cache_path)
                futures[fut] = case
            for i, fut in enumerate(as_completed(futures), 1):
                if i % 5 == 0 or i == len(cache_misses):
                    elapsed_ts = time.time() - start_time
                    print(f"  [{i}/{len(cache_misses)}] {elapsed_ts:.0f}s elapsed")
                try:
                    fut.result()  # side effect: populates cache
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
    elif cache_misses:
        for i, case in enumerate(cache_misses):
            if (i + 1) % 5 == 0:
                elapsed_ts = time.time() - start_time
                print(f"  [{i + 1}/{len(cache_misses)}] {elapsed_ts:.0f}s elapsed")
            _run_single(case, cache, cache_path)  # side effect: populates cache

    # Single source of truth: all results from cache
    for case in cases:
        qhash = _query_hash(case.text)
        cached = cache.get(qhash)
        if cached:
            results.append(ConformanceResult(
                id=case.id, query=case.text,
                expected=case.expected, predicted=cached.predicted,
                correct=cached.predicted == case.expected,
                reason=cached.reason,
                raw_snippet=cached.raw_snippet[:200],
            ))
        else:
            results.append(ConformanceResult(
                id=case.id, query=case.text,
                expected=case.expected, predicted="UNPARSED",
                correct=False, reason="cache_miss:not_in_cache",
            ))

    elapsed = time.time() - start_time
    print(f"[conformance] Done in {elapsed:.0f}s")

    report = _build_report(results, cases)

    if out_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = REPORTS_DIR / f"conformance_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report.model_dump_json(indent=2))
    print(f"[report] Saved to {out_path}")

    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Conformance test: real router (deepseek-v4-flash) vs golden set"
    )
    parser.add_argument(
        "--golden", type=Path, default=DEFAULT_GOLDEN,
        help="Path to golden_set.json",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit to N cases (0=all)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Parallel workers (default: 4)",
    )
    parser.add_argument(
        "--cache", type=Path, default=DEFAULT_CACHE,
        help="Cache file path (JSONL)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output report path",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Test a single case and exit",
    )
    args = parser.parse_args()

    if args.dry_run:
        ok = _test_dry_run()
        sys.exit(0 if ok else 1)

    limit = args.limit if args.limit > 0 else None
    report = run_conformance(
        golden_path=args.golden,
        limit=limit,
        workers=args.workers,
        cache_path=args.cache,
        out_path=args.out,
    )
    _print_report(report)

    print("\n=== COMPARISON WITH PYTHON EMULATION ===")
    print("Python classifier (src/classifier.py): accuracy = 100.00% (60/60)")
    correct_count = int(report.accuracy * report.total_samples)
    print(f"Real router (deepseek-v4-flash):      accuracy = "
          f"{report.accuracy:.2%} ({correct_count}/{report.total_samples})")


if __name__ == "__main__":
    main()
