import { homedir } from 'node:os';
import { join } from 'node:path';
import * as vscode from 'vscode';
import { buildDataset, resolveDisplayCurrencies, resolveDisplayCurrency } from '../analytics/dataset.ts';
import type { PortfolioContextStore } from '../chat/portfolioContext.ts';
import type { CredentialStore } from '../config/secrets.ts';
import { readSettings } from '../config/settings.ts';
import { validateForm } from '../config/validation.ts';
import { filterTradesByAccount, filterTradesByRange, rangeToMs } from '../core/dates.ts';
import { RateTable } from '../core/rates.ts';
import type { BaseCurrencySource, ConversionRate, DateRange, FormState, Trade } from '../core/types.ts';
import { tradesToCsv } from '../export/csv.ts';
import { FLEX_BASE_URL, FlexClient } from '../flex/client.ts';
import { FlexCancelledError, FlexEmptyError, FlexError } from '../flex/errors.ts';
import { detectQueryType, parseReport } from '../flex/parser.ts';
import type { FlexRowShape } from '../flex/parser.ts';
import { buildDiagnosticsReport, failureFactsOf } from './diagnostics.ts';
import { CLIENT_PORTAL_FLEX_URL, FLEX_DOCS_URL } from './html.ts';
import type { DatasetMeta, HostMessage, SettingsSnapshot, WebviewMessage } from './protocol.ts';

export interface PanelDependencies {
  readonly extensionUri: vscode.Uri;
  readonly store: CredentialStore;
  readonly output: vscode.OutputChannel;
  /**
   * Shared with the Trade Chat. Every successful fetch publishes its dataset
   * here, so the chat always talks about the same rows the panel shows.
   */
  readonly chat?: PortfolioContextStore;
}

/** Transport used by the controller to talk to one webview (editor panel or sidebar view). */
export interface HistorySink {
  post(message: HostMessage): Thenable<unknown>;
  log(line: string): void;
}

const VIEW_TYPE = 'ibkrHistory.panel';

/** Facts of the last successful fetch that a display-currency switch must reuse. */
interface PersistedBuild {
  readonly rowsTotal: number;
  readonly range: DateRange;
  readonly accountFilter: string;
  readonly baseCurrency: string;
  readonly baseCurrencySource: BaseCurrencySource;
  readonly conversionRates: readonly ConversionRate[];
}

/**
 * The explicit non-base setting wins. Otherwise the panel restores the last
 * choice made in the segmented control, and `base` when neither is present.
 */
function preferredDisplayCurrency(setting: string, stored: string | undefined): string {
  if (setting && setting !== 'base') {
    return setting;
  }
  return stored && stored.length > 0 ? stored : 'base';
}

/** Version shown in the diagnostics report. Falls back when the host cannot resolve it. */
function extensionVersion(): string {
  try {
    const extension = vscode.extensions.getExtension('giuseppe.ibkr-mexem-portfolio-history');
    const version: unknown = extension?.packageJSON?.version;
    return typeof version === 'string' && version.length > 0 ? version : 'unknown';
  } catch {
    return 'unknown';
  }
}

export function createOutputLogger(output: vscode.OutputChannel): (message: string) => void {
  return (message: string) => {
    output.appendLine(`[${new Date().toISOString()}] ${message}`);
  };
}

/**
 * Shared state, message protocol and analytics for every surface that renders the
 * IBKR portfolio UI. The editor tab and the Activity Bar webview view only differ
 * in how they post messages and how they are shown.
 */
export class HistoryController {
  static readonly viewType = VIEW_TYPE;

  private readonly sink: HistorySink;
  private readonly store: CredentialStore;
  private readonly chat: PortfolioContextStore | undefined;
  private abortController: AbortController | undefined;
  private lastTrades: readonly Trade[] = [];
  private lastMeta: DatasetMeta | undefined;
  private ready = false;
  private pendingFetch = false;
  private disposed = false;
  private lastDiagnostics = '';
  /** Row shape of the last fetched report, for the diagnostics report. */
  private lastQueryType: FlexRowShape | undefined;
  /** Rows the last parse produced, for the diagnostics report. */
  private lastRowsParsed: number | undefined;
  /** Everything needed to rebuild the dataset when the display currency changes. */
  private lastBuild: PersistedBuild | undefined;
  /** P&L currency currently rendered by every surface. */
  private displayCurrency: string | undefined;

