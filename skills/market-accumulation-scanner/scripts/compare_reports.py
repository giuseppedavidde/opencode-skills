#!/usr/bin/env python3
"""
Confronto A/B tra report scanner vecchio e nuovo formato.

Confronta due report CSV (vecchio formato con 6 dimensioni, nuovo formato con 7 dimensioni
incluso competitive e sentiment breakdown) e genera un report di analisi.

Usage:
    python3 compare_reports.py <vecchio.csv> <nuovo.csv>
    python3 compare_reports.py <vecchio.csv> <nuovo.csv> --json
    python3 compare_reports.py <vecchio.csv> <nuovo.csv> --report output.md
    python3 compare_reports.py --auto  # cerca automaticamente gli ultimi due report
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


def find_latest_reports(reports_dir: str) -> tuple[str, str] | None:
    """Trova automaticamente l'ultimo report vecchio e nuovo."""
    reports_path = Path(reports_dir)
    if not reports_path.exists():
        return None

    # Trova tutti i report CSV
    all_csvs = sorted(reports_path.rglob("scan_report_*.csv"), reverse=True)
    if len(all_csvs) < 2:
        return None

    # Il primo è il più recente (nuovo formato), il secondo è il vecchio
    new_report = all_csvs[0]
    old_report = all_csvs[1]

    return str(old_report), str(new_report)


def load_report(path: str) -> pd.DataFrame:
    """Carica un report CSV e rimuove duplicati."""
    df = pd.read_csv(path)
    # Rimuovi duplicati (stesso ticker può apparire più volte)
    df = df.drop_duplicates(subset=['symbol'], keep='first')
    return df


def compare_reports(old_path: str, new_path: str) -> dict[str, Any]:
    """Confronta due report e restituisce un dizionario con l'analisi."""
    old_df = load_report(old_path)
    new_df = load_report(new_path)

    # Identifica il formato
    old_has_competitive = 'competitive' in old_df.columns
    new_has_competitive = 'competitive' in new_df.columns
    old_has_sentiment_breakdown = 'sent_si' in old_df.columns
    new_has_sentiment_breakdown = 'sent_si' in new_df.columns

    # Ticker comuni
    common_tickers = set(old_df['symbol']) & set(new_df['symbol'])

    # Confronto per ticker comuni
    comparisons = []
    for ticker in sorted(common_tickers):
        old_row = old_df[old_df['symbol'] == ticker].iloc[0]
        new_row = new_df[new_df['symbol'] == ticker].iloc[0]

        old_score = old_row['final_score']
        new_score = new_row['final_score']
        delta = new_score - old_score

        # Confronto dimensioni
        dim_comparison = {}
        for dim in ['wyckoff', 'volprof', 'pa', 'sentiment', 'fundamentals']:
            if dim in old_row and dim in new_row:
                dim_comparison[dim] = {
                    'old': old_row[dim],
                    'new': new_row[dim],
                    'delta': new_row[dim] - old_row[dim]
                }

        # Competitive (solo nel nuovo formato)
        competitive = new_row.get('competitive', None)

        # Sentiment breakdown (solo nel nuovo formato)
        sentiment_breakdown = None
        if new_has_sentiment_breakdown:
            sub_dims = {
                'si': new_row.get('sent_si'),
                'options': new_row.get('sent_options'),
                'insider': new_row.get('sent_insider'),
                'retail': new_row.get('sent_retail'),
                'institutional': new_row.get('sent_institutional'),
                'momentum': new_row.get('sent_momentum'),
            }
            # Rimuovi None
            sub_dims = {k: v for k, v in sub_dims.items() if pd.notna(v)}
            if sub_dims:
                avg_sub = sum(sub_dims.values()) / len(sub_dims)
                sentiment_breakdown = {
                    'sub_dimensions': sub_dims,
                    'average': avg_sub,
                    'aggregate': new_row['sentiment'],
                    'delta_aggregate_vs_avg': new_row['sentiment'] - avg_sub
                }

        comparisons.append({
            'ticker': ticker,
            'old_score': old_score,
            'new_score': new_score,
            'delta': delta,
            'dimensions': dim_comparison,
            'competitive': competitive,
            'sentiment_breakdown': sentiment_breakdown
        })

    # Statistiche aggregate
    deltas = [c['delta'] for c in comparisons]
    avg_delta = sum(deltas) / len(deltas) if deltas else 0

    # Impatto competitive
    competitive_impact = []
    for c in comparisons:
        if c['competitive'] is not None and pd.notna(c['competitive']):
            # Calcola quanto competitive contribuisce al final_score
            # Assumendo peso 10% e score medio 50 come baseline
            competitive_contribution = (c['competitive'] - 50) * 0.10
            competitive_impact.append({
                'ticker': c['ticker'],
                'competitive_score': c['competitive'],
                'contribution_to_final': competitive_contribution
            })

    return {
        'old_report': old_path,
        'new_report': new_path,
        'old_format': {
            'has_competitive': old_has_competitive,
            'has_sentiment_breakdown': old_has_sentiment_breakdown
        },
        'new_format': {
            'has_competitive': new_has_competitive,
            'has_sentiment_breakdown': new_has_sentiment_breakdown
        },
        'old_tickers_count': len(old_df),
        'new_tickers_count': len(new_df),
        'common_tickers_count': len(common_tickers),
        'common_tickers': sorted(common_tickers),
        'comparisons': comparisons,
        'statistics': {
            'avg_delta_score': avg_delta,
            'max_delta': max(deltas) if deltas else 0,
            'min_delta': min(deltas) if deltas else 0,
            'tickers_improved': sum(1 for d in deltas if d > 0),
            'tickers_worsened': sum(1 for d in deltas if d < 0),
            'tickers_unchanged': sum(1 for d in deltas if d == 0)
        },
        'competitive_impact': competitive_impact
    }


