# 💰 Budget App Manager (VS Code extension)

A VS Code extension that reproduces the features of the Streamlit **Budget App**:
SQLite personal-budget database, Plotly dashboard, monthly editor, AI bank-statement
import and an AI financial assistant.

Everything runs locally inside the extension host. The webview loads **no CDN assets**:
Plotly is bundled in `dist/media/plotly.min.js`.

## Features

### Dashboard
- **Patrimonio Totale** and **Totale Investito** cards with growth deltas.
- **Run-rate & KPI** for the last 12 months (mean, median, sparklines).
- **Statistiche Patrimonio**: distributions, savings stats, CAGR, YoY growth, runway.
- Charts: patrimonio history + 12-month forecast with 80% CI band, investments,
  cash flow, monthly waterfall, expense donut, savings rate, net savings + 6-month
  moving average, year × month heatmap, stacked category trend, 3-year YoY comparison,
  benchmark vs budget targets and delta.
- Filters in the sidebar (and on the page): selected month, trend horizon
  `3 / 6 / 12 / 24 / All`, optional exclusion of `Investimenti` and
  `Spese Straordinarie`, optional inclusion of `Acquisto Auto` (CAPEX view).
- Tabs **Mese Selezionato** / **Periodo (N mesi)** for the expense detail.

### Gestione Dati
- Editable monthly-budget table (add, edit, delete rows, save).
- Budget-targets editor per expense category (prefilled with the historical mean).
- Merchant → category mapping table: view, manual override, add, delete, seed import,
  JSON export. Manual entries have absolute priority over LLM/seed entries.
- SQLite info panel and CSV export.

### Gestione Mese
- Drag & drop **PDF or CSV** bank statement.
- PDF text extraction with **pdfjs-dist** (pure Node/TypeScript, no Python).
- AI categorization in two modes, exactly like the Streamlit app:
  - `hybrid (merchant map + AI)` — deterministic shortcuts, merchant map, then LLM for the rest.
  - `llm_only (force LLM on all)` — bypasses every deterministic shortcut.
- Review table with category dropdowns, row deletion, AI statistics, monthly totals
  preview and markdown report.
- The review is cumulative: a new file adds rows to the pending review until you
  save. Nothing is lost when you process a second statement.
- `Conferma e Salva` uses an in-webview two-click confirmation, because webview
  native dialogs are not reliable.
- Saves the month incrementally (existing months are summed) and persists individual
  transactions. Manual corrections are learned as `source='manual'`.
- After a save the imported month becomes the selected month in the sidebar.
- Manual month entry form (create or increment). It defaults to the newest month in
  the database, detects an existing month by name or number, and shows the current
  values before you add new ones.

### 💬 Assistant AI
- Streaming responses rendered as markdown.
- Chat history in the webview.
- The same data-context system prompt used by the Streamlit app (CSV of all months,
  “Thinking:” instructions, Italian answer).
- Works with OpenCode Go, Gemini, Groq, Ollama, OpenRouter and Puter.

### Cloud sync (optional)
- GitHub Contents API backup/restore through `GITHUB_TOKEN`.
- Uploads `budget.db` and the CSV export to the configured repo/branch/path.
- `Scarica CSV` downloads the remote CSV and seeds an empty local database.
  Read access works without a token for public repositories (raw URL).
- `Restore` falls back to the CSV seed when the remote DB file is missing.
- Empty database imports the remote CSV automatically on first open. The import
  never overwrites a database that already contains rows.
- Default paths: repo `giuseppedavidde/StreamLitPrj`, DB `Budget_App/budget.db`,
  CSV `Budget_App/budget_database.csv`.
- Backup now, restore, status. Tokens are never logged.

## AI providers

| Provider | Transport | Models |
|---|---|---|
| `opencode` | `opencode` CLI (`opencode run --format json --model opencode-go/...`) | live catalog from `https://opencode.ai/zen/go/v1/models`, merged with a static fallback |
| `gemini` | Google Generative Language REST | `gemini-2.5-flash`, `gemini-2.5-pro`, … |
| `groq` | OpenAI-compatible | `moonshotai/kimi-k2-instruct`, … |
| `ollama` | OpenAI-compatible (`http://localhost:11434/v1`) | any local model |
| `openrouter` | OpenAI-compatible | any OpenRouter model |
| `puter` | OpenAI-compatible | Claude/Gemini free tier |
| `llamacpp` | OpenAI-compatible (`http://localhost:8080/v1`) | any loaded llama-server model |