  constructor(deps: Pick<PanelDependencies, 'store'> & { readonly chat?: PortfolioContextStore }, sink: HistorySink) {
    this.store = deps.store;
    this.chat = deps.chat;
    this.sink = sink;
  }

  get hasData(): boolean {
    return this.lastTrades.length > 0;
  }

  async refreshState(): Promise<void> {
    if (this.ready) {
      await this.sendState();
    }
  }

  requestFetch(): void {
    if (!this.ready) {
      this.pendingFetch = true;
      return;
    }
    void this.post({ type: 'requestFetch' });
  }

  private log(message: string): void {
    if (this.disposed) {
      return;
    }
    this.sink.log(message);
  }

  private async post(message: HostMessage): Promise<void> {
    if (this.disposed) {
      return;
    }
    await this.sink.post(message);
  }

  private async snapshot(): Promise<SettingsSnapshot> {
    const token = await this.store.getToken();
    const queryId = await this.store.getQueryId();
    const masked = queryId ? `${'•'.repeat(Math.min(8, Math.max(0, queryId.length - 3)))}${queryId.slice(-3)}` : '';
    return {
      hasToken: Boolean(token),
      hasQueryId: Boolean(queryId),
      queryIdMasked: masked,
      accountFilter: this.store.getAccountFilter(),
      preset: this.store.getLastPreset(),
      customStart: '',
      customEnd: '',
      lastFetchIso: this.store.getLastFetchIso() ?? null,
      fallbackFromProceeds: readSettings().fallbackFromProceeds,
      displayCurrency: readSettings().displayCurrency
    };
  }

  private async sendState(): Promise<void> {
    const settings = await this.snapshot();
    const runtime = readSettings();
    await this.post({
      type: 'state',
      settings,
      deadlineMs: runtime.deadlineMs,
      maxAttempts: runtime.maxAttempts
    });
  }

