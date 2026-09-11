#!/usr/bin/env python3
"""CLI evaluation runner for the OpenCode router.

Modes:
  --history       Replay classifier on historical session-level dataset
  --golden        Precision/recall/F1 on curated golden set
  --message-level Replay classifier on message-level dataset
  --before-after  Compare old vs new classifier on all datasets
  --all           Run all evaluations
"""
# pylint: disable=too-many-locals,too-many-arguments,too-many-statements,no-member

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from src.classifier import RouterClassifier

try:
    from src.classifier_v4 import classify as classify_old
except ImportError:
    try:
        from src.classifier_v1 import classify as classify_old
    except ImportError:
        from src.classifier_old import classify as classify_old
from src.extractor import extract_dataset
from src.extractor_v2 import extract_message_dataset
from src.models import (
    CategoryStats,
    ConfusionCounts,
    EvalReport,
    EvalResult,
    GoldenCase,
    RoutingLabel,
    SessionRecord,
)

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
HISTORY_DATASET = DATA_DIR / "history_dataset.jsonl"
MESSAGE_DATASET = DATA_DIR / "message_dataset.jsonl"
MISROUTED_REPORT = DATA_DIR / "misrouted_report.jsonl"
GOLDEN_SET = DATA_DIR / "golden_set.json"

ALL_LABELS = [
    RoutingLabel.TRADE,
    RoutingLabel.CODER,
    RoutingLabel.GRAPHIFY,
    RoutingLabel.SKILL_UPDATER,
    RoutingLabel.BOOK_TO_SKILL,
    RoutingLabel.SIMPLE,
]


def _label_short(label: RoutingLabel) -> str:
    mapping = {
        RoutingLabel.TRADE: "TRD",
        RoutingLabel.CODER: "COD",
        RoutingLabel.GRAPHIFY: "GRP",
        RoutingLabel.SKILL_UPDATER: "SKU",
        RoutingLabel.BOOK_TO_SKILL: "BTS",
        RoutingLabel.SIMPLE: "SIM",
        RoutingLabel.OTHER: "OTH",
    }
    return mapping.get(label, label.value[:3])


def _build_counts(results: list[EvalResult]) -> ConfusionCounts:
    """Costruisce ConfusionCounts da una lista di risultati eval."""
    counts = ConfusionCounts()
    for r in results:
        a = r.expected.value
        p = r.predicted.value
        if a not in counts.matrix:
            counts.matrix[a] = defaultdict(int)
        counts.matrix[a][p] += 1
        counts.total += 1
        if r.correct:
            counts.correct += 1
    counts.misrouted = counts.total - counts.correct

    for label in ALL_LABELS:
        key = label.value
        matrix = counts.matrix
        tp = matrix.get(key, {}).get(key, 0)
        total_actual = sum(matrix.get(key, {}).values())
        total_predicted = sum(
            matrix.get(a_key, {}).get(key, 0)
            for a_key in matrix
        )
        precision = tp / total_predicted if total_predicted > 0 else 0.0
        recall = tp / total_actual if total_actual > 0 else 0.0
        denom = precision + recall
        f1_val = 2 * precision * recall / denom if denom > 0 else 0.0
        counts.by_category[key] = {
            "tp": tp,
            "total_actual": total_actual,
            "total_predicted": total_predicted,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1_val, 4),
        }
    return counts


def _build_per_category(counts: ConfusionCounts) -> dict[str, CategoryStats]:
    result: dict[str, CategoryStats] = {}
    for k, v in counts.by_category.items():
        result[k] = CategoryStats(
            precision=v["precision"],
            recall=v["recall"],
            f1=v["f1"],
            support=int(v["total_actual"]),
        )
    return result


