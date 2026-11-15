import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import * as vscode from 'vscode';
import {
  BUDGET_COLUMNS,
  CAPEX_COLUMNS,
  EXPENSE_COLUMNS,
  INCOME_COLUMNS,
  MONTHS_EN,
  PROVIDER_MODELS,
  PROVIDER_TYPES,
  type AiConfig,
  type AiConfigState,
  type ChatMessage,
  type ClassifyMode,
  type CloudConfig,
  type HostMessage,
  type ImportResultPayload,
  type ImportReviewRow,
  type MerchantEntry,
  type MonthlyKey,
  type MonthlyRow,
  type ProviderType,
  type WebviewMessage,
} from './types';
import { BudgetDb } from './db';
import { DotEnv } from './env';
import { AiProvider, envKeyFor, listProviderModels } from './ai/provider';
import { OpenCodeCliAgent } from './ai/opencode';
import type { StreamingLlmClient } from './ai/client';
import { CloudManager } from './cloud';
import {
  aggregatedFromReview,
  applyReviewEdits,
  buildTransactionRecords,
  combineImportResults,
  mergeAggregatedIntoMonthly,
  processBankFile,
  reviewReport,
} from './importer/bankImporter';
import { toCsv } from './importer/csv';
import { sortDescending } from './metrics';

const TARGET_CATEGORIES: string[] = [
  ...INCOME_COLUMNS,
  ...EXPENSE_COLUMNS,
  ...CAPEX_COLUMNS,
];

interface CachedLlm {
  signature: string;
  client: StreamingLlmClient;
}

