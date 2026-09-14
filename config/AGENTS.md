# Global Rules

## Multi-Agent Architecture
This OpenCode instance uses automatic model routing to save tokens:
- **Router (agent router)**: deepseek-v4.1-flash — receives all requests, classifies, delegates
- **@trade**: deepseek-v4-pro — trading, options, market analysis. Delega i task di codice e script personalizzati a @coder
- **@coder**: deepseek-v4.1-flash esecutore guidato da @coder_planner (glm-5.3) per decomposizione atomica — complex coding, refactoring, multi-file changes
- **@coder_planner**: glm-5.3 — definisce la lista di azioni atomiche per @coder (unico utilizzo consentito di GLM-5.3 per minimizzare i token)
- **@graphify_helper**: deepseek-v4-flash — smart graphify orchestrator, builds/updates/queries knowledge graphs
- **@skill_updater**: deepseek-v4-flash — updates skills that depend on -src submodules (graphify, book-to-skill, quant-mind, karpathy)
- **@explore / @scout**: deepseek-v4-flash — code search / web research

The router delegates based on keywords. Trading requests go to @trade, complex coding to @coder, skill updates to @skill_updater, graphify requests to @graphify_helper.
Every subagent MUST end its response with a `## VERIFICA` section (confidenza, evidenza, non_verificato, escalation_consigliata). The router interprets this to decide whether to retry, escalate, or ask the user for clarification.
The `verifica-gate` plugin appends each task's token saving (`📊 Token saving: ...`, from auto-headroom) as the last line of the `## VERIFICA` block and logs a `token_saving` event; run `/token-stats` for the aggregated headroom report.
All agents read these AGENTS.md rules. See opencode.json for full agent configuration.

## Python Virtual Environment Mandatory
CRITICAL: Before ANY Python operation (install, run, test), load @skills/python-venv. You MUST use a virtual environment. Never `pip install` on the system Python.
- Use a SINGLE shared venv at `/tmp/opencode/.venv` for all temporary NON-trading work. For trading/market-data Python work, REUSE the existing MCP trading venv at `~/.local/share/opencode/trading-mcp-venv` (it already has pandas, yfinance, lightgbm, scikit-learn — never reinstall). Never create duplicate venvs.

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

## Headroom Compression & Token Saving — AUTOMATIC & MANDATORY
CRITICAL: OpenCode uses automatic middleware token compression (`auto-headroom.js`).
Every tool output (bash, read, grep, glob, webfetch) ≥800 chars is AUTOMATICALLY compressed in-process before entering your context window, eliminating double-trip token ingestion penalties.

### Automated Middleware Flow & Selective Retrieval
1. **Automatic Ingestion**: When a tool result is ≥800 chars, `auto-headroom.js` saves the raw content into `~/.config/opencode/context-store/<hash>.txt` and generates `<hash>_index.json`.
2. **Context Delivery**: You receive a structured preview + reference hash (`hash=<hash>`).
3. **Selective Retrieval (Chunking)**: When you need detailed lines, numbers, or specific sections:
   - Use `/read-chunk <hash> --chunk <N>` or `/read-chunk <hash> --lines <start> <end>`.
   - Or use the `read` tool on `~/.config/opencode/context-store/<hash>.txt` ALWAYS specifying `start_line` and `end_line`.
   - Or use `headroom_retrieve(hash="<hash>")` for complete uncompressed retrieval.
4. **Prompt Caching**: Keep static rules, system instructions, and skill definitions intact at the top of your prompt context to maximize provider prefix caching hit rate (50-90% discount).

### Workflow rules — GOAL: maximize token savings
- **Quote hashes, not full content**: When referring to compressed data, reference the hash or chunk index, don't re-paste full raw output.
- **Selective Retrieval over full reads**: NEVER read an entire file in `context-store` without `start_line`/`end_line` parameters.
- **Check `headroom_stats`**: Run `headroom_stats` mid-session or end of session to audit compression metrics.

### Anti-patterns (forbidden)
- Re-pasting large uncompressed JSON, logs, or file contents into reasoning steps or prompts.
- Reading entire files from `context-store` without specifying line ranges.
- Bypassing automatic compression.