def _save_report(report: EvalReport, out_dir: Path, prefix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{prefix}_{ts}.json"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report.model_dump_json(indent=2))
    return path


def _run_on_records(
    records: list[SessionRecord],
    classifier_fn,
    label: str,
    out_dir: Path,
    mlabel: str = "history",
) -> EvalReport:
    results: list[EvalResult] = []
    for rec in records:
        actual = rec.actual_routing
        if actual == RoutingLabel.OTHER:
            continue
        decision = classifier_fn(rec.user_query)
        predicted = decision.label
        results.append(EvalResult(
            query=rec.user_query[:200],
            session_id=rec.session_id,
            expected=actual,
            predicted=predicted,
            correct=actual == predicted,
            reason=decision.reason,
        ))

    counts = _build_counts(results)
    misrouted = sorted(
        [r for r in results if not r.correct],
        key=lambda r: r.expected.value,
    )

    misrouted_out = DATA_DIR / f"misrouted_report_{mlabel}_{label}.jsonl"
    with open(misrouted_out, "w", encoding="utf-8") as fh:
        for r in misrouted:
            fh.write(r.model_dump_json() + "\n")

    accuracy = counts.correct / counts.total if counts.total > 0 else 0.0
    report = EvalReport(
        mode=f"{mlabel}_{label}",
        total_samples=counts.total,
        accuracy=round(accuracy, 4),
        misrouting_rate=round(1 - accuracy, 4),
        confusion=counts,
        misrouted=misrouted[:50],
        per_category=_build_per_category(counts),
    )

    report_path = _save_report(report, out_dir, f"{mlabel}_{label}")
    print(f"[{mlabel}/{label}] Report -> {report_path}")
    print(f"[{mlabel}/{label}] Misrouted -> {misrouted_out} ({len(misrouted)} cases)")
    return report


def _evaluate_model_set(  # pylint: disable=unused-argument
    model_data: list[dict],
    classifier_fn,
    out_dir: Path,
    mlabel: str,
    label: str,
) -> EvalReport:
    results: list[EvalResult] = []
    for item in model_data:
        text = item.get("text", item.get("user_query", ""))
        actual_str = item.get("expected", item.get("actual_routing", "SIMPLE"))
        session_id = item.get("session_id", item.get("id", ""))

        try:
            valid_labels = {v.value: v for v in RoutingLabel}
            actual = valid_labels.get(actual_str)
        except (ValueError, AttributeError):
            actual = None
        if actual is None or actual == RoutingLabel.OTHER:
            continue

        decision = classifier_fn(text)
        predicted = decision.label
        results.append(EvalResult(
            query=text[:200],
            session_id=str(session_id),
            expected=actual,
            predicted=predicted,
            correct=actual == predicted,
            reason=decision.reason,
        ))

    counts = _build_counts(results)
    misrouted = sorted(
        [r for r in results if not r.correct],
        key=lambda r: r.expected.value,
    )
    accuracy = counts.correct / counts.total if counts.total > 0 else 0.0

    return EvalReport(
        mode=f"{mlabel}_{label}",
        total_samples=counts.total,
        accuracy=round(accuracy, 4),
        misrouting_rate=round(1 - accuracy, 4),
        confusion=counts,
        misrouted=misrouted,
        per_category=_build_per_category(counts),
    )


def _run_golden_on(classifier_fn, out_dir: Path, label: str) -> EvalReport:
    with open(GOLDEN_SET, "r", encoding="utf-8") as fh:
        cases_raw = json.load(fh)
    cases = [GoldenCase(**c) for c in cases_raw]
    print(f"[golden/{label}] Loaded {len(cases)} golden cases")

    results: list[EvalResult] = []
    for case in cases:
        decision = classifier_fn(case.text)
        predicted = decision.label
        results.append(EvalResult(
            query=case.text,
            expected=case.expected,
            predicted=predicted,
            correct=case.expected == predicted,
            reason=decision.reason,
        ))

    counts = _build_counts(results)
    misrouted = [r for r in results if not r.correct]
    accuracy = counts.correct / counts.total if counts.total > 0 else 0.0

    report = EvalReport(
        mode=f"golden_{label}",
        total_samples=counts.total,
        accuracy=round(accuracy, 4),
        misrouting_rate=round(1 - accuracy, 4),
        confusion=counts,
        misrouted=misrouted,
        per_category=_build_per_category(counts),
    )

    report_path = _save_report(report, out_dir, f"golden_{label}")
    print(f"[golden/{label}] Report -> {report_path}")
    return report


def run_history(  # pylint: disable=missing-function-docstring
    classifier_fn, output_dir: str | None = None,
    label: str = "v2",
) -> EvalReport:
    out_dir = Path(output_dir) if output_dir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not HISTORY_DATASET.exists():
        print("[extractor] Dataset not found. Extracting from DB...")
        extract_dataset()

    records: list[SessionRecord] = []
    with open(HISTORY_DATASET, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(SessionRecord.model_validate_json(line))

    print(f"[history/{label}] Loaded {len(records)} session records")
    return _run_on_records(records, classifier_fn, label, out_dir, "history")


def run_message_level(  # pylint: disable=missing-function-docstring
    classifier_fn, output_dir: str | None = None,
    label: str = "v2",
) -> EvalReport:
    out_dir = Path(output_dir) if output_dir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not MESSAGE_DATASET.exists():
        print("[extractor-v2] Message-level dataset not found. Extracting from DB...")
        extract_message_dataset()

    raw: list[dict] = []
    with open(MESSAGE_DATASET, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                raw.append(json.loads(line))

    print(f"[message-level/{label}] Loaded {len(raw)} message records")
    return _evaluate_model_set(raw, classifier_fn, out_dir, "message", label)


def run_golden(  # pylint: disable=missing-function-docstring
    classifier_fn,
    output_dir: str | None = None,
    label: str = "v2",
) -> EvalReport:
    out_dir = Path(output_dir) if output_dir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    return _run_golden_on(classifier_fn, out_dir, label)


def print_report(report: EvalReport) -> None:  # pylint: disable=missing-function-docstring
    """Stampa a terminale il report formattato."""
    header_sep = "=" * 70
    print(f"\n{header_sep}")
    print(f"  REPORT: {report.mode.upper()}")
    print(f"{header_sep}")
    print(f"  Total samples:    {report.total_samples}")
    print(f"  Accuracy:         {report.accuracy:.2%}")
    print(f"  Misrouting rate:  {report.misrouting_rate:.2%}")
    print()

    labels_ordered = [
        l.value for l in ALL_LABELS if l.value in report.confusion.matrix
    ]
    header = ["Category", "Support", "Precision", "Recall", "F1", "TP"]

    rows = []
    for key in labels_ordered:
        stats = report.per_category.get(key)
        cstats = report.confusion.by_category.get(key, {})
        if stats:
            rows.append([
                key,
                str(stats.support),
                f"{stats.precision:.2%}",
                f"{stats.recall:.2%}",
                f"{stats.f1:.2%}",
                str(cstats.get("tp", 0)),
            ])

    col_widths = [
        max(len(str(r[i])) for r in rows + [header]) for i in range(len(header))
    ]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*row))

    matrix = report.confusion.matrix
    print("\n  Confusion Matrix (actual -> predicted):")
    short_labels = {
        l.value: _label_short(l) for l in ALL_LABELS if l.value in matrix
    }
    present = list(short_labels.keys())
    header2 = ["act\\pred"] + [short_labels[k] for k in present]
    matrix_rows = []
    for a_key in present:
        row = [short_labels[a_key]]
        for p_key in present:
            row.append(str(matrix.get(a_key, {}).get(p_key, 0)))
        matrix_rows.append(row)

    col_w2 = [
        max(len(str(r[i])) for r in matrix_rows + [header2])
        for i in range(len(header2))
    ]
    fmt2 = "  " + "  ".join(f"{{:>{w}}}" for w in col_w2)
    print(fmt2.format(*header2))
    print(fmt2.format(*["-" * w for w in col_w2]))
    for row in matrix_rows:
        print(fmt2.format(*row))

    if report.misrouted:
        print("\n  Top misrouted cases:")
        for i, m in enumerate(report.misrouted[:15], 1):
            query_short = m.query[:100].replace("\n", " ")
            print(f"  {i:2d}. [{m.expected.value}>{m.predicted.value}] {query_short}")
            if m.reason:
                print(f"      reason: {m.reason}")

    print(f"\n{header_sep}\n")


def _make_old_classifier_fn():
    """Return the old classifier's classify function for before/after comparison.
    Uses classifier_v1 if available, falls back to classifier_old."""
    return classify_old


def _make_new_classifier_fn():
    """Return the new classifier's classify function."""
    classifier = RouterClassifier()
    return classifier.classify


def run_before_after(output_dir: str | None = None) -> None:
    """Run both old and new classifier on all datasets and compare."""
    out_dir = Path(output_dir) if output_dir else REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    old_fn = _make_old_classifier_fn()
    new_fn = _make_new_classifier_fn()

    print("\n" + "=" * 70)
    print("  BEFORE/AFTER COMPARISON")
    print("=" * 70)

    print("\n--- OLD CLASSIFIER (baseline) ---")
    old_golden = run_golden(old_fn, out_dir, "old")
    old_history = run_history(old_fn, out_dir, "old")
    old_message = run_message_level(old_fn, out_dir, "old")

    print("\n--- NEW CLASSIFIER (contextual disambiguation) ---")
    new_golden = run_golden(new_fn, out_dir, "new")
    new_history = run_history(new_fn, out_dir, "new")
    new_message = run_message_level(new_fn, out_dir, "new")

    print("\n" + "=" * 70)
    print("  SUMMARY COMPARISON")
    print("=" * 70)

    def _fmt_rate(r: float) -> str:
        return f"{r:.2%}"

    datasets = [
        ("Golden set", old_golden, new_golden),
        ("History (session-level)", old_history, new_history),
        ("Message-level", old_message, new_message),
    ]

    for name, old_r, new_r in datasets:
        delta_acc = (new_r.accuracy - old_r.accuracy) * 100
        delta_mis = (old_r.misrouting_rate - new_r.misrouting_rate) * 100
        print(f"\n  {name}:")
        print(f"    Accuracy:      {_fmt_rate(old_r.accuracy)} -> "
              f"{_fmt_rate(new_r.accuracy)}  ({delta_acc:+.1f}pp)")
        print(f"    Misrouting:    {_fmt_rate(old_r.misrouting_rate)} -> "
              f"{_fmt_rate(new_r.misrouting_rate)}  ({delta_mis:+.1f}pp)")

    for label in ALL_LABELS:
        key = label.value
        old_stats = old_message.per_category.get(key)
        new_stats = new_message.per_category.get(key)
        if old_stats or new_stats:
            old_prec = old_stats.precision if old_stats else 0.0
            new_prec = new_stats.precision if new_stats else 0.0
            old_rec = old_stats.recall if old_stats else 0.0
            new_rec = new_stats.recall if new_stats else 0.0
            old_f1 = old_stats.f1 if old_stats else 0.0
            new_f1 = new_stats.f1 if new_stats else 0.0
            print(f"\n  {key} (message-level):")
            print(f"    Precision:     {_fmt_rate(old_prec)} -> {_fmt_rate(new_prec)}")
            print(f"    Recall:        {_fmt_rate(old_rec)} -> {_fmt_rate(new_rec)}")
            print(f"    F1:            {_fmt_rate(old_f1)} -> {_fmt_rate(new_f1)}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"before_after_{ts}.json"
    comparison = {
        "generated_at": ts,
        "golden": {
            "old": {"accuracy": old_golden.accuracy, "misrouting_rate": old_golden.misrouting_rate},
            "new": {"accuracy": new_golden.accuracy, "misrouting_rate": new_golden.misrouting_rate},
        },
        "history": {
            "old": {
                "accuracy": old_history.accuracy,
                "misrouting_rate": old_history.misrouting_rate,
            },
            "new": {
                "accuracy": new_history.accuracy,
                "misrouting_rate": new_history.misrouting_rate,
            },
        },
        "message_level": {
            "old": {
                "accuracy": old_message.accuracy,
                "misrouting_rate": old_message.misrouting_rate,
            },
            "new": {
                "accuracy": new_message.accuracy,
                "misrouting_rate": new_message.misrouting_rate,
            },
        },
        "per_category_message_level": {
            key: {
                "old": {
                    "precision": old_message.per_category.get(key, CategoryStats()).precision,
                    "recall": old_message.per_category.get(key, CategoryStats()).recall,
                    "f1": old_message.per_category.get(key, CategoryStats()).f1,
                },
                "new": {
                    "precision": new_message.per_category.get(key, CategoryStats()).precision,
                    "recall": new_message.per_category.get(key, CategoryStats()).recall,
                    "f1": new_message.per_category.get(key, CategoryStats()).f1,
                },
            }
            for key, label in [(l.value, l) for l in ALL_LABELS]
            if old_message.per_category.get(key) or new_message.per_category.get(key)
        },
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(comparison, fh, indent=2, ensure_ascii=False)
    print(f"\n  Comparison report -> {report_path}")


def main() -> None:  # pylint: disable=missing-function-docstring
    parser = argparse.ArgumentParser(
        description="OpenCode Router Evaluation Harness"
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Replay classifier on historical dataset",
    )
    parser.add_argument(
        "--golden", action="store_true",
        help="Evaluate on curated golden set",
    )
    parser.add_argument(
        "--message-level", action="store_true",
        help="Evaluate on message-level dataset (extracts if needed)",
    )
    parser.add_argument(
        "--before-after", action="store_true",
        help="Compare old vs new classifier on all datasets",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all evaluations",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Output directory for reports",
    )
    args = parser.parse_args()

    if not (args.history or args.golden or args.message_level
            or args.before_after or args.all):
        parser.print_help()
        sys.exit(1)

    if args.before_after:
        run_before_after(args.output_dir)
        return

    classifier = RouterClassifier()
    fn = classifier.classify

    if args.history or args.all:
        report = run_history(fn, args.output_dir, "v2")
        print_report(report)

    if args.golden or args.all:
        report = run_golden(fn, args.output_dir, "v2")
        print_report(report)

    if args.message_level or args.all:
        report = run_message_level(fn, args.output_dir, "v2")
        print_report(report)


if __name__ == "__main__":
    main()
