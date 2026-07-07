# Global Rules

## Multi-Agent Architecture
This OpenCode instance uses automatic model routing to save tokens:
- **Router (build agent)**: deepseek-v4-flash — receives all requests, classifies, delegates
- **@trade**: glm-5.2 — trading, options, market analysis 
- **@coder**: glm-5.2 — complex coding, refactoring, multi-file changes 
- **@graphify_helper**: deepseek-v4-flash — smart graphify orchestrator, builds/updates/queries knowledge graphs
- **@skill_updater**: deepseek-v4-flash — updates skills that depend on -src submodules
- **@explore / @scout**: deepseek-v4-flash — code search / web research

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
For ALL market analysis tasks, load the relevant @skills directly. The skills are well-organized and handle MCP usage internally.
- Market scanning → @skills/market-accumulation-scanner
- Stock/crypto analysis → @skills/stock-crypto-analysis
- Options analysis → @skills/options-analysis
- Options strategy → @skills/options-strategy-suggestions
- Market data → @skills/market-data-fetch
- Framework knowledge → use `get_skill_knowledge` for on-demand Wyckoff, VPA, VP concepts

Always run `get_macro_context` FIRST before any analysis.

### Position Repair Mandatory (CRITICAL)
When a user presents an EXISTING options position and asks what to do / how to fix it:
1. Run the standard flow: macro → `analyze_stock` → `analyze_options` → `suggest_options_strategy`
2. **MANDATORY RISK AUDIT** — after step 1, audit the position for these risk flags:
   - **Naked options** (short call/put without protection) → propose a spread to cap max loss
   - **Negative gamma** on a directional position → propose adding long options to flip gamma positive
   - **Unbalanced ratio** (e.g., 2:1 short vs long) → propose rebalancing to reduce leverage
   - **Deep OTM positions** (delta < 0.15 total) → propose repair or close
3. For EACH risk flag found, test at least 2 strikes with `analyze_options` in parallel
4. Present a comparison table (current vs proposed adjustments) with: max loss, breakeven, net credit/debit, delta, gamma
5. The directional verdict alone is NOT sufficient — always optimize risk regardless of outlook
6. Query `get_skill_knowledge("options-playbook")` for relevant strategy definitions when proposing repairs

### Options Execution Rules (CRITICAL — zero tolerance)
These rules apply to ANY options trade proposal (repair, diagonal, spread, roll, etc.):

1. **TIME-SHIFTED PREMIUMS — NEVER quote today's premium for a future date.**
   - If proposing "on date X, sell Y strike @ $Z", $Z must be computed as: today's_premium − (theta × days_until_X) − (delta × expected_price_move).
   - Use `bash` with `python3` to compute this. Show the work.
   - Example WRONG: "Il 10 luglio vendi 300C Jul17 @ $3.18" — $3.18 is today, not July 10.
   - Example RIGHT: compute theta decay over N days, subtract from today's mid.

2. **BID-ASK SPREADS — never assume fills at mid.**
   - Fetch real bid/ask via `fetch_options_chain` or `analyze_options`. If unavailable, estimate spread as 25-35% of mid for LHX-tier liquidity and flag the uncertainty.
   - Compute P&L using the **bid** for sells and the **ask** for buys.
   - If spread >50% of mid, warn the user the trade may not be executable at acceptable prices.

3. **ROLL BREAK-EVEN — compute the exact price where roll flips from credit to debit.**
   - Use `bash` with `python3`. Sweep prices from current to short strike + 20%.
   - At each price: estimate buyback cost of current short option (intrinsic + residual time value) vs premium of new short option at roll strike/expiry.
   - Report the break-even price. Never say "you can always roll at a credit."

4. **CHECK ALL EXPIRATIONS — never propose only the nearest monthly.**
   - Inspect `expirations` array from `analyze_stock` options_context.
   - Evaluate at least the next 4-5 expirations (weekly + monthly) before recommending a strike/expiry.
   - Skip expirations that encompass binary events (earnings) unless user explicitly accepts the risk.

 5. **PROBABILITY CHECK — never propose adjustment with <50% estimated success probability.**
   - For each proposed trade, check `max_profit_prob` from `analyze_options`.
   - If <50%, either widen the strike or skip the trade. Do not propose sub-coinflip trades.

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
