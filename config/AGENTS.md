# Global Rules

## Multi-Agent Architecture
This OpenCode instance uses automatic model routing to save tokens:
- **Router (build agent)**: deepseek-v4-flash — receives all requests, classifies, delegates
- **@trade**: deepseek-v4-pro (default), escalabile a glm-5.2 per calcoli complessi — trading, options, market analysis
- **@coder**: glm-5.2 — complex coding, refactoring, multi-file changes 
- **@graphify_helper**: deepseek-v4-flash — smart graphify orchestrator, builds/updates/queries knowledge graphs
- **@skill_updater**: deepseek-v4-flash — updates skills that depend on -src submodules (graphify, book-to-skill, quant-mind, karpathy)
- **@explore / @scout**: deepseek-v4-flash — code search / web research
- **@general**: glm-5.2 — escalation target per calcoli complessi di @trade (non chiamato direttamente)

The router delegates based on keywords. Trading requests go to @trade, complex coding to @coder, skill updates to @skill_updater, graphify requests to @graphify_helper.
All agents read these AGENTS.md rules. See opencode.json for full agent configuration.

## Python Virtual Environment Mandatory
CRITICAL: Before ANY Python operation (install, run, test), load @skills/python-venv. You MUST use a virtual environment. Never `pip install` on the system Python.
- Use a SINGLE shared venv at `/tmp/opencode/.venv` for all temporary work. Never create duplicate venvs.

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
For ALL market analysis tasks, delegate to @trade (subagent_type="trade"). See `agents/trade.md` for the complete trading workflow.
All trading-specific rules (signals, execution, repair, papers) live in that file.

Skill reference (used by @trade):
- Market scanning → @skills/market-accumulation-scanner
- Stock/crypto analysis → @skills/stock-crypto-analysis
- Options analysis → @skills/options-analysis
- Options strategy → @skills/options-strategy-suggestions
- Market data → @skills/market-data-fetch
- Framework knowledge → `get_skill_knowledge` for Wyckoff, VPA, VP concepts

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
