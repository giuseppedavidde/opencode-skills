#!/usr/bin/env python3
"""
infer.py — Legge SKILL.md di qualsiasi skill, estrae metadati orchestrator.
Se il frontmatter ha già orchestrator:, lo restituisce.
Altrimenti inferisce da pattern strutturali (CLI args, tabelle output, capitoli).
"""

import sys
import re
import json
from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from SKILL.md text. Returns (frontmatter_dict, body_text)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    # Simple YAML parser (no PyYAML dependency needed)
    result = {}
    current_key = None
    current_list = None
    indent_stack = []

    for line in yaml_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Detect list item
        if stripped.startswith("- "):
            val = stripped[2:].strip()
            if current_list is not None:
                current_list.append(val)
            continue

        # Detect key:
        if ":" in stripped:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            rest = stripped[colon_idx + 1:].strip()

            # Nested key (indented)
            leading = len(line) - len(line.lstrip())
            if leading > 0 and current_key:
                if isinstance(result.get(current_key), dict):
                    result[current_key][key] = _parse_yaml_value(rest)
                continue

            current_key = key
            current_list = None

            if rest == "":
                # Could be a list or dict next
                result[key] = {}
                # Check if next non-empty line has list items
            elif rest.startswith("["):
                # Inline list like [a, b, c]
                items = [x.strip().strip('"').strip("'") for x in rest.strip("[]").split(",") if x.strip()]
                result[key] = items
            else:
                result[key] = _parse_yaml_value(rest)

        # Detect nested dict key under orchestrator
        leading = len(line) - len(line.lstrip())
        if leading >= 2 and ":" in stripped and current_key:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            if isinstance(result.get(current_key), dict):
                result[current_key][k] = _parse_yaml_value(v)

    # Post-process nested dicts for orchestrator
    # Re-parse for nested structures properly
    result = _parse_nested_yaml(yaml_text)

    return result, body


def _parse_yaml_value(val: str):
    """Parse a YAML scalar value."""
    val = val.strip()
    if val == "true":
        return True
    if val == "false":
        return False
    if val == "null" or val == "~":
        return None
    try:
        if "." in val:
            return float(val)
        return int(val)
    except (ValueError, TypeError):
        pass
    val = val.strip('"').strip("'")
    return val


def _parse_nested_yaml(yaml_text: str) -> dict:
    """Proper nested YAML parser for our specific frontmatter format."""
    result = {}
    lines = yaml_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if stripped.startswith("- "):
            i += 1
            continue

        if ":" in stripped:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            rest = stripped[colon_idx + 1:].strip()
            indent = len(line) - len(line.lstrip())

            if indent == 0:
                # Top-level key
                if rest == "":
                    # Nested block follows
                    nested = {}
                    i += 1
                    while i < len(lines):
                        nline = lines[i]
                        nstripped = nline.strip()
                        nindent = len(nline) - len(nline.lstrip())
                        if nindent <= indent or not nstripped:
                            break
                        if nstripped.startswith("- "):
                            val = nstripped[2:].strip()
                            if key not in result:
                                result[key] = []
                            if isinstance(result.get(key), list):
                                result[key].append(_parse_yaml_value(val))
                            else:
                                result[key] = [_parse_yaml_value(val)]
                        elif ":" in nstripped:
                            nk, nv = nstripped.split(":", 1)
                            nk = nk.strip()
                            nv = nv.strip()
                            if nv == "":
                                sub = {}
                                i += 1
                                while i < len(lines):
                                    sline = lines[i]
                                    sstripped = sline.strip()
                                    sindent = len(sline) - len(sline.lstrip())
                                    if sindent <= nindent or not sstripped:
                                        break
                                    if ":" in sstripped:
                                        sk, sv = sstripped.split(":", 1)
                                        sub[sk.strip()] = _parse_yaml_value(sv.strip())
                                    i += 1
                                nested[nk] = sub
                                continue
                            else:
                                nested[nk] = _parse_yaml_value(nv)
                        i += 1
                    result[key] = nested
                    continue
                else:
                    result[key] = _parse_yaml_value(rest)
        i += 1
    return result


def infer_from_body(body: str, skill_dir: Path) -> dict:
    """Infer orchestrator metadata from SKILL.md body when frontmatter is missing."""
    inference = {
        "parallel": False,
        "split_by": "none",
        "confidence": 0.0,
        "reason": "No orchestrator frontmatter found"
    }

    has_scripts = (skill_dir / "scripts").exists()
    has_cli = bool(re.search(r'--tickers|--universe|--files|--source|--input', body))
    has_score_col = bool(re.search(r'\b(final_)?score\b', body, re.IGNORECASE))
    has_table_output = bool(re.search(r'\|.*Score.*\|.*WYCK.*\|', body))
    has_chapters = bool(re.search(r'chapters/', body) or (skill_dir / "chapters").exists())
    has_ticker_arg = bool(re.search(r'argument-hint.*ticker', body))
    has_market_table = bool(re.search(r'us_large|italy|germany|france', body))

    if has_cli and has_ticker_arg:
        inference = {
            "parallel": True,
            "split_by": "ticker",
            "chunk_size": 15 if "scanner" in body.lower() else 1,
            "merge": "rank" if has_score_col else "concat",
            "merge_key": "final_score" if has_score_col else None,
            "confidence": 0.8,
            "reason": "CLI --tickers found, ticker-based split"
        }
    elif has_cli and has_market_table:
        inference = {
            "parallel": True,
            "split_by": "market",
            "chunk_size": 1,
            "merge": "rank" if has_score_col else "concat",
            "merge_key": "final_score" if has_score_col else None,
            "confidence": 0.7,
            "reason": "Universe/market table found, market-based split"
        }
    elif has_cli and re.search(r'--files|--source|--input', body):
        inference = {
            "parallel": True,
            "split_by": "file",
            "chunk_size": 20,
            "merge": "concat",
            "confidence": 0.7,
            "reason": "CLI --files/--source found, file-based split"
        }
    elif has_chapters:
        inference = {
            "parallel": True,
            "split_by": "chapter",
            "chunk_size": 1,
            "merge": "none",
            "confidence": 0.6,
            "reason": "Chapters directory found, chapter-based split"
        }
    elif has_scripts:
        inference = {
            "parallel": True,
            "split_by": "ticker",
            "chunk_size": 1,
            "merge": "concat",
            "confidence": 0.4,
            "reason": "Has scripts/ but no clear split indicator"
        }
    else:
        inference = {
            "parallel": False,
            "type": "kb",
            "confidence": 0.9,
            "reason": "No scripts, no CLI, no chapters — pure knowledge base"
        }

    return inference


def infer(skill_path: str) -> dict:
    """
    Main entry point.
    Returns orchestrator metadata dict for the given skill path.
    """
    path = Path(skill_path).expanduser().resolve()
    if path.is_dir():
        path = path / "SKILL.md"
    if not path.exists():
        return {"error": f"File not found: {path}", "parallel": False}

    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)

    # If orchestrator already in frontmatter, return it
    if "orchestrator" in frontmatter:
        result = frontmatter["orchestrator"]
        result["_source"] = "frontmatter"
        return result

    # Infer from body
    inferred = infer_from_body(body, path.parent)
    inferred["_source"] = "inference"
    return inferred


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Infer orchestrator metadata from a skill")
    parser.add_argument("skill_path", help="Path to skill directory or SKILL.md")
    args = parser.parse_args()

    result = infer(args.skill_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