When `opencode` is selected the extension creates an OpenCode agent with the model
prefixed as `opencode-go/<model>` and a **300 s** timeout. The model list is fetched
live and cached for 5 minutes; the `Aggiorna` link in the sidebar forces a new fetch. The agent is recreated
automatically when the provider, model or API key changes.

## Security

- API keys and the GitHub token live in **VS Code SecretStorage**.
- `.env` is supported only as a fallback (workspace root or extension folder).
- Nothing is written into `settings.json` except non-secret configuration.
- `.env`, `budget.db` and real data are git-ignored. Use `.env.example` as a template.
- The webview has a nonce-based CSP and no network access (`connect-src 'none'`).

## Installation (development)

```bash
npm install
npm run build
```

Then press `F5` in VS Code (Extension Development Host) or install the packaged VSIX.

## Commands

- **Budget: Open Dashboard** (`budget.openDashboard`)
- **Budget: Import Bank Statement** (`budget.importBankStatement`)

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `budgetApp.dbPath` | `""` | SQLite path; empty = `<globalStorage>/budget.db` |
| `budgetApp.defaultTimeWindow` | `"12"` | `3`, `6`, `12`, `24`, `All` |
| `budgetApp.defaultProvider` | `"opencode"` | default AI provider (`opencode`, `gemini`, `groq`, `ollama`, `openrouter`, `puter`, `llamacpp`) |
| `budgetApp.defaultModel` | `"deepseek-v4-pro"` | default model |
| `budgetApp.cloud.enabled` | `true` | enable GitHub sync |
| `budgetApp.cloud.repo` | `"giuseppedavidde/StreamLitPrj"` | `owner/repo` |
| `budgetApp.cloud.branch` | `"main"` | branch |
| `budgetApp.cloud.path` | `"Budget_App/budget.db"` | DB path in the repo |
| `budgetApp.cloud.csvPath` | `"Budget_App/budget_database.csv"` | CSV path in the repo |

## Database

The schema mirrors the Streamlit `db.py`:

- `monthly_budget` — all base columns and `UNIQUE(Year, MonthNum)`.
- `transactions` — daily transactions with `month_ref`.
- `budget_targets` — category targets.
- `merchant_categories` — normalized merchant → category, with `source`, `confidence`,
  `times_seen`, `first_seen`, `last_seen`.

On startup the extension creates the database, seeds `media/merchant_seed.json` once
(only when the mapping is empty) and migrates `budget_database.csv` when it finds one
next to the DB path or in the workspace root. Every write creates a `.bak` backup first.

The extension uses **sql.js** (SQLite compiled to WebAssembly), so there is no native
build step and `vsce package` works on any platform.

## Development

```bash
npm run typecheck   # tsc --noEmit (strict)
npm test            # vitest (metrics, forecast, merchant normalization, classification modes, DB, PDF, cloud)
npm run build       # esbuild: extension + webview + local Plotly/sql.js/pdf.js assets
npx @vscode/vsce ls # inspect the package contents
node scripts/webview-smoke.mjs  # jsdom smoke test of the webview (needs npm run build)
npm run smoke:host             # mock VS Code host: activation, DB seed, save, targets, merchant map
```

The backend smoke test bundles and runs the SQLite + PDF code paths against the
packaged assets:

```bash
npx esbuild scripts/smoke.ts --bundle --platform=node --format=cjs --target=node18 \
  --external:canvas --outfile=/tmp/budget-smoke.cjs
node /tmp/budget-smoke.cjs
```

Sample data with synthetic values: `media/examples/sample_budget_database.csv`.
Copy it to `budget_database.csv` in the workspace root to exercise the CSV migration.

## Known limitations vs the Streamlit app

- Chat attachments (images/PDF) are not forwarded to the model.
- AI classification batches run sequentially; there is no cancellation button mid-batch.
- Bank PDFs are read as text with pdfjs-dist. Scanned/image-only PDFs are rejected with a clear error.
- LlamaCpp uses an already-running OpenAI-compatible `llama-server`; the extension does not start or stop it.
- The dashboard recomputes in the webview from the pure `metrics`/`forecast` modules.
  No `statsmodels` equivalent is needed because the app uses a deterministic linear
  trend + calendar-month seasonality forecast.
- Dynamic provider model discovery is best effort (static lists are always available).

## License

MIT — see `LICENSE`.
