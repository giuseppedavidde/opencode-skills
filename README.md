# opencode-skills

Custom skills and configuration for [opencode](https://opencode.ai).

## Structure

```
opencode-skills/
├── install.py                  # Python install script (recommended)
├── install.sh                  # Shell install script (quick alternative)
├── config/
│   ├── AGENTS.md               # Global rules referencing skills
│   ├── opencode.json           # Provider/model/MCP configuration
│   └── secrets.env.enc         # Encrypted API keys (decrypt with scripts/decrypt_secrets.sh)
├── agents/                     # Agent definitions (router, trade, coder, ...)
│   ├── router.md
│   ├── trade.md
│   ├── coder.md
│   ├── general.md
│   ├── graphify_helper.md
│   ├── skill_updater.md
│   └── book-to-skill-agent.md
├── command/                    # Slash commands
│   └── routing-stats.md        # Routing telemetry /routing-stats
├── plugins/                    # Auto-discovery plugins (.opencode/plugins/)
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
├── skills/                     # Skill definitions (41, see below)
├── setup-headroom.sh           # Install headroom in venv
└── setup-trading-mcp.sh        # Install trading-mcp in venv
```

## Portable Install (Full Flow)

### Prerequisites

- git, python3, opencode CLI installed
- Node.js 18+ (optional — for plugin runtime via `@opencode-ai/plugin`)

### 1. Clone the repo

```bash
git clone https://github.com/giuseppedavidde/opencode-skills.git
cd opencode-skills
git submodule update --init --recursive
```

### 2. Install

**Python (recommended):**
```bash
python3 install.py              # install all, skip existing
python3 install.py --force      # overwrite existing symlinks
python3 install.py --dry-run    # preview without changes
python3 install.py -v           # verbose output
```

**Shell (quick):**
```bash
./install.sh                    # install all, skip existing
./install.sh --force            # overwrite existing symlinks
```

What gets installed:

| Category   | Source         | Destination                           |
|------------|----------------|---------------------------------------|
| skills     | `skills/`      | `~/.config/opencode/skills/`          |
| agents     | `agents/`      | `~/.config/opencode/agents/`          |
| commands   | `command/`     | `~/.config/opencode/command/`         |
| plugins    | `plugins/`     | `~/.config/opencode/.opencode/plugins/` |
| config     | `config/`      | `~/.config/opencode/` (symlinked)     |
| routing-eval | `routing-eval/` | `~/.config/opencode/routing-eval` (symlinked) |
| alphavantage | `scripts/`   | `~/.local/bin/alphavantage-mcp.sh`    |

All items are symlinked — changes to the repo propagate immediately. The only
exception is `alphavantage-mcp.sh` which is also symlinked into
`~/.local/bin/`.  Plugins use **auto-discovery** via `.opencode/plugins/`
(no `file://` paths in `opencode.json`).

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

### 5. API keys & secrets

```bash
# Alpha Vantage (required for the alphavantage MCP)
echo 'YOUR_KEY' > ~/.config/opencode/alpha_vantage_key.txt
# or: export ALPHA_VANTAGE_API_KEY='YOUR_KEY'

# FMP (for LGBM trader / fundamental data)
echo 'YOUR_FMP_KEY' > ~/.config/opencode/fmp_api_key.txt

# Decrypt the bundled secrets file (FMP, etc.)
./scripts/decrypt_secrets.sh
```

### 6. Restart opencode

Quit and restart opencode for the new config, agents, commands, plugins and
MCP servers to take effect.

### 7. Optional: routing-stats

The `/routing-stats` slash command uses `routing-eval/`, which is now bundled in
this repo and installed automatically as a symlink to
`~/.config/opencode/routing-eval/`. No separate clone needed.

The command needs `pydantic` in the command venv:

```bash
/tmp/opencode/.venv/bin/pip install -r routing-eval/requirements.txt
```

## Portability Notes

- **`$HOME` expansion** — all MCP commands use `$HOME/.local/...` and are
  resolved at runtime by the shell. No manual path edits needed.
- **Plugins auto-discovery** — plugins are loaded from
  `{config}/.opencode/plugins/` (no machine-specific `file://` URLs).
- **`verifica-gate` audit trail** — `plugins/verifica-gate.js` appends one JSON
  line per flagged subagent result to
  `~/.config/opencode/stats/gate_events.jsonl` (write-only, no reader by
  design; forensic log for post-hoc inspection only).
- **LGBM artifacts** — `skills/lgbm-trader-skill/models/`, `weights.json`,
  `predictions/`, `calibrations/` are runtime artefacts regenerated by training.
- **Secrets** — never committed. `config/secrets.env.enc` is the encrypted
  bundle; decrypt it with `scripts/decrypt_secrets.sh` using the shared
  passphrase.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Symlinks broken after moving the repo | `python3 install.py` (ripara i symlink rotti in sicurezza, senza `--force`) |
| Plugins not loading after restart | Check `~/.config/opencode/.opencode/plugins/` has 5 symlinks |
| MCP servers fail (`exec: ... not found`) | Run `./setup-headroom.sh` and/or `./setup-trading-mcp.sh` |
| Submodule folders empty | `git submodule update --init --recursive` |
| `alphavantage-mcp.sh: command not found` | Ensure `~/.local/bin` is in `$PATH` |
| `routing-stats` shows "not found" | Rilancia `python3 install.py` per ricreare il symlink; verifica `pip install -r routing-eval/requirements.txt` |

## Venv & Recovery

Mappa dei virtual environment usati dal repo (nessun venv è committato: i
`.venv/` locali sono gitignored):

| Venv | Creato da | Scopo |
|------|-----------|-------|
| `~/.local/share/opencode/trading-mcp-venv` | `./setup-trading-mcp.sh` | Trading MCP server (pandas, yfinance, lightgbm, scikit-learn) |
| `~/.local/share/opencode/headroom-venv` | `./setup-headroom.sh` | Tool headroom (compressione token) |
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
```

## Contents

| Skill | Description |
| ----- | ----------- |
| `advances-in-financial-machine-learning` | Knowledge base from 'Advances in Financial Machine Learning' by Marcos M. López de Prado |
| `asset-management-factor-investing` | Knowledge base from 'Asset Management: A Systematic Approach to Factor Investing' by Andrew Ang |
| `async-python-patterns` | Implementing asynchronous Python applications using asyncio, concurrent programming, and async/await |
| `book-to-skill` | Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, etc.) into structured agent skills |
| `book-to-skill-bridge` | Auto-generates OpenCode skills from books/documents without interactive prompts |
| `consulting-writing` | Management-consulting writing craft — McKinsey SCR (Situation·Complication·Resolution), Minto Pyramid/MECE, BCG bold-bullet executive summary, so-what upfront, numeric precision, Forrester Landscape |
| `crypto-crash-course` | Knowledge base from 'The Crypto Crash Course' by Frank Richmond (cryptocurrency, blockchain) |
| `crypto-technical-analysis` | Knowledge base from 'Crypto Technical Analysis' by Alan John & Jon Law (TA adapted for crypto) |
| `encyclopedia-writing` | Encyclopedic neutral-reference writing craft — NPOV (attribute facts not opinions, due weight, neutral faction labels, verdict restraint), summary style and Coatrack avoidance, wikilink conventions (link density, first-mention, slug alias, abbreviation glossing) |
| `evidence-based-technical-analysis` | Knowledge base from 'Evidence-Based Technical Analysis' by David R. Aronson (scientific method for trading signals) |
| `graphify` | any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report |
| `journalism-writing` | Journalism and argumentation writing craft — inverted pyramid, lede, nut graph, kicker, explainer framing, PAGE frames, Toulmin argument (claim/rebuttal/qualifier), Hegelian dialectic, BBC due impartiality |
| `karpathy-llm-wiki` | Build and maintain a personal LLM-powered knowledge base |
| `lgbm-trader-skill` | LightGBM Trading System — stacking ensemble of 5 models + meta-model producing a 0-100 trade score |
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
| `config/opencode.json` | Provider/model configuration + MCP servers (headroom, trading, alphavantage) |
| `setup-headroom.sh` | Installs headroom in a dedicated venv for token compression (60-95% savings) |

## Requires

- [opencode](https://opencode.ai) CLI installed
- Python 3.10+ (for `install.py`)

## Prerequisites per skill

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