def format_markdown_report(result: dict[str, Any]) -> str:
    """Formatta il risultato come report markdown."""
    lines = [
        "# Report Confronto A/B Scanner",
        "",
        f"**Report vecchio**: `{result['old_report']}`",
        f"**Report nuovo**: `{result['new_report']}`",
        "",
        "## Formato",
        f"- Vecchio: {'6 dimensioni' if not result['old_format']['has_competitive'] else '7 dimensioni'}",
        f"- Nuovo: {'7 dimensioni' if result['new_format']['has_competitive'] else '6 dimensioni'}",
        f"- Ticker nel vecchio: {result['old_tickers_count']}",
        f"- Ticker nel nuovo: {result['new_tickers_count']}",
        f"- Ticker comuni: {result['common_tickers_count']}",
        "",
        "## Statistiche Aggregate",
        f"- Delta medio final_score: **{result['statistics']['avg_delta_score']:+.2f}**",
        f"- Delta massimo: {result['statistics']['max_delta']:+.2f}",
        f"- Delta minimo: {result['statistics']['min_delta']:+.2f}",
        f"- Ticker migliorati: {result['statistics']['tickers_improved']}",
        f"- Ticker peggiorati: {result['statistics']['tickers_worsened']}",
        f"- Ticker invariati: {result['statistics']['tickers_unchanged']}",
        "",
        "## Confronto per Ticker",
        "",
        "| Ticker | Vecchio | Nuovo | Delta | Competitive | Sent Δ |",
        "|--------|---------|-------|-------|-------------|--------|"
    ]

    for comp in result['comparisons']:
        competitive = f"{comp['competitive']:.0f}" if comp['competitive'] is not None else "N/A"
        sent_delta = "N/A"
        if comp['sentiment_breakdown']:
            sent_delta = f"{comp['sentiment_breakdown']['delta_aggregate_vs_avg']:+.1f}"
        lines.append(
            f"| {comp['ticker']:8s} | {comp['old_score']:5.1f} | {comp['new_score']:5.1f} | "
            f"{comp['delta']:+.1f} | {competitive:>11s} | {sent_delta:>6s} |"
        )

    # Impatto competitive
    if result['competitive_impact']:
        lines.extend([
            "",
            "## Impatto Dimensione Competitive",
            "",
            "La nuova dimensione `competitive` (peso 10%) modifica il final_score rispetto al formato vecchio.",
            "",
            "| Ticker | Competitive Score | Contributo al Final Score |",
            "|--------|-------------------|---------------------------|"
        ])
        for impact in result['competitive_impact']:
            lines.append(
                f"| {impact['ticker']:8s} | {impact['competitive_score']:17.0f} | "
                f"{impact['contribution_to_final']:+20.2f} |"
            )

    # Sentiment breakdown
    sentiment_comparisons = [c for c in result['comparisons'] if c['sentiment_breakdown']]
    if sentiment_comparisons:
        lines.extend([
            "",
            "## Analisi Sentiment Breakdown",
            "",
            "Il nuovo formato include 6 sub-dimensioni di sentiment. Confronto tra aggregato e media.",
            "",
            "| Ticker | Aggregato | Media Sub-Dim | Delta | SI | Options | Insider | Retail | Inst | Momentum |",
            "|--------|-----------|---------------|-------|----|---------|---------|--------|------|----------|"
        ])
        for comp in sentiment_comparisons:
            sb = comp['sentiment_breakdown']
            sub = sb['sub_dimensions']
            lines.append(
                f"| {comp['ticker']:8s} | {sb['aggregate']:9.0f} | {sb['average']:13.1f} | "
                f"{sb['delta_aggregate_vs_avg']:+5.1f} | "
                f"{sub.get('si', 'N/A'):>2} | {sub.get('options', 'N/A'):>7} | "
                f"{sub.get('insider', 'N/A'):>7} | {sub.get('retail', 'N/A'):>6} | "
                f"{sub.get('institutional', 'N/A'):>4} | {sub.get('momentum', 'N/A'):>8} |"
            )

    return "\n".join(lines)


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Confronto A/B tra report scanner vecchio e nuovo formato"
    )
    parser.add_argument("old_report", nargs="?", help="Path al report vecchio CSV")
    parser.add_argument("new_report", nargs="?", help="Path al report nuovo CSV")
    parser.add_argument("--auto", action="store_true",
                        help="Cerca automaticamente gli ultimi due report")
    parser.add_argument("--reports-dir", default="reports",
                        help="Directory dei report (default: reports)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--report", type=str, help="Salva report markdown nel file")
    args = parser.parse_args()

    # Determina i report da confrontare
    if args.auto:
        result = find_latest_reports(args.reports_dir)
        if not result:
            print("Errore: meno di 2 report trovati in", args.reports_dir, file=sys.stderr)
            sys.exit(1)
        old_path, new_path = result
        print(f"Auto-detect: vecchio={old_path}, nuovo={new_path}")
    else:
        if not args.old_report or not args.new_report:
            parser.error("Specificare due report o usare --auto")
        old_path = args.old_report
        new_path = args.new_report

    # Verifica che i file esistano
    if not Path(old_path).exists():
        print(f"Errore: file non trovato: {old_path}", file=sys.stderr)
        sys.exit(1)
    if not Path(new_path).exists():
        print(f"Errore: file non trovato: {new_path}", file=sys.stderr)
        sys.exit(1)

    # Esegui il confronto
    comparison = compare_reports(old_path, new_path)

    # Output
    if args.json:
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
    elif args.report:
        markdown = format_markdown_report(comparison)
        Path(args.report).write_text(markdown, encoding='utf-8')
        print(f"Report salvato in: {args.report}")
    else:
        markdown = format_markdown_report(comparison)
        print(markdown)


if __name__ == "__main__":
    main()
