# opencode-skills

Custom skills and configuration for [opencode](https://opencode.ai).

## Structure

```
opencode-skills/
├── install.py                  # Python install script (recommended)
├── install.sh                  # Shell install script (quick alternative)
├── config/
│   ├── AGENTS.md               # Global rules referencing skills
│   └── opencode.json           # Provider/model configuration
└── skills/
    ├── async-python-patterns/  # Async Python patterns & practices
    ├── book-to-skill/          # Book-to-skill converter
    ├── book-to-skill-bridge/   # Zero-prompt book-to-skill generator
    ├── crypto-crash-course/    # Crypto fundamentals knowledge base
    ├── crypto-technical-analysis/  # Crypto technical analysis KB
    ├── graphify/               # Any input → knowledge graph
    ├── italy-tax-declaration-instructions/  # Italian tax return instructions
    ├── karpathy-llm-wiki/      # Personal LLM-powered wiki
    ├── market-data-fetch/      # Stock & crypto market data fetcher
    ├── opencode-skills-installer/  # Skill installer & syncer
    ├── options-analysis/       # Multi-leg options position analyzer
    ├── options-course-workbook/  # Options course workbook KB
    ├── options-crash-course/   # Options trading crash course KB
    ├── options-playbook/       # 40+ option strategies reference
    ├── pdf-ingest/             # PDF extractor for wiki/graphify
    ├── price-action-volman/    # Price action frameworks KB
    ├── python-pydantic/        # Python/Pydantic coding standards
    ├── python-venv/            # Python venv enforcement
    ├── system-info/            # OS/hardware/diagnostic reporter
    ├── trades-about-to-happen/ # Tape reading & order flow KB
    ├── trading-against-the-crowd/  # Contrarian trading KB
    ├── volume-price-analysis/  # Volume-price analysis KB
    ├── volume-profile/         # Volume profile frameworks KB
    └── wyckoff-2-0/            # Wyckoff Method frameworks KB
```

## Install

### Python (recommended)

```bash
python install.py            # copy skills, skip existing
python install.py --force    # overwrite existing files
python install.py --dry-run  # preview without copying
python install.py -v         # verbose output
```

### Shell (quick)

```bash
./install.sh                 # copy skills, skip existing
./install.sh --force         # overwrite existing files
```

## Contents

| Skill                       | Description                                                                                                    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `async-python-patterns`     | Implementing asynchronous Python applications using asyncio, concurrent programming, and async/await           |
| `book-to-skill`             | Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, etc.) into structured agent skills              |
| `book-to-skill-bridge`      | Auto-generates OpenCode skills from books/documents without interactive prompts                                |
| `crypto-crash-course`       | Knowledge base from 'The Crypto Crash Course' by Frank Richmond (cryptocurrency, blockchain)                   |
| `crypto-technical-analysis` | Knowledge base from 'Crypto Technical Analysis' by Alan John & Jon Law (TA adapted for crypto)                 |
| `graphify`                  | any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report  |
| `italy-tax-declaration-instructions` | Italian tax return instructions for financial income, capital gains, derivatives, foreign investments (Redditi PF 2026) |
| `karpathy-llm-wiki`         | Build and maintain a personal LLM-powered knowledge base                                                       |
| `market-data-fetch`         | Standardized templates for fetching stock, ETF, and crypto market data using yfinance, CoinGecko, and Bitpanda |
| `opencode-skills-installer` | Manages the opencode-skills GitHub repository where all skills live and are version-controlled                 |
| `options-analysis`          | Analyze multi-leg options positions with Greeks, payoff scenarios, and recommendations                         |
| `options-course-workbook`   | Knowledge base from 'The Options Course Workbook' by George A. Fontanills (exercises and applications)         |
| `options-crash-course`      | Knowledge base from 'Options Trading Crash Course' by Mark Elder and Brian Douglas (options trading)           |
| `options-playbook`          | Knowledge base from 'The Options Playbook' by Brian Overby (40+ options strategies)                            |
| `pdf-ingest`                | PDF extraction helper for both Karpathy LLM Wiki and Graphify workflows                                        |
| `price-action-volman`       | Knowledge base from 'Understanding Price Action' by Bob Volman (price action frameworks)                       |
| `python-pydantic`           | Python coding standards with Pydantic data models, type hints, and pylint compliance                           |
| `python-venv`               | Enforces the mandatory use of Python virtual environments (venv) for all Python projects                       |
| `system-info`               | Gather detailed machine information to make correct build decisions (OS, hardware, toolchains)                 |
| `trades-about-to-happen`    | Knowledge base from 'Trades About to Happen' by David Weis (tape reading, order flow)                          |
| `trading-against-the-crowd` | Knowledge base from 'Trading Against the Crowd' by John F. Summa (contrarian trading frameworks)               |
| `volume-price-analysis`     | Knowledge base from 'A Complete Guide To Volume Price Analysis' by Anna Coulling                               |
| `volume-profile`            | Knowledge base from 'VOLUME PROFILE' by Trader Dale (volume profile frameworks for institutional trading)      |
| `wyckoff-2-0`               | Knowledge base from 'Wyckoff 2.0' by Rubén Villahermosa Chaves (volume profile, order flow, Wyckoff Method)    |
| `config/AGENTS.md`          | Global rules that load skills automatically                                                                    |
| `config/opencode.json`      | Provider/model configuration (modify before installing)                                                        |

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
