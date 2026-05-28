#!/usr/bin/env python3
"""Auto-detect book type, title, and author from extracted text.

Usage:
    auto_detect.py <full_text.txt>

Output (stdout):
    JSON: {"mode": "technical"|"text", "title": "...", "author": "..."}

Heuristics:
    - table_density > 1.5%  → technical
    - trading_score > 20     → technical
    - code_density > 5%      → technical
    - otherwise              → text
"""

import json
import re
import sys
from pathlib import Path

TRADING_KEYWORDS = [
    "wyckoff", "volume", "vpa", "vap", "poc", "hvn", "lvn", "value area",
    "accumulation", "distribution", "spring", "upthrust", "shakeout",
    "breakout", "breakdown", "support", "resistance", "price action",
    "candle", "bullish", "bearish", "trendline", "order flow", "footprint",
    "bid", "ask", "spread", "liquidity", "momentum", "divergence",
    "consolidation", "reversal", "continuation", "volume profile",
    "market profile", "tpo", "point of control", "volume point of control",
    "buying climax", "selling climax", "stopping volume", "test",
    "reaction", "rally", "decline", "trading range", "channel",
    "moving average", "ema", "rsi", "macd", "stochastic", "bollinger",
    "fibonacci", "retracement", "option", "call", "put", "strike",
    "premium", "greeks", "delta", "gamma", "theta", "vega",
    "implied volatility", "historical volatility", "scalping",
    "bid ask spread", "level 2", "time and sales", "tape reading",
    "institutional", "smart money", "market maker", "blockchain",
    "cryptocurrency", "bitcoin", "ethereum", "trading", "stock",
    "future", "forex", "market", "chart pattern",
]


def detect_mode(text: str) -> str:
    """Detect whether book is technical (tables/code) or text-heavy."""
    lines = text.split("\n")
    total = len(lines)
    if total == 0:
        return "text"

    table_lines = sum(1 for l in lines if "|" in l or "\t" in l)
    table_density = table_lines / total

    code_lines = sum(1 for l in lines if l.startswith(("    ", "\t")) and len(l) > 10)
    code_density = code_lines / total

    text_lower = text.lower()
    trading_score = sum(
        1 for kw in TRADING_KEYWORDS if kw.lower() in text_lower
    )

    if table_density > 0.015 or code_density > 0.05 or trading_score > 20:
        return "technical"
    return "text"


def detect_title_and_author(text: str) -> tuple[str, str]:
    """Extract book title and author from first pages."""
    lines = text.split("\n")[:200]
    title_buffer: list[str] = []
    author = "Unknown"
    found_by = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r"^\d+$", stripped):
            continue
        if "copyright" in stripped.lower() or "all rights" in stripped.lower():
            break
        if stripped.startswith("##") or stripped.startswith("Page"):
            continue
        if stripped.startswith("www.") or stripped.startswith("http"):
            continue
        if re.match(r"^[•\-*]\s", stripped):
            continue

        low = stripped.lower()
        if low == "by" or low.startswith("by "):
            found_by = True
            remainder = stripped[2:].strip() if low.startswith("by ") else ""
            if remainder and not remainder.startswith("www"):
                author = remainder.strip(".,:;\"'")
            elif i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith("www"):
                    author = next_line.strip(".,:;\"'")
            break

        if len(stripped) < 4:
            continue
        first_char = stripped[0]
        if first_char.isupper() or first_char.isdigit():
            title_buffer.append(stripped)

    title = " ".join(title_buffer) if title_buffer else "Untitled Document"
    title = re.sub(r"\s+", " ", title).strip().strip(".,:;\"'")
    if len(title) > 150:
        title = title[:147] + "..."

    return title if len(title) > 10 else "Untitled Document", author


def detect_title(text: str) -> str:
    return detect_title_and_author(text)[0]


def detect_author(text: str) -> str:
    return detect_title_and_author(text)[1]


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"mode": "text", "title": "Untitled", "author": "Unknown"}))
        return

    path = Path(sys.argv[1])
    if not path.exists():
        print(json.dumps({"mode": "text", "title": "Untitled", "author": "Unknown"}))
        sys.exit(1)

    text = path.read_text(encoding="utf-8", errors="replace")
    sample = text[:50000]

    result = {
        "mode": detect_mode(sample),
        "title": detect_title(sample),
        "author": detect_author(sample),
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