export class BudgetAppService implements vscode.Disposable {
  private db: BudgetDb | null = null;
  private post: ((message: HostMessage) => void) | null = null;
  private readonly dotenv: DotEnv;
  private chatMessages: ChatMessage[] = [];
  private importResult: ImportResultPayload | null = null;
  private cachedLlm: CachedLlm | null = null;
  private importing = false;
  private chatBusy = false;
  private dynamicModels: Partial<Record<ProviderType, string[]>> = {};
  private dynamicModelsAt: Partial<Record<ProviderType, number>> = {};
  private cloudSeedTried = false;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly extensionPath: string,
    private readonly output: vscode.OutputChannel,
  ) {
    const roots = (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath);
    roots.push(extensionPath);
    this.dotenv = new DotEnv(roots);
  }

  attach(post: (message: HostMessage) => void): void {
    this.post = post;
  }

  detach(): void {
    this.post = null;
  }

  dispose(): void {
    this.db?.close();
    this.db = null;
  }

  private send(message: HostMessage): void {
    if (this.post) this.post(message);
  }

  private toast(level: 'info' | 'warn' | 'error' | 'success', message: string): void {
    this.send({ type: 'toast', level, message });
    if (level === 'error') this.output.appendLine(`[error] ${message}`);
  }

  private get workspaceRoot(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  private config() {
    return vscode.workspace.getConfiguration('budgetApp');
  }

  private async ensureDb(): Promise<BudgetDb> {
    if (this.db) return this.db;
    const configured = this.config().get<string>('dbPath')?.trim();
    const dbPath =
      configured && configured.length > 0
        ? configured
        : vscode.Uri.joinPath(this.context.globalStorageUri, 'budget.db').fsPath;
    const seedPath = vscode.Uri.joinPath(this.context.extensionUri, 'media', 'merchant_seed.json').fsPath;
    const wasmPath = vscode.Uri.joinPath(this.context.extensionUri, 'dist', 'sql-wasm.wasm').fsPath;
    if (!existsSync(wasmPath)) {
      throw new Error(`File sql-wasm.wasm mancante: ${wasmPath}. Esegui "npm run build".`);
    }
    const db = await BudgetDb.open({ dbPath, seedPath, wasmPath });
    this.db = db;

    if (db.getDbInfo().rowCount === 0) {
      const candidates = [
        join(dirname(dbPath), 'budget_database.csv'),
        this.workspaceRoot ? join(this.workspaceRoot, 'budget_database.csv') : '',
      ].filter(Boolean);
      for (const candidate of candidates) {
        if (existsSync(candidate)) {
          const migrated = db.migrateFromCsv(candidate);
          if (migrated > 0) {
            this.output.appendLine(`[db] migrati ${migrated} mesi da ${candidate}`);
            break;
          }
        }
      }
    }
    return db;
  }

  private provider(): ProviderType {
    const configured = this.context.globalState.get<string>('ai.provider');
    if (configured && (PROVIDER_TYPES as string[]).includes(configured)) {
      return configured as ProviderType;
    }
    const fallback = this.config().get<string>('defaultProvider') ?? 'opencode';
    return (PROVIDER_TYPES as string[]).includes(fallback)
      ? (fallback as ProviderType)
      : 'opencode';
  }

  private modelFor(provider: ProviderType): string {
    const stored = this.context.globalState.get<string>(`ai.model.${provider}`);
    if (stored) return stored;
    const defaultProvider = this.config().get<string>('defaultProvider') ?? 'opencode';
    const defaultModel = this.config().get<string>('defaultModel');
    if (provider === defaultProvider && defaultModel) return defaultModel;
    return PROVIDER_MODELS[provider][0] ?? '';
  }

  private aiConfig(): AiConfig {
    const provider = this.provider();
    return { provider, model: this.modelFor(provider) };
  }

  private async apiKey(provider: ProviderType): Promise<string> {
    const secret = await this.context.secrets.get(`budgetApp.apiKey.${provider}`);
    if (secret) return secret;
    const envName = envKeyFor(provider);
    return this.dotenv.get(envName) ?? process.env[envName] ?? '';
  }

  private async githubToken(): Promise<string> {
    const secret = await this.context.secrets.get('budgetApp.githubToken');
    if (secret) return secret;
    return this.dotenv.get('GITHUB_TOKEN') ?? process.env.GITHUB_TOKEN ?? '';
  }

  private cloudConfig(): CloudConfig {
    const cfg = this.config();
    return {
      enabled: cfg.get<boolean>('cloud.enabled') ?? false,
      repo: cfg.get<string>('cloud.repo') ?? '',
      branch: cfg.get<string>('cloud.branch') ?? 'main',
      path: cfg.get<string>('cloud.path') ?? 'budget.db',
      csvPath: cfg.get<string>('cloud.csvPath') ?? 'budget_database.csv',
      tokenSet: false,
    };
  }

  private async cloudConfigState(): Promise<CloudConfig> {
    return { ...this.cloudConfig(), tokenSet: Boolean(await this.githubToken()) };
  }

  private async aiConfigState(dynamic = false): Promise<AiConfigState> {
    const config = this.aiConfig();
    const key = await this.apiKey(config.provider);
    let models = PROVIDER_MODELS[config.provider];
    const cacheAge = Date.now() - (this.dynamicModelsAt[config.provider] ?? 0);
    if (dynamic && cacheAge > 300_000) {
      try {
        const fetched = await listProviderModels(config.provider, key);
        if (fetched.length > 0) {
          this.dynamicModels[config.provider] = fetched;
          this.dynamicModelsAt[config.provider] = Date.now();
        }
      } catch {
        // keep static list
      }
    }
    const cachedModels = this.dynamicModels[config.provider];
    if (cachedModels && cachedModels.length > 0) models = cachedModels;
    return {
      ...config,
      keySet: Boolean(key),
      models,
      envKeyAvailable: Boolean(this.dotenv.get(envKeyFor(config.provider)) ?? process.env[envKeyFor(config.provider)]),
    };
  }

  private invalidateLlm(): void {
    this.cachedLlm = null;
  }

  private async getLlm(required: boolean): Promise<StreamingLlmClient | null> {
    const config = this.aiConfig();
    const key = await this.apiKey(config.provider);
    const signature = `${config.provider}|${config.model}|${key}`;
    if (this.cachedLlm?.signature === signature) return this.cachedLlm.client;

    try {
      const client: StreamingLlmClient =
        config.provider === 'opencode'
          ? new OpenCodeCliAgent({
              model: config.model,
              timeoutMs: 300_000,
              apiKey: key,
              cwd: this.workspaceRoot ?? this.extensionPath,
            })
          : new AiProvider(config, key, { timeoutMs: 300_000 });
      this.cachedLlm = { signature, client };
      return client;
    } catch (error) {
      if (!required) return null;
      throw error;
    }
  }

  async handleMessage(message: WebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case 'ready':
          await this.sendInitial();
          break;
        case 'refreshAll':
          this.dynamicModelsAt[this.aiConfig().provider] = 0;
          await this.sendDatabase();
          await this.sendAiConfig(true);
          await this.sendCloudState();
          break;
        case 'loadTransactions':
          await this.sendTransactions(message.monthRef);
          break;
        case 'saveMonthly': {
          const db = await this.ensureDb();
          db.saveData(message.rows, message.deleted);
          await this.sendDatabase();
          this.toast('success', 'Dati salvati con successo!');
          break;
        }
        case 'saveTargets': {
          const db = await this.ensureDb();
          db.saveBudgetTargets(message.targets);
          await this.sendDatabase();
          this.toast('success', 'Target salvati!');
          break;
        }
        case 'loadMerchants':
          await this.sendMerchantMap();
          break;
        case 'setMerchantManual':
        case 'addMerchantManual': {
          const db = await this.ensureDb();
          db.setMerchantManual(message.merchant, message.category);
          await this.sendMerchantMap();
          this.toast('success', `Mappatura manuale salvata: ${message.merchant} → ${message.category}`);
          break;
        }
        case 'deleteMerchant': {
          const db = await this.ensureDb();
          const deleted = db.deleteMerchant(message.merchant);
          await this.sendMerchantMap();
          this.toast(deleted ? 'success' : 'warn', deleted ? 'Voce eliminata.' : 'Voce non trovata.');
          break;
        }
        case 'importSeed': {
          const db = await this.ensureDb();
          const seedPath = vscode.Uri.joinPath(this.context.extensionUri, 'media', 'merchant_seed.json').fsPath;
          const count = db.seedMerchantsFromJson(seedPath);
          await this.sendMerchantMap();
          this.toast(
            count > 0 ? 'success' : 'info',
            count > 0 ? `Seed importato: ${count} voci.` : 'Seed già importato o file assente.',
          );
          break;
        }
        case 'exportCsv':
          await this.exportCsv();
          break;
        case 'exportMerchants':
          await this.exportMerchants();
          break;
        case 'chooseImportFile':
          await this.chooseImportFile(message.classifyMode);
          break;
        case 'importStatement':
          await this.importBuffer(
            message.fileName,
            Buffer.from(message.dataBase64, 'base64'),
            message.classifyMode,
          );
          break;
        case 'applyImportEdits':
          await this.applyImport(message.rows);
          break;
        case 'saveImport':
          await this.saveImport(message.rows);
          break;
        case 'cancelImport':
          this.importResult = null;
          break;
        case 'setAiConfig': {
          await this.context.globalState.update('ai.provider', message.provider);
          await this.context.globalState.update(`ai.model.${message.provider}`, message.model);
          this.invalidateLlm();
          await this.sendAiConfig(true);
          this.toast('success', `AI configurata: ${message.provider} / ${message.model}`);
          break;
        }
        case 'setApiKey': {
          await this.context.secrets.store(`budgetApp.apiKey.${message.provider}`, message.apiKey.trim());
          this.invalidateLlm();
          await this.sendAiConfig(true);
          this.toast('success', `API key salvata per ${message.provider} (SecretStorage).`);
          break;
        }
        case 'clearApiKey': {
          await this.context.secrets.delete(`budgetApp.apiKey.${message.provider}`);
          this.invalidateLlm();
          await this.sendAiConfig();
          this.toast('info', `API key rimossa per ${message.provider}.`);
          break;
        }
        case 'chatSend':
          await this.chat(message.requestId, message.text);
          break;
        case 'chatClear':
          this.chatMessages = [];
          this.send({ type: 'chatHistory', messages: [] });
          break;
        case 'setCloudEnabled': {
          await this.config().update('cloud.enabled', message.enabled, vscode.ConfigurationTarget.Global);
          await this.sendCloudState();
          break;
        }
        case 'setCloudConfig': {
          await this.config().update('cloud.repo', message.repo, vscode.ConfigurationTarget.Global);
          await this.config().update('cloud.branch', message.branch, vscode.ConfigurationTarget.Global);
          await this.config().update('cloud.path', message.path, vscode.ConfigurationTarget.Global);
          await this.config().update('cloud.csvPath', message.csvPath, vscode.ConfigurationTarget.Global);
          await this.sendCloudState();
          this.toast('success', 'Configurazione cloud salvata.');
          break;
        }
        case 'setGithubToken': {
          await this.context.secrets.store('budgetApp.githubToken', message.token.trim());
          await this.sendCloudState();
          this.toast('success', 'GitHub token salvato (SecretStorage).');
          break;
        }
        case 'clearGithubToken': {
          await this.context.secrets.delete('budgetApp.githubToken');
          await this.sendCloudState();
          this.toast('info', 'GitHub token rimosso.');
          break;
        }
        case 'cloudBackup':
          await this.cloudBackup();
          break;
        case 'cloudRestore':
          await this.cloudRestore();
          break;
        case 'cloudImportCsv':
          await this.cloudImportCsv();
          break;
        case 'cloudStatus':
          await this.cloudStatus();
          break;
        case 'addManualMonth':
          await this.addManualMonth(message.year, message.month, message.mode, message.values);
          break;
        default:
          this.toast('warn', 'Comando non riconosciuto.');
      }
    } catch (error) {
      const text = (error as Error).message;
      if (message.type === 'importStatement' || message.type === 'chooseImportFile') {
        this.send({ type: 'importError', message: text });
      } else if (message.type === 'chatSend') {
        this.send({ type: 'chatError', requestId: message.requestId, message: text });
      } else {
        this.toast('error', text);
      }
    }
  }

  async sendInitial(): Promise<void> {
    const db = await this.ensureDb();
    const rows = db.loadData();
    const latest = rows[0];
    const transactions = db.loadTransactions(
      latest ? `${latest.Month} ${latest.Year}` : undefined,
    );
    const ai = await this.aiConfigState();
    const cloud = await this.cloudConfigState();
    this.send({
      type: 'init',
      payload: {
        rows,
        targets: db.getBudgetTargets(),
        dbInfo: db.getDbInfo(),
        transactions,
        ai,
        cloud,
        defaultTimeWindow: this.config().get<string>('defaultTimeWindow') ?? '12',
        chat: this.chatMessages,
        extensionVersion: String(this.context.extension.packageJSON.version ?? '0.1.0'),
      },
    });
    void this.sendAiConfig(true);
    if (!this.cloudSeedTried && rows.length === 0 && cloud.repo) {
      this.cloudSeedTried = true;
      void this.cloudImportCsv();
    }
  }

  private async sendDatabase(): Promise<void> {
    const db = await this.ensureDb();
    this.send({
      type: 'database',
      rows: db.loadData(),
      targets: db.getBudgetTargets(),
      dbInfo: db.getDbInfo(),
    });
  }

  private async sendTransactions(monthRef: string): Promise<void> {
    const db = await this.ensureDb();
    this.send({ type: 'transactions', monthRef, rows: db.loadTransactions(monthRef) });
  }

  private async sendAiConfig(dynamic = false): Promise<void> {
    this.send({ type: 'aiConfig', config: await this.aiConfigState(dynamic) });
  }

  private async sendCloudState(status = ''): Promise<void> {
    this.send({ type: 'cloudState', state: await this.cloudConfigState(), status });
  }

  private async sendMerchantMap(): Promise<void> {
    const db = await this.ensureDb();
    const entries = db.getMerchantList();
    const categories = [
      ...new Set<string>([
        ...TARGET_CATEGORIES,
        ...entries.map((entry) => entry.category),
      ]),
    ].sort();
    this.send({
      type: 'merchantMap',
      entries,
      categories,
      count: entries.length,
    });
  }

  private async chooseImportFile(mode: ClassifyMode): Promise<void> {
    const picked = await vscode.window.showOpenDialog({
      canSelectMany: false,
      openLabel: 'Analizza estratto conto',
      filters: { 'Estratto conto': ['csv', 'pdf'] },
    });
    const file = picked?.[0];
    if (!file) return;
    const bytes = readFileSync(file.fsPath);
    await this.importBuffer(file.fsPath.split(/[\\/]/).pop() ?? 'statement.csv', bytes, mode);
  }

  async openImportFlow(mode: ClassifyMode): Promise<void> {
    await this.chooseImportFile(mode);
  }

  private async importBuffer(fileName: string, data: Buffer, mode: ClassifyMode): Promise<void> {
    if (this.importing) {
      this.toast('warn', 'Un import è già in corso.');
      return;
    }
    this.importing = true;
    const previous = this.importResult;
    try {
      const db = await this.ensureDb();
      const llm = await this.getLlm(false);
      if (!llm && mode === 'llm_only') {
        throw new Error('Modalità "Solo AI" richiede un provider AI configurato con API key valida.');
      }
      const result = await processBankFile(data, fileName, {
        targetCategories: TARGET_CATEGORIES,
        incomeColumns: [...INCOME_COLUMNS],
        merchantMap: db.getMerchantMap(),
        classifyMode: mode,
        llm,
        progress: (percent, text) =>
          this.send({ type: 'importProgress', percent, message: text }),
        onLlmMapping: (keys, category) => {
          for (const key of keys) {
            try {
              db.upsertMerchant(key, category, 'llm', 0.7, false);
            } catch {
              // manual entries win; ignore
            }
          }
        },
        pdfAssetsDir: vscode.Uri.joinPath(this.context.extensionUri, 'dist').fsPath,
        sourceName: fileName,
      });
      db.persistNow();
      this.importResult = previous
        ? combineImportResults(previous, result, TARGET_CATEGORIES)
        : result;
      this.send({ type: 'importResult', result: this.importResult });
      this.output.appendLine(
        `[import] ${fileName}: ${result.rows.length} righe, ${result.stats.llmMapped}/${result.stats.llmSent} AI.`,
      );
    } catch (error) {
      this.importResult = previous;
      const message = (error as Error).message;
      this.output.appendLine(`[import] errore: ${message}`);
      this.send({ type: 'importError', message });
    } finally {
      this.importing = false;
    }
  }

  private applyEditsInternal(rows: readonly ImportReviewRow[]): {
    editedRows: ImportReviewRow[];
    aggregated: ImportResultPayload['aggregated'];
    report: string;
    learned: number;
    deleted: number;
  } {
    if (!this.importResult) throw new Error('Nessun import in memoria.');
    const result = applyReviewEdits(rows, this.importResult.categoryOptions);
    for (const entry of result.learning) {
      for (const key of entry.keys) {
        try {
          void this.db?.setMerchantManual(key, entry.category);
        } catch {
          // ignore
        }
      }
    }
    const aggregated = aggregatedFromReview(result.rows, TARGET_CATEGORIES);
    const report = reviewReport(result.rows);
    return {
      editedRows: result.rows,
      aggregated,
      report,
      learned: result.learning.length,
      deleted: result.deleted,
    };
  }

  private async applyImport(rows: readonly ImportReviewRow[]): Promise<void> {
    if (!this.importResult) throw new Error('Nessun import in memoria.');
    const applied = this.applyEditsInternal(rows);
    this.importResult = {
      ...this.importResult,
      rows: applied.editedRows,
      aggregated: applied.aggregated,
      report: applied.report,
    };
    this.send({ type: 'importResult', result: this.importResult });
    const detail = [
      'Categorie aggiornate!',
      applied.deleted > 0 ? `${applied.deleted} righe eliminate.` : '',
      applied.learned > 0 ? `🧠 ${applied.learned} correzioni apprese.` : '',
    ]
      .filter(Boolean)
      .join(' ');
    this.toast('success', detail);
  }

  private async saveImport(rows: readonly ImportReviewRow[]): Promise<void> {
    if (!this.importResult) throw new Error('Nessun import in memoria.');
    const db = await this.ensureDb();
    const applied = this.applyEditsInternal(rows);
    const merged = mergeAggregatedIntoMonthly(db.loadData(), applied.aggregated);
    db.saveData(merged.rows);
    try {
      db.saveTransactions(buildTransactionRecords(applied.editedRows));
    } catch (error) {
      this.output.appendLine(
        `[import] salvataggio transazioni non riuscito: ${(error as Error).message}`,
      );
      this.toast('warn', 'Mesi salvati, ma il salvataggio delle transazioni giornaliere è fallito.');
    }
    this.importResult = null;
    await this.sendDatabase();
    await this.sendMerchantMap();
    const message = [
      'Importazione completata: dati salvati.',
      merged.updated > 0 ? `${merged.updated} mesi aggiornati (incrementale).` : '',
      merged.created > 0 ? `${merged.created} mesi creati.` : '',
      applied.learned > 0 ? `🧠 ${applied.learned} correzioni apprese.` : '',
    ]
      .filter(Boolean)
      .join(' ');
    const latest = [...applied.aggregated].sort(
      (a, b) => a.Year * 12 + a.MonthNum - (b.Year * 12 + b.MonthNum),
    ).at(-1);
    const monthRef = latest ? `${latest.Month} ${latest.Year}` : undefined;
    this.send({ type: 'importSaved', message, monthRef });
    this.toast('success', message);
  }

  private async exportCsv(): Promise<void> {
    const db = await this.ensureDb();
    const base = this.workspaceRoot ?? homedir();
    const target = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.file(join(base, 'budget_database.csv')),
      filters: { CSV: ['csv'] },
      saveLabel: 'Esporta CSV',
    });
    if (!target) return;
    db.exportToCsv(target.fsPath);
    this.toast('success', `CSV esportato: ${target.fsPath}`);
  }

  private async exportMerchants(): Promise<void> {
    const db = await this.ensureDb();
    const entries = db.getMerchantList();
    const base = this.workspaceRoot ?? homedir();
    const target = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.file(join(base, 'merchant_categories.json')),
      filters: { JSON: ['json'] },
      saveLabel: 'Esporta mappatura',
    });
    if (!target) return;
    await vscode.workspace.fs.writeFile(
      target,
      Buffer.from(JSON.stringify(entries, null, 2), 'utf8'),
    );
    this.toast('success', `Mappatura esportata (${entries.length} voci).`);
  }

  private buildChatContext(rows: readonly MonthlyRow[]): string {
    const csv = toCsv(
      BUDGET_COLUMNS,
      rows.map((row) => BUDGET_COLUMNS.map((column) =>
        column === 'Month' ? row.Month : Number(row[column]) || 0,
      )),
    );
    return `
                            SEI UN ESPERTO ANALISTA FINANZIARIO.
                            Analizza i seguenti dati di budget personale (ultimi ${rows.length} mesi).
                            Rispondi in italiano. Sii conciso e diretto. Usa markdown per tabelle o grassetto.

                            ISTRUZIONE IMPORTANTE:
                            Prima di dare la risposta finale, scrivi un blocco riga per riga indicando cosa stai analizzando, iniziando con 'Thinking:'.
                            Esempio:
                            Thinking: Analizzo le entrate degli ultimi 3 mesi...
                            Thinking: Controllo le spese straordinarie...
                            Thinking: Calcolo la media del risparmio...

                            [RISPOSTA FINALE QUI]

                            DATI CSV:
                            ${csv}
                            `;
  }

  private async chat(requestId: string, text: string): Promise<void> {
    if (!text.trim()) return;
    if (this.chatBusy) {
      this.send({ type: 'chatError', requestId, message: 'Attendi la risposta precedente.' });
      return;
    }
    this.chatBusy = true;
    const db = await this.ensureDb();
    const rows = db.loadData();
    this.chatMessages.push({ role: 'user', content: text });
    try {
      const llm = await this.getLlm(true);
      if (!llm) throw new Error('AI non configurata.');
      const system = this.buildChatContext(rows);
      let accumulator = '';
      for await (const chunk of llm.streamChat(system, text)) {
        accumulator += chunk;
        this.send({ type: 'chatChunk', requestId, text: chunk });
      }
      if (!accumulator.trim()) throw new Error('Nessuna risposta ricevuta dal modello.');
      this.chatMessages.push({ role: 'assistant', content: accumulator });
      this.send({ type: 'chatDone', requestId, text: accumulator });
    } catch (error) {
      const message = (error as Error).message;
      this.chatMessages.push({ role: 'assistant', content: `Errore: ${message}` });
      this.send({ type: 'chatError', requestId, message });
    } finally {
      this.chatBusy = false;
    }
  }

  private async addManualMonth(
    year: number,
    month: string,
    _mode: 'increment' | 'create',
    values: Record<string, number>,
  ): Promise<void> {
    const db = await this.ensureDb();
    const rows = db.loadData();
    const monthNum = Math.max(1, (MONTHS_EN as readonly string[]).indexOf(month) + 1);
    const existing = rows.find(
      (row) => Number(row.Year) === Number(year) && (row.Month === month || Number(row.MonthNum) === monthNum),
    );
    if (existing) {
      const bag = existing as unknown as Record<string, number>;
      for (const [column, value] of Object.entries(values)) {
        const allowed = (BUDGET_COLUMNS as readonly string[]).includes(column);
        if (allowed && Number.isFinite(Number(value))) {
          bag[column] = Math.round((Number(bag[column] ?? 0) + Number(value)) * 100) / 100;
        }
      }
      db.saveData(rows);
      this.toast('success', `Dati aggiornati per ${month} ${year}!`);
    } else {
      const row = {} as unknown as Record<string, number | string>;
      row.Year = Number(year);
      row.MonthNum = monthNum;
      row.Month = month;
      for (const column of BUDGET_COLUMNS) {
        if (column === 'Year' || column === 'MonthNum' || column === 'Month') continue;
        row[column] = Math.round((Number(values[column] ?? 0) || 0) * 100) / 100;
      }
      db.saveData([...rows, row as unknown as MonthlyRow]);
      this.toast('success', `Mese ${month} ${year} creato.`);
    }
    await this.sendDatabase();
  }

  private cloudManager(token: string): CloudManager {
    const cfg = this.cloudConfig();
    return new CloudManager({
      token,
      repo: cfg.repo,
      branch: cfg.branch,
      path: cfg.path,
      csvPath: cfg.csvPath,
    });
  }

  private async cloudBackup(): Promise<void> {
    const token = await this.githubToken();
    if (!token) {
      this.toast('error', 'GitHub token mancante. Salvalo nella sezione Cloud Sync.');
      return;
    }
    const db = await this.ensureDb();
    const tempCsv = join(this.context.globalStorageUri.fsPath, 'budget_backup_export.csv');
    db.exportToCsv(tempCsv);
    const csv = existsSync(tempCsv) ? readFileSync(tempCsv, 'utf8') : '';
    try {
      if (existsSync(tempCsv)) unlinkSync(tempCsv);
    } catch {
      // ignore
    }
    const manager = this.cloudManager(token);
    const result = await manager.backup(db.readBytes(), csv);
    this.send({ type: 'cloudResult', action: 'backup', ok: result.ok, message: result.message });
    this.toast(result.ok ? 'success' : 'error', result.message);
    await this.sendCloudState(result.message);
  }

  private async cloudRestore(): Promise<void> {
    const token = await this.githubToken();
    if (!token) {
      this.toast('error', 'GitHub token mancante. Salvalo nella sezione Cloud Sync.');
      return;
    }
    const manager = this.cloudManager(token);
    const result = await manager.restore();
    if (!result.ok || !result.bytes) {
      const seeded = await this.importCloudCsv(manager);
      if (seeded) return;
      this.send({ type: 'cloudResult', action: 'restore', ok: false, message: result.message });
      this.toast('error', result.message);
      return;
    }
    const db = await this.ensureDb();
    db.restoreFromBytes(result.bytes);
    this.invalidateLlm();
    await this.sendDatabase();
    await this.sendMerchantMap();
    const latest = db.loadData()[0];
    if (latest) {
      await this.sendTransactions(`${latest.Month} ${latest.Year}`);
    }
    this.send({
      type: 'cloudResult',
      action: 'restore',
      ok: true,
      message: 'Backup ripristinato. Riapri pure il pannello per aggiornare.',
    });
    this.toast('success', 'Backup ripristinato dal cloud.');
    await this.sendCloudState(result.message);
  }

  private async cloudImportCsv(): Promise<void> {
    const token = await this.githubToken();
    await this.importCloudCsv(this.cloudManager(token));
  }

  private async importCloudCsv(manager: CloudManager): Promise<boolean> {
    const csv = await manager.fetchCsv();
    if (!csv.ok || !csv.text) {
      this.send({ type: 'cloudResult', action: 'csv', ok: false, message: csv.message });
      this.toast('error', csv.message);
      await this.sendCloudState(csv.message);
      return false;
    }
    const db = await this.ensureDb();
    const tempCsv = join(this.context.globalStorageUri.fsPath, 'budget_cloud_seed.csv');
    writeFileSync(tempCsv, csv.text, 'utf8');
    let migrated = 0;
    try {
      migrated = db.migrateFromCsv(tempCsv);
    } finally {
      try {
        unlinkSync(tempCsv);
      } catch {
        // ignore
      }
    }
    const message =
      migrated > 0
        ? `CSV iniziale importato: ${migrated} mesi da ${this.cloudConfig().csvPath}.`
        : 'CSV scaricato, ma il database locale contiene già dati.';
    this.send({ type: 'cloudResult', action: 'csv', ok: migrated > 0, message });
    this.toast(migrated > 0 ? 'success' : 'info', message);
    await this.sendDatabase();
    await this.sendMerchantMap();
    const latest = db.loadData()[0];
    if (latest) await this.sendTransactions(`${latest.Month} ${latest.Year}`);
    await this.sendCloudState(message);
    return migrated > 0;
  }

  private async cloudStatus(): Promise<void> {
    const token = await this.githubToken();
    if (!token) {
      await this.sendCloudState('Token GitHub mancante.');
      return;
    }
    const status = await this.cloudManager(token).status();
    await this.sendCloudState(status.message);
    this.send({ type: 'cloudResult', action: 'status', ok: status.ok, message: status.message });
  }

  async reloadDatabase(): Promise<void> {
    this.db?.close();
    this.db = null;
    this.invalidateLlm();
    const fresh = await this.ensureDb();
    await this.sendDatabase();
    await this.sendMerchantMap();
    const latest = fresh.loadData()[0];
    if (latest) {
      await this.sendTransactions(`${latest.Month} ${latest.Year}`);
    }
    this.toast('info', `Database ricaricato: ${fresh.dbPath}`);
  }

  async broadcastDatabase(): Promise<void> {
    await this.sendDatabase();
  }

  async loadMerchantMap(): Promise<void> {
    await this.sendMerchantMap();
  }

  static sortedRows(rows: readonly MonthlyRow[]): MonthlyRow[] {
    return sortDescending([...rows]);
  }
}
