# Changelog

## 0.1.0

- Initial VS Code extension release.
- SQLite data layer on sql.js with backups, CSV export/migration and merchant seeding.
- Plotly dashboard with patrimony forecast, run-rate, statistics, waterfall,
  benchmark, heatmap, category trend and YoY comparison.
- Gestione Dati editor: monthly budget, budget targets, merchant mapping.
- Gestione Mese: PDF/CSV bank import, hybrid and llm_only AI classification,
  review table, incremental save and manual month entry.
- Streaming AI assistant with budget data context and markdown rendering.
- Multi-provider AI configuration (OpenCode CLI, Gemini, Groq, Ollama, OpenRouter, Puter)
  with SecretStorage keys and `.env` fallback.
- Optional GitHub cloud backup/restore.

## 0.2.0

- The UI now lives in the Activity Bar as a dedicated view container with a
  single `Budget` webview, in the same style as IBKR Portfolio History and
  Trade Assistant.
- Removed the editor-area webview panel; commands focus the Activity Bar view.
- Added the `Budget: Open AI Assistant` command.
- Added view title actions for import and navigation.

## 0.3.0

- OpenCode Go model list is now discovered live from
  `https://opencode.ai/zen/go/v1/models` and merged with the static catalog.
  The static catalog is refreshed to the current 30 models.
- Model list cache is 5 minutes; `refreshAll` forces a new fetch.
- Cloud Sync can seed the local database from the remote CSV (`Budget: CSV iniziale`).
- `Restore` falls back to the CSV seed when the remote DB file is missing.
- Empty database plus enabled cloud sync imports the CSV automatically on first open.
- Default cloud paths point to `giuseppedavidde/StreamLitPrj`, `Budget_App/budget.db`
  and `Budget_App/budget_database.csv`.

## 0.3.1

- The remote CSV is read without a GitHub token for public repositories
  (`raw.githubusercontent.com`), so the seed works out of the box.
- The automatic CSV seed runs when the local database is empty and a cloud
  repository is configured. It does not depend on the cloud toggle or the token.
- The seed never overwrites a database that already contains rows.
- Renamed the button to `Scarica CSV`.
- A cloud repository written with a trailing folder (`owner/repo/Budget_App`) is
  normalized automatically: the extra segment moves into the DB and CSV paths.

## 0.4.0

- Fix: `Conferma e Salva nel Database` was blocked when the webview dialog was
  unavailable. The save now uses an in-webview two-click confirmation.
  Same fix for the cloud `Restore` action.
- Review results are cumulative: a new CSV or PDF adds rows to the pending
  review until you save. Row indices are preserved.
- After a save the extension selects the imported month in the sidebar,
  reloads the transactions and re-renders the whole UI.
- `Gestione Mese` defaults to the newest month in the database, not to today.
- The manual month form detects an existing month by name or month number and
  shows a read-only table with the current values.
