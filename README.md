# opencode-skills

Custom skills and configuration for [opencode](https://opencode.ai).

## Structure

```
opencode-skills/
├── install.sh                  # Single installer: opencode + VS Code (run this one)
├── install.py                  # Compatibility wrapper: runs install.sh
├── install-vscode.py           # VS Code layer generator (install.sh calls it)
├── vscode/                     # VS Code templates, hooks, models.json, tests, docs
├── config/
│   ├── AGENTS.md               # Global rules referencing skills
│   ├── opencode.json           # Provider/model/MCP configuration
│   ├── bin/
│   │   └── rea-mcp.sh          # Wrapper MCP rea (build on-change del repo rea locale)
│   └── secrets.env.enc         # Encrypted API keys (decrypt with scripts/decrypt_secrets.sh)
├── agents/                     # Agent definitions (router, trade, coder, ...)
│   ├── router.md
│   ├── trade.md
│   ├── coder.md
│   ├── graphify_helper.md
│   ├── skill_updater.md
│   └── book-to-skill-agent.md
├── command/                    # Slash commands
│   └── routing-stats.md        # Routing telemetry /routing-stats
├── plugins/                    # Plugin V2 (dichiarati in opencode.json → "plugins")
│   ├── graphify.js
│   ├── tokens-per-second.js
│   ├── routing-stats.js
│   ├── verifica-gate.js        # enforce ## VERIFICA; writes write-only audit trail
│   └── context-store.js
├── scripts/
│   ├── alphavantage-mcp.sh     # Alpha Vantage MCP bootstrap
│   └── decrypt_secrets.sh      # Decrypt secrets.env.enc → API keys
├── mcp/                        # Trading MCP server (pip install -e)
├── routing-eval/               # Router evaluation harness (telemetria /routing-stats)
├── skills/                     # Skill definitions (49, see below)
├── setup-headroom.sh           # Install headroom in venv
├── setup-trading-mcp.sh        # Install trading-mcp in venv
├── setup-rea-mcp.sh            # Clone + build the local rea repo (rea MCP)
└── setup-bladebro.sh           # Install bladebro (stealth browser) + Chrome link
```

## Install on a new machine

### Prerequisites

- git, bash, python3 (3.10+ with the `venv` module)
- the [opencode](https://opencode.ai) CLI and/or VS Code 1.146+ with GitHub Copilot
- Node.js >= 22 (`^22.23.4 || ^24.22.1 || >=26.12.1`) **only for the `rea` MCP**
  — rea lives in a **separate** repo ([morluto/rea](https://github.com/morluto/rea)),
  cloned by `./setup-rea-mcp.sh` into the folder `rea` next to this repository
  (override with `$REA_REPO` or with a path as first argument)
- Chrome/Chromium **only for the optional `./setup-bladebro.sh`** (bladebro is
  not in `config/opencode.json`)

### 1. Clone and install (one command)

```bash
git clone --recursive https://github.com/giuseppedavidde/opencode-skills.git
cd opencode-skills
./install.sh
```

The installer is idempotent. Run `./install.sh` again after a `git pull` or
after you move the repository. `python3 install.py` runs the same installer.

| Step | Result |
|------|--------|
| Submodules | `git submodule update --init --recursive` when a submodule is empty |
| opencode layer | links in `~/.config/opencode/`: `skills`, `agents/*`, `command/*`, `AGENTS.md`, `opencode.json`, `bin/*`, `scripts/*`, `routing-eval`, and the anchor `opencode-skills` → this repository |
| MCP runtimes | `./setup-headroom.sh` and `./setup-trading-mcp.sh` (skip with `--no-mcp`) |
| VS Code layer | `install-vscode.py --target user` → `~/.copilot/` (skip with `--no-vscode`) |

```bash
./install.sh --dry-run          # print the plan, change nothing
./install.sh --force            # replace real files that are in the way (backup first)
./install.sh --no-mcp           # links + VS Code layer only
./install.sh --with-rea         # also the rea MCP (Node.js, separate repo)
./install.sh --with-systemd     # regenerate the VS Code layer after each edit
./install.sh --yes              # no questions (CI)
```

No file of the repository contains a machine path. `config/opencode.json` uses
`{env:HOME}` placeholders and reaches the plugins through the anchor link
`~/.config/opencode/opencode-skills`. The installer never rewrites a tracked
file. A real file that is in the way stays in place; with `--force` it goes to
`~/.cache/opencode-skills/backup/<timestamp>/` first.

### 2. Steps that need you

1. Log in to the opencode provider once per machine: `opencode auth login`.
2. API keys, only for the skills that use them (see "API keys & secrets").
3. VS Code: install the extension **OpenCode Go Provider for Copilot**
   (`OnesoftQwQ.opencode-go-copilot-provider`) and run
   `OpenCodeGo: Set OpenCode Go API Key`. The agents use the OpenCode Go models
   `opencodego/<id>`, with the fallbacks of
   [`vscode/models.json`](vscode/models.json) (model ids of the
   [OpenCode Go API](https://opencode.ai/console/go#api)).
4. Restart opencode. In VS Code, start a **new** chat session.

### 3. Headroom (token compression)

```bash
./setup-headroom.sh
```

Creates `~/.local/share/opencode/headroom-venv/`, installs `headroom-ai[mcp]==0.27.0`,
and applies the required opencode patch (`scripts/patches/headroom-0.27.0-opencode.patch`)
idempotently (fixed retrieve fallback, store format v2, coherent stats). `opencode.json`
is pre-configured with the MCP command
(`$HOME/.local/share/opencode/headroom-venv/bin/headroom`).

> After any manual `headroom` upgrade, re-run `./setup-headroom.sh` to re-apply the patch.

### 4. Trading MCP (market analysis)

```bash
./setup-trading-mcp.sh
```

Creates `~/.local/share/opencode/trading-mcp-venv/`, installs the MCP server
from `mcp/` in editable mode. Pre-configured in `opencode.json`.

### 5. rea MCP (reverse engineering / app analysis)

```bash
./setup-rea-mcp.sh                  # default: the folder `rea` next to this repository
REA_REPO=/path/to/rea ./setup-rea-mcp.sh   # an existing checkout in a different folder
```

`./install.sh --with-rea` runs this script. For a checkout in a different
folder, also export `REA_REPO` in the environment of opencode and VS Code: the
wrapper and the VS Code installer look for the `rea` folder next to this
repository when `REA_REPO` is not set.

Clones [morluto/rea](https://github.com/morluto/rea) if missing, installs deps
(`npm ci`), builds it (`npm run build`) and validates the wrapper
`config/bin/rea-mcp.sh` (`--check`). The wrapper is symlinked into
`~/.config/opencode/bin/rea-mcp.sh` by the installer and is declared in
`opencode.json` as `bash -c 'exec "$HOME/.config/opencode/bin/rea-mcp.sh"'`, so it
is the single source of truth and survives moving either repo. It rebuilds
automatically only when the rea `HEAD` or its tracked working tree changes
(log: `~/.cache/rea-mcp/build.log`).

### 6. Bladebro MCP (stealth browser, optional)

`config/opencode.json` does not contain a bladebro server (the skills use
`reddit_client.py`), and `./install.sh` does not install it. To use bladebro,
run the script and add the MCP entry yourself.

```bash
./setup-bladebro.sh
```

Installs `bladebro` via `npm` into the canonical dir
`~/.local/share/opencode/bladebro-node/` and creates a **stable symlink**
`~/.local/share/opencode/bladebro-node/chrome` pointing to the detected
Chrome/Chromium binary (env `CHROME_PATH` → `PATH` → newest Playwright cache).
Use `CHROME_PATH="$HOME/.local/share/opencode/bladebro-node/chrome"` in the MCP
entry, so it survives Playwright upgrades. Re-run idempotently after
installing/upgrading Chrome.

### 6b. browse MCP (your real browser, optional)

`config/opencode.json` starts [browse](https://github.com/anomalyco/browse)
from `~/.local/bin/browse`. Install it once per machine, then rerun
`./install.sh` (the VS Code layer adds the server only when the binary exists):

```bash
curl -fsSL https://opencode.ai/browse/install | bash
```

`browse install` can edit `~/.config/opencode/opencode.json`, which is the
tracked `config/opencode.json`. Run `git diff config/opencode.json` after the
install, and keep the `{env:HOME}` form of the entry.

### 7. API keys & secrets

```bash
# Alpha Vantage (required for the alphavantage MCP)
echo 'YOUR_KEY' > ~/.config/opencode/alpha_vantage_key.txt
# or: export ALPHA_VANTAGE_API_KEY='YOUR_KEY'

# FMP (for LGBM trader / fundamental data)
echo 'YOUR_FMP_KEY' > ~/.config/opencode/fmp_api_key.txt

# Decrypt the bundled secrets file (FMP, etc.)
./scripts/decrypt_secrets.sh
```

### 8. Restart opencode

Quit and restart opencode for the new config, agents, commands, plugins and
MCP servers to take effect.

### 9. Optional: routing-stats

The `/routing-stats` slash command uses `routing-eval/`, which is now bundled in
this repo and installed automatically as a symlink to
`~/.config/opencode/routing-eval/`. No separate clone needed.

The command needs `pydantic` in the command venv:

```bash
/tmp/opencode/.venv/bin/pip install -r routing-eval/requirements.txt
```

## VS Code (Copilot harness)

`./install.sh` also generates the VS Code layer at user scope (`~/.copilot/`),
so every workspace sees it. opencode stays the source of truth:

```bash
python3 install-vscode.py --target user            # done by ./install.sh
python3 install-vscode.py --verify --target user   # exit 1 = drift
python3 install-vscode.py --target user --dry-run -v
python3 install-vscode.py --workspace /path/to/ws  # one workspace instead
python3 install-vscode.py --target user --workspace /path/to/ws  # also migrate its legacy .vscode/mcp.json
```

The installer migrates the MCP servers that `config/opencode.json` owns from the
legacy VS Code files (`.vscode/mcp.json` and the user `mcp.json`) to
`~/.copilot/mcp-config.json` and the workspace root `.mcp.json`. Use
`--no-migrate-mcp` to keep the legacy files unchanged.

| opencode | VS Code (user scope) |
|----------|---------|
| `skills/<name>/SKILL.md` | `~/.copilot/skills/<name>` (symlink) |
| `agents/<name>.md` | `~/.copilot/agents/<name>.agent.md` |
| `command/<name>.md` | `~/.copilot/skills/<name>/SKILL.md` (slash-only skill: `/read-chunk`) |
| `config/AGENTS.md` | `~/.copilot/copilot-instructions.md` |
| `config/opencode.json` → `mcp` | `~/.copilot/mcp-config.json` |
| `plugins/verifica-gate` | `~/.copilot/hooks/verifica-gate.json` (`SubagentStop`) |
| `plugins/graphify` | `~/.copilot/hooks/graphify-reminder.json` (`SessionStart`) |

> Use **one** scope. The user folder and a workspace `.github/` are both native
> Copilot sources, so a second copy loads every agent, skill, and hook two times.

See [`vscode/README.md`](vscode/README.md) for the model fallbacks, the
delegation rules (a subagent cannot start a subagent in VS Code), the hooks, and
the limitations. Start a **new chat** after installing so VS Code discovers the
new skills and agents.

## Writing directive — ASD-STE100

Every agent writes its output text under ASD-STE100 (Simplified Technical
English). The single source of truth is the `asd-ste100` skill:

| Layer | File | Role |
|---|---|---|
| Canonical rule set | `skills/asd-ste100/SKILL.md` | Full directive, checklist, rewrite examples, per-agent matrix |
| Agent enforcement | `agents/*.md` | Mandatory 9-point block in every agent |
| Global rule | `config/AGENTS.md` | Applies to all agents and to the VS Code generated instructions |
| Trade diagrams | `skills/interactive-trade-diagram/SKILL.md` | Diagram text follows the same directive |

Hard limits:

1. Maximum 20 words per sentence in a procedure. Maximum 25 words in a description.
2. One idea per sentence. One topic per paragraph, maximum 6 sentences.
3. Active voice. Simple tenses. One term for one concept in the whole answer.
4. Procedures go in numbered vertical lists, one action per step.
5. Exact numbers with units. No idiom, no metaphor, no slang.

Exempt: code, tool output, JSON, tickers, paths, and quoted document text.

```bash
# Load the full directive in a session
skill asd-ste100        # opencode
/asd-ste100             # VS Code Copilot Chat
```

The directive propagates to the VS Code layer automatically: `install-vscode.py`
symlinks the skill into `.github/skills/asd-ste100/` and embeds the agent block
in the generated `.agent.md` files.

### Conformance test

`scripts/ste_conformance.py` checks the wiring and the text.

```bash
# Wiring: every agent carries the directive, the skill exists, VS Code is linked
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py --wiring

# Built-in fixtures: 22 positive and negative cases
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py --self-test

# Lint real output (a directory expands to *.md, *.html, *.txt)
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py trades/

# Machine-readable report, strict mode, or summary only
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py trades/ --json /tmp/ste.json
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py trades/ --strict
/tmp/opencode/.venv/bin/python scripts/ste_conformance.py trades/ --no-warn
```

| Rule | Check | Severity |
|---|---|---|
| `R1` | Sentence: max 20 words (procedure) / 25 (description) | FAIL |
| `R2` | Paragraph: max 6 sentences | FAIL |
| `R3` | Active voice | WARN |
| `R4` | Forbidden verb: `effettuare`, `provvedere`, `eseguire la verifica` | FAIL |
| `R5` | Forbidden connective: `al fine di`, `in merito a`, `qualora` | FAIL |
| `R6` | Idiom, metaphor, slang | FAIL |
| `R7` | Semicolon between clauses | FAIL |
| `R8` | Contraction | FAIL |
| `R9` | Abbreviation defined at first use | WARN |
| `R10` | Vague quantity: `circa`, `alcuni`, `molti` | WARN |
| `R11` | Emphatic adverb or adjective | WARN |
| `W1`–`W7` | Wiring: skill, agent blocks, global rules, VS Code layer, permissions | FAIL |

A numbered or bulleted item counts as a procedure only when it starts with an
imperative verb (`verifica`, `calcola`, `chiudi`, ...). Other bullets use the
descriptive limit. Code fences, inline code, quoted lines, and table cells are
exempt from the sentence and punctuation rules.

Exit code is `0` when the target is conform. Exit code is `1` on any FAIL.
`--strict` makes WARN findings fail too.

## Portability Notes

- **No machine paths** — `config/opencode.json` uses `{env:HOME}` placeholders,
  which opencode resolves at load time. The `headroom` and `rea` commands run
  through `bash -c`, so the shell expands `$HOME`. A test
  (`vscode/tests/test_install_vscode.py`) fails when a runtime source contains
  `/home/...` or a `Progetti` path.
- **Anchor link** — `./install.sh` creates `~/.config/opencode/opencode-skills` →
  this repository. The plugin entries, the commands, the agents, the systemd
  units and the trade-assistant extension reach the repository through it, so
  the clone can live in any folder. Move the repository, then rerun `./install.sh`.
- **MCP runtimes** — the setup scripts create the runtimes outside the repository:
  - `./setup-headroom.sh` → `~/.local/share/opencode/headroom-venv`
  - `./setup-trading-mcp.sh` → `~/.local/share/opencode/trading-mcp-venv`
  - `./setup-rea-mcp.sh` → clones/builds the separate `rea` repo next to this one
    and validates `config/bin/rea-mcp.sh` (linked to `~/.config/opencode/bin/rea-mcp.sh`)
  - `./setup-bladebro.sh` → `~/.local/share/opencode/bladebro-node`
- **Plugins (API V2)** — `config/opencode.json` → `plugins` lists the 5 plugin
  folders through the anchor link. The installer does not rewrite this file.
- **Data files** — `trade_log.jsonl` and `pump_history.jsonl` go to
  `$OPENCODE_SKILLS_DATA_DIR`, else to `~/Progetti/Github/Data_for_Analysis`
  when that folder exists, else to `~/.local/share/opencode-skills/`.
- **`verifica-gate` audit trail** — `plugins/verifica-gate/index.js` appends one JSON
  line per flagged subagent result to
  `~/.config/opencode/stats/gate_events.jsonl` (write-only, no reader by
  design; forensic log for post-hoc inspection only). Exit-code anchoring is
  **per task and last-outcome-wins**: a transient verification failure followed
  by a successful re-run of the same command does not anchor confidence, and
  inline exploration snippets (`python3 -c`, heredoc) are never anchorable.

- **Secrets** — never committed. `config/secrets.env.enc` is the encrypted
  bundle; decrypt it with `scripts/decrypt_secrets.sh` using the shared
  passphrase.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Symlinks broken after moving the repo | `./install.sh` (repairs the links; real files stay unless `--force`) |
| Plugins not loading after restart | `ls ~/.config/opencode/opencode-skills/plugins` must list 5 folders; else rerun `./install.sh` |
| MCP servers fail (`exec: ... not found`) | Run `./setup-headroom.sh` and/or `./setup-trading-mcp.sh` |
| `rea` MCP fails / `dist` missing / `npm` errors | Run `./setup-rea-mcp.sh` (clone + `npm ci` + `npm run build` + `--check`); verify `node --version` >= 22 |
| MCP `rea` serves old code | It rebuilds on `HEAD`/dirty change; check `~/.cache/rea-mcp/build.log`, or force with `REA_MCP_SKIP_BUILD=0` (set `=1` to serve the existing `dist` without rebuilding) |
| `rea` log says `Direct dependency installation is stale` | The checkout moved ahead of its `node_modules`; run `npm ci` in the `rea` folder, then start the server again |
| `pylance mcp server` fails with `transport failure ... http://localhost:<port>/stream` | VS Code froze an old Pylance port in an agent-host snapshot; run `scripts/vscode-mcp-clean.py` (close VS Code first) |
| bladebro MCP fails (`Could not launch Chrome`) | Run `./setup-bladebro.sh` (or ensure Chrome/Chromium is installed) |
| Submodule folders empty | `./install.sh` (it runs `git submodule update --init --recursive`) |
| `alphavantage-mcp.sh: command not found` | Ensure `~/.local/bin` is in `$PATH` |
| `routing-stats` shows "not found" | Rerun `./install.sh`; verify `pip install -r routing-eval/requirements.txt` |
| VS Code shows an agent or skill two times | Keep one scope: remove the workspace `.github/` copy or the `~/.copilot` copy |
| VS Code agents ignore new edits | Start a new chat session; with `--with-systemd` the layer regenerates on save |

## Venv & Recovery

Mappa dei virtual environment usati dal repo (nessun venv è committato: i
`.venv/` locali sono gitignored):

| Venv | Creato da | Scopo |
|------|-----------|-------|
| `~/.local/share/opencode/trading-mcp-venv` | `./setup-trading-mcp.sh` | Trading MCP server (pandas, numpy, scipy, yfinance; no machine-learning packages) |
| `~/.local/share/opencode/headroom-venv` | `./setup-headroom.sh` | Tool headroom (compressione token) |
| `~/.local/share/opencode/bladebro-node` | `./setup-bladebro.sh` | Bladebro MCP server (browser stealth, Node/npm) + symlink `chrome` |
| `/tmp/opencode/.venv` | manuale | Venv condiviso temporaneo per lavoro NON-trading (routing-eval, script generici) |

Ricreazione del venv temporaneo condiviso:

```bash
python3 -m venv /tmp/opencode/.venv && /tmp/opencode/.venv/bin/pip install -r routing-eval/requirements.txt
```

Dipendenze note del venv temporaneo: `pydantic>=2.0` (routing-eval). Per il
resto, installa le dipendenze del lavoro corrente con `pip install` nel venv.

Per ricreare un venv canonico, rimuovilo e rilancia lo script relativo:

```bash
rm -rf ~/.local/share/opencode/trading-mcp-venv && ./setup-trading-mcp.sh
rm -rf ~/.local/share/opencode/headroom-venv && ./setup-headroom.sh
rm -rf ~/.local/share/opencode/bladebro-node && ./setup-bladebro.sh
```

## Contents

| Skill | Description |
| ----- | ----------- |
| `advances-in-financial-machine-learning` | Knowledge base from 'Advances in Financial Machine Learning' by Marcos M. López de Prado |
| `asd-ste100` | ASD-STE100 (Simplified Technical English) writing directive shared by every agent: sentence limits, active voice, simple tenses, one term per concept, vertical lists, exact numbers |
| `asset-management-factor-investing` | Knowledge base from 'Asset Management: A Systematic Approach to Factor Investing' by Andrew Ang |
| `async-python-patterns` | Implementing asynchronous Python applications using asyncio, concurrent programming, and async/await |
| `book-to-skill` | Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, etc.) into structured agent skills |
| `book-to-skill-bridge` | Auto-generates agent skills from books/documents without interactive prompts |
| `consulting-writing` | Management-consulting writing craft — McKinsey SCR (Situation·Complication·Resolution), Minto Pyramid/MECE, BCG bold-bullet executive summary, so-what upfront, numeric precision, Forrester Landscape |
| `crypto-crash-course` | Knowledge base from 'The Crypto Crash Course' by Frank Richmond (cryptocurrency, blockchain) |
| `crypto-technical-analysis` | Knowledge base from 'Crypto Technical Analysis' by Alan John & Jon Law (TA adapted for crypto) |
| `encyclopedia-writing` | Encyclopedic neutral-reference writing craft — NPOV (attribute facts not opinions, due weight, neutral faction labels, verdict restraint), summary style and Coatrack avoidance, wikilink conventions (link density, first-mention, slug alias, abbreviation glossing) |
| `evidence-based-technical-analysis` | Knowledge base from 'Evidence-Based Technical Analysis' by David R. Aronson (scientific method for trading signals) |
| `graphify` | any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report |
| `journalism-writing` | Journalism and argumentation writing craft — inverted pyramid, lede, nut graph, kicker, explainer framing, PAGE frames, Toulmin argument (claim/rebuttal/qualifier), Hegelian dialectic, BBC due impartiality |
| `karpathy-llm-wiki` | Build and maintain a personal LLM-powered knowledge base |
| `liotta-smartfood` | Knowledge base from 'Le Ricette Smartfood' by Eliana Liotta & Lucilla Titta (nutrigenomics nutrition) |
| `machine-learning-for-asset-managers` | Knowledge base from 'Machine Learning for Asset Managers' by Marcos M. López de Prado |
| `market-accumulation-scanner` | Scans stock/crypto markets for accumulation patterns via trading MCP |
| `market-data-fetch` | Standardized templates for fetching stock, ETF, and crypto market data using yfinance, CoinGecko, and Bitpanda |
| `opencode-skills-installer` | Manages the opencode-skills GitHub repository where all skills live and are version-controlled |
| `option-volatility-pricing` | Knowledge base from 'Option Volatility and Pricing' by Sheldon Natenberg (2nd Edition) |
| `options-analysis` | Analyze multi-leg options positions with Greeks, payoff scenarios, and recommendations |
| `options-course-workbook` | Knowledge base from 'The Options Course Workbook' by George A. Fontanills (exercises and applications) |
| `options-crash-course` | Knowledge base from 'Options Trading Crash Course' by Mark Elder and Brian Douglas (options trading) |
| `options-playbook` | Knowledge base from 'The Options Playbook' by Brian Overby (40+ options strategies) |
| `options-strategy-suggestions` | Suggests an options strategy from stock analysis verdict + IV regime |
| `pdf-compress` | Reduces the size of PDF files with a Python script (PyMuPDF): presets, batches, encrypted files, JSON report |
| `pdf-ingest` | PDF extraction helper for both Karpathy LLM Wiki and Graphify workflows |
| `ponytail-coding` | Forces the laziest solution that actually works, simplest, shortest, most minimal — YAGNI, standard library before custom code, native platform features before dependencies, one line before fifty |
| `position-management-playbook` | Active management of difficult positions: exit ladder, rolling, downside protection, documentary discipline |
| `price-action-volman` | Knowledge base from 'Understanding Price Action' by Bob Volman (price action frameworks) |
| `python-pydantic` | Python coding standards with Pydantic data models, type hints, and pylint compliance |
| `python-venv` | Enforces the mandatory use of Python virtual environments (venv) for all Python projects |
| `quant-mind-skill` | QuantMind integration — knowledge extraction and retrieval for quantitative finance (arXiv, news, PDF) |
| `scholarly-citation` | Verifiable-attribution and citation-discipline craft — atomic claim decomposition, evidence grading (primary/analysis/forecast tiers), claimant attribution, citation typing (cites/references/contradicts/defines), source anchoring (Xanadu) |
| `smart-dispatcher` | Auto-dispatcher that translates natural language requests into parallel orchestration via subatomic-orchestrator |
| `stock-crypto-analysis` | Deep single-stock/crypto analysis via trading MCP, enriched with Bali & Hovakimian volatility-spread signals |
| `subatomic-orchestrator` | Meta-skill that decomposes workloads into independent sub-tasks and dispatches them to parallel agents |
| `system-info` | Gather detailed machine information to make correct build decisions (OS, hardware, toolchains) |
| `trades-about-to-happen` | Knowledge base from 'Trades About to Happen' by David Weis (tape reading, order flow) |
| `trading-against-the-crowd` | Knowledge base from 'Trading Against the Crowd' by John F. Summa (contrarian trading frameworks) |
| `trading-in-the-zone` | Knowledge base from 'Trading in the Zone' by Mark Douglas (trading psychology and discipline) |
| `volume-price-analysis` | Knowledge base from 'A Complete Guide To Volume Price Analysis' by Anna Coulling |
| `volume-profile` | Knowledge base from 'VOLUME PROFILE' by Trader Dale (volume profile frameworks for institutional trading) |
| `wallstreetbets-pump-detect` | Scrapes r/wallstreetbets public JSON to detect pumped stocks/ETFs and score hype/squeeze potential |
| `way-of-the-turtle` | Knowledge base from 'Way of the Turtle' by Curtis M. Faith (systematic trend following, position sizing) |
| `wyckoff-2-0` | Knowledge base from 'Wyckoff 2.0' by Rubén Villahermosa Chaves (volume profile, order flow, Wyckoff Method) |
| `config/AGENTS.md` | Global rules that load skills automatically + headroom compression mandatory |
| `config/opencode.json` | Provider/model configuration + MCP servers (headroom, trading, rea, browse); portable `{env:HOME}` paths |
| `config/bin/rea-mcp.sh` | Wrapper MCP `rea`: serves the local rea repo, rebuilds only on HEAD/dirty change (`REA_REPO`, `REA_MCP_SKIP_BUILD`, `--check`) |
| `setup-headroom.sh` | Installs headroom in a dedicated venv for token compression (60-95% savings) |
| `setup-rea-mcp.sh` | Clones + builds the separate [rea](https://github.com/morluto/rea) repo and validates the `rea` MCP wrapper |
| `setup-bladebro.sh` | Installs bladebro (stealth browser MCP) into `~/.local/share/opencode/bladebro-node` and links Chrome |
| `install-vscode.py` | Generates the VS Code layer (skill links, agents, command skills, MCP, hooks); `install.sh` runs it |
| `scripts/ste_conformance.py` | ASD-STE100 conformance test: wiring check, text lint, self-test fixtures |
| `vscode/` | VS Code-native templates: `copilot-instructions.md`, Python instructions, verifica-gate / graphify hooks, docs |

## Requires

- [opencode](https://opencode.ai) CLI installed (for the opencode layer)
- bash, git, Python 3.10+ (for `install.sh`, `install-vscode.py` and the MCP venvs)
- VS Code 1.146+ with GitHub Copilot, Copilot harness (only for the VS Code layer)

## Prerequisites per skill

### pdf-compress

Requires Python 3.10+ and a virtual environment with PyMuPDF and Pydantic:

```bash
mkdir -p /tmp/opencode
python3 -m venv /tmp/opencode/.venv
/tmp/opencode/.venv/bin/pip install -r skills/pdf-compress/requirements.txt
```

The script needs no external binary. It uses PyMuPDF for image rewriting,
font subsetting, object streams, and stream deflate.

### pdf-ingest

Requires `tesseract` installed system-wide:

- **Arch Linux:** `paru -S tesseract tesseract-data-eng tesseract-data-ita`

Requires a Python virtual environment inside your wiki root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` is provided in the wiki root — see [Comm_Prot_Wiki](https://github.com/giuseppedavidde/opencode-skills) or create one with:

```
pdfplumber>=0.11
pymupdf>=1.24
Pillow>=10.0
pytesseract>=0.3
pydantic>=2.0
```
