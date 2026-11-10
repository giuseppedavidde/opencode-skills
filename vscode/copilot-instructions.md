# opencode-skills workflow in VS Code

This setup mirrors the opencode configuration from `{{OPENCODE_SKILLS}}`.
VS Code reads the generated VS Code-native layer:

| Primitive | Location |
|-----------|----------|
| Skills | `{{SKILLS_DIR}}/<name>/SKILL.md` |
| Agents | `{{AGENTS_DIR}}/*.agent.md` |
| Prompts | `{{PROMPTS_DIR}}/*.prompt.md` |
| Instructions | `{{INSTRUCTIONS_DIR}}/` |
| MCP servers | `{{MCP_FILE}}` |
| Hooks | `{{HOOKS_DIR}}/*.json` |

`.opencode/`, `config/opencode.json`, and `plugins/` are opencode-only: VS Code
does not read them. The files above are the VS Code equivalents.

## Delegation

Use the `agent` tool with these agent names:

| Agent | Use for |
|-------|---------|
| `trade` | Stocks, crypto, options, positions, risk, market scans |
| `coder` | Complex coding, refactors, multi-file changes, new features |
| `coder-planner` | Atomic step plans for `coder` (invoked by `coder`) |
| `graphify-helper` | Knowledge graphs, codebase maps, `graphify` queries |
| `skill-updater` | Updating skills that follow the `skill` + `-src` submodule pattern |
| `book-to-skill-agent` | Generating a skill from a book |
| `pdf-reader` | Any PDF, contract, invoice, policy, or scanned document |
| `oegk-health` | ÖGK coverage and personal cost for blood tests and specialist exams in Austria |

Rules:

- Trading requests always go to `trade`; do not improvise market analysis.
- Any attached PDF or document-analysis request goes to `pdf-reader`.
- ÖGK / Austrian health-insurance coverage questions go to `oegk-health`.
- Code/scripting requests from `trade` go to `coder`.
- `coder` delegates atomic planning to `coder-planner` for tasks touching
  **2+ files or more than 20 lines**.
- Graph requests go to `graphify-helper` even when they mention code.
- The PDF and graph categories win over trading/coding when the request is
  about reading a document or building/querying a graph.

Every subagent response must end with:

```markdown
## VERIFICA
- confidenza: <0-100>
- evidenza: <commands/files actually checked>
- non_verificato: <what was not checked>
- escalation_consigliata: <sì/no>
```

The `SubagentStop` hook in `{{HOOKS_DIR}}/verifica-gate.json` blocks a subagent
that omits this block and appends an audit event to
`~/.config/opencode/stats/gate_events.jsonl`.

## Writing directive (ASD-STE100)

Every agent writes all output text under ASD-STE100. The single source of truth
is `{{SKILLS_DIR}}/asd-ste100/SKILL.md`; read it when you write or review a long
report.

1. Maximum 20 words per sentence in a procedure. Maximum 25 words in a description.
2. One idea per sentence. One topic per paragraph, maximum 6 sentences.
3. Active voice. Simple tenses. Use `use`, `calculate`, `check`, `close`. Do not
   use `perform`, `provide`, `implement`.
4. Use one term for one concept in the whole answer.
5. Put procedures in numbered vertical lists. One action per step.
6. No idiom, no metaphor, no slang. No semicolon between two clauses.
7. Define each abbreviation at first use: `BE = break-even`.
8. Give exact numbers with units: `−$3,383.54`. Never "about three thousand".
9. The `## VERIFICA` block follows the same rules.

Code, tool output, tickers, paths, and quoted document text are exempt.

## Mandatory skills

- `asd-ste100` — the writing directive above; load it for the full rule set,
  checklist, and rewrite examples.
- `python-venv` — before **any** Python install, run, or test. Never
  `pip install` on the system Python. Use `/tmp/opencode/.venv` for temporary
  non-trading work and reuse `~/.local/share/opencode/trading-mcp-venv` for
  trading (pandas, yfinance, lightgbm, scikit-learn are already installed).
  Never create duplicate venvs.
- `python-pydantic` — Pydantic models for structured data, type hints
  everywhere, PEP 8, and `pylint` before proposing Python code.
- `graphify` — build or query `graphify-out/`; query the graph instead of
  grepping large codebases.
- Trading: `market-accumulation-scanner`, `stock-crypto-analysis`,
  `options-analysis`, `options-strategy-suggestions`, `market-data-fetch`.
- Documents: `pdf-ingest`, `pdf-compress`.

Load a skill by reading `{{SKILLS_DIR}}/<name>/SKILL.md` or by typing
`/<skill-name>` in chat.

## Token discipline

- Do not re-paste large tool outputs, logs, or JSON into reasoning or prompts.
- Use targeted reads with line ranges.
- If the `headroom` MCP server is available, use its `headroom/*` tools to
  retrieve compressed content by hash.
- `/read-chunk` retrieves a chunk or a line range from a headroom
  context-store hash.
- `/routing-stats` and `/token-stats` read telemetry written by the opencode
  runtime; they print `MANCANTE` when opencode has not produced data.

## Runtime differences from opencode

- `auto-headroom` (automatic compression of every tool output) does not exist
  in VS Code. Use the `headroom` MCP server and `/read-chunk` instead.
- `verifica-gate` is approximated by the `SubagentStop` hook (audit + block).
- The `graphify` reminder is approximated by the `PreToolUse` hook.
- `routing-stats` and `tokens-per-second` plugins do not run in VS Code; their
  reports only cover opencode sessions.
- `permission`, `steps`, and `hidden` are opencode-only frontmatter keys. Tool
  access in VS Code is restricted by the `tools` list of each agent.