  async handleMessage(message: WebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case 'ready':
          this.ready = true;
          await this.sendState();
          if (this.pendingFetch) {
            this.pendingFetch = false;
            await this.post({ type: 'requestFetch' });
          }
          break;
        case 'fetch':
          await this.runFetch(message.form);
          break;
        case 'cancel':
          this.abortController?.abort();
          break;
        case 'displayCurrency':
          await this.setDisplayCurrency(message.currency);
          break;
        case 'export':
          await this.exportCsv();
          break;
        case 'clearCredentials':
          await this.clearCredentials();
          break;
        case 'openDocs':
          await vscode.env.openExternal(vscode.Uri.parse(FLEX_DOCS_URL));
          break;
        case 'copyDiagnostics':
          await this.copyDiagnostics();
          break;
        default:
          break;
      }
    } catch (error) {
      this.log(`Unhandled panel error: ${error instanceof Error ? error.name : 'unknown'}`);
      await this.post({
        type: 'error',
        message:
          error instanceof FlexError ? error.userMessage : `Unexpected failure: ${error instanceof Error ? error.message : String(error)}`,
        fieldErrors: {}
      });
      await this.post({ type: 'busy', busy: false, message: '' });
    }
  }

  private async fail(message: string, fieldErrors: Record<string, string> = {}): Promise<void> {
    await this.post({ type: 'error', message, fieldErrors });
    const choice = await vscode.window.showErrorMessage(message, 'Open Flex docs', 'Open Client Portal');
    if (choice === 'Open Flex docs') {
      await vscode.env.openExternal(vscode.Uri.parse(FLEX_DOCS_URL));
    } else if (choice === 'Open Client Portal') {
      await vscode.env.openExternal(vscode.Uri.parse(CLIENT_PORTAL_FLEX_URL));
    }
  }

  private async runFetch(form: FormState): Promise<void> {
    const hasStoredToken = await this.store.hasToken();
    const hasStoredQueryId = await this.store.hasQueryId();
    const validation = validateForm(form, { hasStoredToken, hasStoredQueryId });
    if (!validation.ok) {
      await this.post({ type: 'error', message: validation.message, fieldErrors: validation.errors });
      return;
    }

    const token = validation.value.token ?? (await this.store.getToken());
    const queryId = validation.value.queryId || (await this.store.getQueryId()) || '';
    if (!token) {
      await this.fail('No Flex token available. Paste a token or clear the stored one and try again.', {
        token: 'Flex token required.'
      });
      return;
    }

    if (validation.value.token) {
      await this.store.setToken(validation.value.token);
    }
    if (validation.value.queryId) {
      await this.store.setQueryId(validation.value.queryId);
    }
    await this.store.setAccountFilter(validation.value.accountId);
    await this.store.setLastPreset(validation.value.range.preset);

    const runtime = readSettings();
    const controller = new AbortController();
    this.abortController = controller;
    controller.signal.addEventListener('abort', () => {
      this.log('Fetch cancelled by the user.');
    });

    this.lastQueryType = undefined;
    this.lastRowsParsed = undefined;
    await this.post({ type: 'busy', busy: true, message: 'Contacting IBKR Flex Web Service…' });

    try {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'IBKR Flex report',
          cancellable: true
        },
        async (progress, cancelToken) => {
          const subscription = cancelToken.onCancellationRequested(() => controller.abort());
          try {
            const client = new FlexClient({
              token,
              queryId,
              requestTimeoutMs: runtime.requestTimeoutMs,
              deadlineMs: runtime.deadlineMs,
              maxAttempts: runtime.maxAttempts,
              maxSendAttempts: runtime.maxSendAttempts,
              initialDelayMs: runtime.initialDelayMs,
              maxDelayMs: runtime.maxDelayMs,
              now: () => Date.now(),
              onAttempt: (attempt, maxAttempts, detail, info) => {
                const label = attempt === 0 ? detail : `${detail} (attempt ${attempt}/${maxAttempts})`;
                progress.report({ message: label, increment: attempt === 0 ? 0 : 100 / maxAttempts });
                void this.post({
                  type: 'progress',
                  message: detail,
                  attempt,
                  maxAttempts,
                  phase: 'poll',
                  elapsedMs: info.elapsedMs,
                  lastStatus: info.lastStatus
                });
              },
              onSendAttempt: (attempt, maxSendAttempts, detail, info) => {
                progress.report({ message: `${detail} (${attempt}/${maxSendAttempts})`, increment: 0 });
                void this.post({
                  type: 'progress',
                  message: detail,
                  attempt,
                  maxAttempts: maxSendAttempts,
                  phase: 'send',
                  elapsedMs: info.elapsedMs,
                  lastStatus: info.lastStatus
                });
              }
            });

            this.log(`SendRequest start (queryId masked, token masked): ${client.describe()}`);
            const result = await client.fetchStatement(controller.signal);
            this.log(
              `Statement received: ${result.xml.length} bytes, ${result.requestCount} HTTP requests, ` +
                `${result.attempts} polls, ${result.durationMs} ms.`
            );

            progress.report({ message: 'Parsing report…', increment: 5 });
            // Detect the query flavour before parsing: the answer must be logged
            // even when the report turns out to contain no rows.
            const queryType = detectQueryType(result.xml);
            this.lastQueryType = queryType.shape;
            this.log(
              `Detected Flex query type: ${queryType.shape}` +
                (queryType.declaredType ? ` (declared type="${queryType.declaredType}")` : ' (no declared type)')
            );
            const report = parseReport(result.xml, {
              fallbackFromProceeds: runtime.fallbackFromProceeds,
              baseCurrencyOverride: runtime.baseCurrency ?? undefined,
              fetch: { attempts: result.attempts, elapsedMs: result.durationMs }
            });
            const trades = report.trades;
            this.lastRowsParsed = trades.length;
            this.log(
              `Parsed ${trades.length} trade rows. Base currency: ${report.baseCurrency} (${report.baseCurrencySource}), ` +
                `${report.conversionRates.length} ConversionRate row(s).`
            );
            for (const warning of report.warnings) {
              this.log(`Parser note: ${warning}`);
            }

            const { startMs, endMs } = rangeToMs(validation.value.range);
            const inRange = filterTradesByRange(trades, startMs, endMs);
            const filtered = filterTradesByAccount(inRange, validation.value.accountId);
            this.log(
              `Local filter ${validation.value.range.start}..${validation.value.range.end}: ` +
                `${inRange.length}/${trades.length} in range, ${filtered.length} after account filter.`
            );

            if (filtered.length === 0) {
              await this.post({ type: 'busy', busy: false, message: '' });
              await this.reportNoRows(trades, inRange.length, validation.value.accountId);
              return;
            }

            const build: PersistedBuild = {
              rowsTotal: trades.length,
              range: validation.value.range,
              accountFilter: validation.value.accountId,
              baseCurrency: report.baseCurrency,
              baseCurrencySource: report.baseCurrencySource,
              conversionRates: report.conversionRates
            };
            const requested = preferredDisplayCurrency(runtime.displayCurrency, this.store.getDisplayCurrency());
            const dataset = buildDataset({
              trades: filtered,
              rowsTotal: build.rowsTotal,
              range: build.range,
              accountFilter: build.accountFilter,
              generatedAt: new Date(),
              baseCurrency: build.baseCurrency,
              baseCurrencySource: build.baseCurrencySource,
              conversionRates: build.conversionRates,
              displayCurrency: requested
            });

            this.lastTrades = filtered;
            this.lastBuild = build;
            this.displayCurrency = dataset.displayCurrency;
            this.lastMeta = dataset.meta;
            if (dataset.displayCurrency !== this.store.getDisplayCurrency()) {
              await this.store.setDisplayCurrency(dataset.displayCurrency);
            }
            this.chat?.set(dataset);
            await this.store.setLastFetchIso(new Date().toLocaleString());
            await this.post({ type: 'data', dataset, reason: 'fetch' });
          } finally {
            subscription.dispose();
          }
        }
      );
    } catch (error) {
      if (error instanceof FlexCancelledError) {
        await this.post({ type: 'info', message: 'Fetch cancelled. Nothing was changed.' });
      } else if (error instanceof FlexError) {
        this.log(`Fetch failed: ${error.name}: ${error.message}`);
        this.lastDiagnostics = this.buildFetchDiagnostics({
          secrets: [token, queryId],
          queryIdDigits: queryId.length,
          maxAttempts: runtime.maxAttempts,
          maxSendAttempts: runtime.maxSendAttempts,
          deadlineMs: runtime.deadlineMs,
          error,
          queryType: this.lastQueryType,
          rowsParsed: error instanceof FlexEmptyError ? 0 : this.lastRowsParsed
        });
        await this.fail(error.userMessage);
      } else {
        const detail = error instanceof Error ? error.message : String(error);
        this.log(`Fetch failed with unexpected error: ${error instanceof Error ? error.name : 'unknown'}`);
        await this.fail(`Unexpected failure while fetching the Flex report: ${detail}`);
      }
    } finally {
      this.abortController = undefined;
      await this.post({ type: 'busy', busy: false, message: '' });
    }
  }

  /** Redacted report for the clipboard. The token and Query ID never appear. */
  private buildFetchDiagnostics(context: {
    secrets: readonly string[];
    queryIdDigits: number;
    maxAttempts: number;
    maxSendAttempts: number;
    deadlineMs: number;
    error: FlexError;
    queryType?: FlexRowShape;
    rowsParsed?: number;
  }): string {
    // Every FlexError fills `diagnostics`, so a network failure, an empty report
    // and a protocol failure all produce a report with real facts.
    const facts = failureFactsOf(context.error);
    return buildDiagnosticsReport({
      extensionVersion: extensionVersion(),
      baseUrl: FLEX_BASE_URL,
      tokenLength: context.secrets[0]?.length ?? 0,
      queryIdDigits: context.queryIdDigits,
      elapsedMs: facts.elapsedMs,
      attempts: facts.attempts,
      maxAttempts: context.maxAttempts,
      sendAttempts: facts.sendAttempts,
      maxSendAttempts: facts.maxSendAttempts ?? context.maxSendAttempts,
      lastRetryReason: facts.lastRetryReason,
      deadlineMs: context.deadlineMs,
      lastStatus: facts.lastStatus,
      lastErrorCode: facts.lastErrorCode,
      bodySnippet: facts.bodySnippet,
      queryType: context.queryType && context.queryType !== 'unknown' ? context.queryType : undefined,
      rowsParsed: context.rowsParsed,
      secrets: context.secrets
    });
  }

  async copyDiagnostics(): Promise<void> {
    if (!this.lastDiagnostics) {
      await vscode.window.showWarningMessage('No diagnostics to copy. Fetch a report first.');
      return;
    }
    await vscode.env.clipboard.writeText(this.lastDiagnostics);
    this.log('Diagnostics copied to the clipboard (redacted).');
    await vscode.window.showInformationMessage('IBKR diagnostics copied to the clipboard.');
  }

  private async reportNoRows(trades: readonly Trade[], inRangeCount: number, accountFilter: string): Promise<void> {
    const dates = trades.map((trade) => trade.tradeDate).filter((value) => value.length > 0).sort();
    const first = dates[0] ?? 'unknown';
    const last = dates[dates.length - 1] ?? 'unknown';
    const parts = [
      inRangeCount === 0
        ? `IBKR returned ${trades.length} trades covering ${first} → ${last}, but none fall in the selected range.`
        : `No trades match the account filter "${accountFilter}".`
    ];
    parts.push(
      'The Flex query period is configured in Client Portal and cannot be changed by this request. ' +
        'Set it to "Year To Date" or "Last 365 days", or widen the date range in this panel.'
    );
    await this.post({ type: 'error', message: parts.join(' '), fieldErrors: {} });
    const choice = await vscode.window.showWarningMessage(parts[0] ?? 'No trades in range.', 'Open Client Portal');
    if (choice === 'Open Client Portal') {
      await vscode.env.openExternal(vscode.Uri.parse(CLIENT_PORTAL_FLEX_URL));
    }
  }

  /**
   * Switch the P&L currency, persist the choice and republish the dataset. An
   * unknown or unavailable code falls back to the base currency: a cross rate is
   * never invented.
   */
  private async setDisplayCurrency(code: string): Promise<void> {
    const build = this.lastBuild;
    if (!build || this.lastTrades.length === 0) {
      return;
    }
    const rates = new RateTable(build.conversionRates, build.baseCurrency);
    const tradeCurrencies = [...new Set(this.lastTrades.map((trade) => trade.currency).filter((value) => value.length > 0))];
    const available = resolveDisplayCurrencies(build.baseCurrency, tradeCurrencies, rates);
    const next = resolveDisplayCurrency(code, build.baseCurrency, available);
    await this.store.setDisplayCurrency(next);
    const dataset = buildDataset({
      trades: this.lastTrades,
      rowsTotal: build.rowsTotal,
      range: build.range,
      accountFilter: build.accountFilter,
      generatedAt: new Date(),
      baseCurrency: build.baseCurrency,
      baseCurrencySource: build.baseCurrencySource,
      conversionRates: build.conversionRates,
      displayCurrency: next
    });
    this.lastMeta = dataset.meta;
    this.displayCurrency = dataset.displayCurrency;
    this.chat?.set(dataset);
    this.log(`P&L display currency set to ${next} (base ${build.baseCurrency}, available: ${available.join(', ')}).`);
    await this.post({ type: 'data', dataset, reason: 'currency' });
  }

  async exportCsv(): Promise<void> {
    if (this.lastTrades.length === 0) {
      await vscode.window.showWarningMessage('No dataset to export. Fetch a report first.');
      return;
    }
    const range = this.lastMeta?.range;
    const name = `ibkr-history-${range?.start ?? 'start'}_${range?.end ?? 'end'}.csv`;
    const target = await vscode.window.showSaveDialog({
      title: 'Export IBKR portfolio history',
      defaultUri: vscode.Uri.file(join(homedir(), name)),
      filters: { CSV: ['csv'] },
      saveLabel: 'Export CSV'
    });
    if (!target) {
      return;
    }
    const build = this.lastBuild;
    const rateTable = build ? new RateTable(build.conversionRates, build.baseCurrency) : undefined;
    // The export follows the currency shown in the panel, so the CSV and the
    // table never disagree.
    const csv = tradesToCsv(this.lastTrades, {
      displayCurrency: this.displayCurrency ?? build?.baseCurrency,
      rateTable
    });
    await vscode.workspace.fs.writeFile(target, new TextEncoder().encode(csv));
    this.log(`Exported ${this.lastTrades.length} rows to ${target.fsPath}.`);
    const choice = await vscode.window.showInformationMessage(
      `Exported ${this.lastTrades.length} trades to ${target.fsPath}.`,
      'Reveal in Explorer'
    );
    if (choice === 'Reveal in Explorer') {
      await vscode.commands.executeCommand('revealFileInOS', target);
    }
  }

  private async clearCredentials(): Promise<void> {
    const confirm = await vscode.window.showWarningMessage(
      'Delete the stored Flex token and Query ID from VS Code SecretStorage?',
      { modal: true },
      'Delete'
    );
    if (confirm !== 'Delete') {
      return;
    }
    await this.store.clearToken();
    await this.store.clearQueryId();
    this.log('Stored Flex credentials cleared.');
    await this.sendState();
    await this.post({ type: 'info', message: 'Stored Flex token and Query ID deleted.' });
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.abortController?.abort();
  }
}
