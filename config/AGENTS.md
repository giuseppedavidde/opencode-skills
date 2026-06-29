# Global Rules

## Python Virtual Environment Mandatory
CRITICAL: Before ANY Python operation (install, run, test), load @skills/python-venv. You MUST use a virtual environment. Never `pip install` on the system Python.

## Python Development Standards
CRITICAL: Whenever working with Python, you MUST load and strictly adhere to the instructions defined in @skills/python-pydantic.

This includes:
- Mandatory use of Pydantic for data models.
- Extensive use of type hinting.
- Ensuring all code is PEP 8 compliant and pythonic.
- Verifying all Python code with `pylint` before proposing it to the user.

## Graphify Knowledge Graph
CRITICAL: Whenever you need to understand a codebase, project architecture, or file relationships, load the @skills/graphify skill and use `/graphify .` to build a knowledge graph. This turns any folder into a queryable graph with community detection, god nodes, and surprising connections.

## Trading Analysis
For ALL market analysis tasks, load the relevant @skills directly. The skills are well-organized and handle MCP usage internally.
- Market scanning → @skills/market-accumulation-scanner
- Stock/crypto analysis → @skills/stock-crypto-analysis
- Options analysis → @skills/options-analysis
- Options strategy → @skills/options-strategy-suggestions
- Market data → @skills/market-data-fetch
- Framework knowledge → use `get_skill_knowledge` for on-demand Wyckoff, VPA, VP concepts

Always run `get_macro_context` FIRST before any analysis.

### Trading outputs + Headroom Compression
Trading outputs (scans, analyses, options chains) are large JSON payloads.
Compress them with `headroom_compress` BEFORE reasoning over the content.
- scan results with 10+ tickers → compress immediately, retrieve only top 3 for deep dive
- analyze_stock → compress, retrieve only dimensions/verdict/confidence
- fetch_options_chain → compress the full chain, retrieve only ATM strikes + IV metrics
- Never paste raw trading JSON into reasoning context uncompressed
- Batch compress: if scan + 3× analyze_stock return in one turn, compress all in parallel

## Headroom Compression — MANDATORY & ACTIVE
CRITICAL: You MUST use headroom to compress content and minimize token usage at ALL times.
This is NOT optional or situational: every session must demonstrate measurable compression.
A session that ends with `headroom_stats` showing 0 compressions is a FAILED session.

### When to compress (threshold: ≥800 chars of tool output)
Compress with `headroom_compress` BEFORE reasoning over the content, in these cases:
1. **Any tool result ≥800 chars** — bash, read, grep, glob, webfetch, task outputs.
2. **JSON/CSV reports** — scanner outputs, deep-dive JSON, options chain dumps, earnings data.
3. **Multi-file reads** — when reading 2+ files in parallel, compress each non-trivial one.
4. **Skill content** — when a loaded skill's SKILL.md is long, compress it after first read.
5. **Large bash outputs** — piped command results, directory listings, log tails.

### Workflow rules — GOAL: maximize token savings
- **Compress the RAW tool output, not a summary**: ALWAYS pass the original, intact tool result
  to `headroom_compress`. NEVER substitute it with your own hand-written summary, excerpt, or
  paraphrase. A summary bypasses the compressor and yields `router:noop` (0 tokens saved).
  The compressor needs the full text to achieve real 70-85% reduction.
- **Compress early, retrieve late**: compress on first sight, use `headroom_retrieve` with the hash
  only when you actually need full detail (numbers, exact strings, code).
- **Always prefer compression over truncation** — Never use head/tail to limit output when you
  can compress and retrieve on demand.
- **Check `headroom_stats` at least twice per session**: once mid-session, once at the end.
- **Quote hashes, not full content** — when referring to compressed data, reference the hash,
  don't re-paste the original.
- **Batch compress**: if multiple tools return large content in one turn, call `headroom_compress`
  once per result, in parallel.
- **Verify non-noop**: after each compress, confirm the returned `strategy` is NOT `router:noop`.
  If it IS noop, the input was too small or already compressed — feed larger raw content next time.

### Anti-patterns (forbidden)
- **Passing a hand-written summary to `headroom_compress` instead of the raw tool output** (causes
  noop, 0 savings — this is the #1 failure mode).
- Reasoning over >800-char tool output without compressing it first.
- Pasting full scanner JSON / analysis JSON into your reasoning context uncompressed.
- Ending a session without calling `headroom_stats`.
- Using `head`/`tail`/`limit` on tool outputs instead of compressing.
- Treating the rule as "best effort": it is a hard requirement, like using a Python venv.
