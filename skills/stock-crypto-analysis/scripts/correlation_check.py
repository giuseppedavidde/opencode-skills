#!/usr/bin/env python3
"""
Portfolio correlation checker.

Computes the correlation matrix for a list of tickers and warns
when positions are too concentrated even across different sectors.

Usage:
    python3 correlation_check.py --tickers AAPL,MSFT,NVDA --days 252
    python3 correlation_check.py --positions portfolio.json --days 126
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

import pandas as pd


def fetch_correlation_matrix(tickers: list[str], days: int = 252) -> pd.DataFrame:
    """Fetch close prices and compute Pearson correlation matrix."""
    try:
        import yfinance as yf  # pylint: disable=import-outside-toplevel
    except ImportError:
        print("Error: yfinance not installed.", file=sys.stderr)
        sys.exit(1)

    closes = {}
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker).history(period=f"{days}d", interval="1d")
            if not data.empty and "Close" in data.columns:
                closes[ticker] = data["Close"]
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    if len(closes) < 2:
        print("Error: Need at least 2 tickers with valid data.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(closes).dropna()
    if df.empty or len(df.columns) < 2:
        print("Error: No overlapping data found.", file=sys.stderr)
        sys.exit(1)

    # Compute correlation on daily returns
    returns = df.pct_change().dropna()
    if len(returns) < 20:
        print("Error: Not enough returns data (need >20 overlapping days).", file=sys.stderr)
        sys.exit(1)

    return returns.corr()


def compute_hierarchical_clusters(corr: pd.DataFrame, threshold: float = 0.70) -> list[list[str]]:
    """Find groups of highly correlated tickers using a simple graph-based approach."""
    tickers = list(corr.columns)
    n_ = len(tickers)

    # Build adjacency: ticker i connected to j if corr > threshold
    adj: list[set[int]] = [set() for _ in range(n_)]
    for i in range(n_):
        for j in range(i + 1, n_):
            if abs(corr.iloc[i, j]) > threshold:
                adj[i].add(j)
                adj[j].add(i)

    # Find connected components (clusters)
    visited = [False] * n_
    clusters = []
    for i in range(n_):
        if visited[i]:
            continue
        component = []
        stack = [i]
        visited[i] = True
        while stack:
            node = stack.pop()
            component.append(tickers[node])
            for neighbor in adj[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    stack.append(neighbor)
        if len(component) >= 2:
            clusters.append(sorted(component))

    return clusters


def compute_diversification_score(corr: pd.DataFrame,
                                  positions: Optional[dict[str, float]] = None) -> float:
    """Compute a simple diversification score (0-100)."""
    tickers = list(corr.columns)
    n_ = len(tickers)

    if n_ < 2:
        return 100.0

    if positions is None:
        positions = {t: 1.0 / n_ for t in tickers}

    # Weighted portfolio variance
    weights = [positions.get(t, 1.0 / n_) for t in tickers]
    total = sum(weights)
    if total == 0:
        return 0.0
    weights = [w / total for w in weights]

    # Simple metric: 100 - (avg absolute pairwise correlation * 100)
    pairwise_corrs = []
    for i in range(n_):
        for j in range(i + 1, n_):
            pairwise_corrs.append(abs(corr.iloc[i, j]))
    avg_corr = sum(pairwise_corrs) / len(pairwise_corrs) if pairwise_corrs else 0

    return round(100 * (1.0 - avg_corr), 1)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Portfolio correlation checker")
    parser.add_argument("--tickers", required=True, help="Comma-separated list of tickers")
    parser.add_argument("--days", type=int, default=252, help="Lookback days for correlation")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Correlation threshold for cluster detection")
    parser.add_argument("--positions", type=str, help="JSON file with {ticker: weight}")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if len(tickers) < 2:
        print("Need at least 2 tickers.")
        sys.exit(1)

    corr = fetch_correlation_matrix(tickers, args.days)

    # Load positions if provided
    positions = None
    if args.positions:
        with open(args.positions, encoding="utf-8") as f:
            positions = json.load(f)

    clusters = compute_hierarchical_clusters(corr, args.threshold)
    div_score = compute_diversification_score(corr, positions)

    if args.json:
        output = {
            "diversification_score": div_score,
            "correlation_matrix": corr.to_dict(),
            "clusters": clusters,
            "tickers": list(corr.columns),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print("=" * 50)
    print("PORTFOLIO CORRELATION ANALYSIS")
    print("=" * 50)
    print(f"Tickers: {', '.join(list(corr.columns))}")
    print(f"Lookback: {args.days} days")
    print(f"Diversification Score: {div_score}/100 (higher = better)")
    print()

    if clusters:
        print(f"\u26a0\ufe0f  High correlation clusters detected (r > {args.threshold:.0%}):")
        for cluster in clusters:
            print(f"  Cluster: {', '.join(cluster)}")
            for i, t1 in enumerate(cluster):
                for t2 in cluster[i + 1:]:
                    r = corr.loc[t1, t2]
                    print(f"    {t1} ↔ {t2}: r = {r:.3f}")
        print()
        print("Recommendation: Reduce combined weight in these clusters")
        print("  to avoid concentration risk.")
    else:
        print("✓ No high correlation clusters detected.")

    if positions and clusters:
        print("\n--- Position-Adjusted Warning ---")
        for cluster in clusters:
            combined = sum(positions.get(t, 0) for t in cluster)
            if combined > 0.25:
                print(f"  ⚠️  {', '.join(cluster)}: combined weight {combined:.1%} > 25% limit")


if __name__ == "__main__":
    main()
