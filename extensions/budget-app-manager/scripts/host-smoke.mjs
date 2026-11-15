import Module from 'node:module';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const projectRoot = resolve('.');
const storage = mkdtempSync(join(tmpdir(), 'budget-host-smoke-'));
const workspace = mkdtempSync(join(tmpdir(), 'budget-host-ws-'));
const messages = [];
const commands = new Map();
let webviewReceive = null;
let disposed = false;

function uri(fsPath) {
  return {
    fsPath,
    scheme: 'file',
    path: fsPath,
    toString: () => `file://${fsPath}`,
  };
}

const config = {
  get(key) {
    const values = {
      dbPath: '',
      defaultTimeWindow: '12',
      defaultProvider: 'opencode',
      defaultModel: 'deepseek-v4-pro',
      'cloud.enabled': false,
      'cloud.repo': '',
      'cloud.branch': 'main',
      'cloud.path': 'budget.db',
      'cloud.csvPath': 'budget_database.csv',
    };
    return values[key];
  },
  async update() {},
};

const view = {
  title: 'Budget',
  description: undefined,
  badge: undefined,
  visible: true,
  webview: {
    html: '',
    options: {},
    cspSource: 'vscode-webview://smoke',
    asWebviewUri: (value) => value,
    onDidReceiveMessage(callback) {
      webviewReceive = callback;
      return { dispose() {} };
    },
    async postMessage(message) {
      messages.push(message);
      return true;
    },
  },
  onDidDispose(callback) {
    view.disposeCallback = callback;
    return { dispose() {} };
  },
  onDidChangeVisibility() {
    return { dispose() {} };
  },
  show() {
    view.visible = true;
  },
  dispose() {
    disposed = true;
    view.disposeCallback?.();
  },
};

let viewProvider = null;
let viewResolved = false;

function resolveView() {
  if (viewResolved) return;
  viewResolved = true;
  viewProvider?.resolveWebviewView(view, { subscriptions: [] }, {});
}

const vscodeMock = {
  ViewColumn: { One: 1 },
  ConfigurationTarget: { Global: 1 },
  Uri: {
    file: (value) => uri(value),
    joinPath: (base, ...parts) => uri(join(base.fsPath ?? String(base), ...parts)),
    parse: (value) => uri(value),
  },
  window: {
    createOutputChannel: () => ({ appendLine() {}, dispose() {} }),
    registerWebviewViewProvider: (id, provider) => {
      if (id !== 'budgetApp.dashboardView') throw new Error(`unexpected view id: ${id}`);
      viewProvider = provider;
      return { dispose() {} };
    },
    showOpenDialog: async () => undefined,
    showSaveDialog: async () => undefined,
    showErrorMessage: async () => undefined,
    showWarningMessage: async () => undefined,
    showInformationMessage: async () => undefined,
  },
  workspace: {
    workspaceFolders: [{ uri: uri(workspace) }],
    getConfiguration: () => config,
    onDidChangeConfiguration: () => ({ dispose() {} }),
    fs: { writeFile: async () => {} },
  },
  commands: {
    registerCommand(name, callback) {
      commands.set(name, callback);
      return { dispose() {} };
    },
    async executeCommand(name) {
      if (name === 'budgetApp.dashboardView.focus') resolveView();
      return undefined;
    },
  },
};

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return vscodeMock;
  return originalLoad.call(this, request, parent, isMain);
};

const context = {
  extensionUri: uri(projectRoot),
  extensionPath: projectRoot,
  globalStorageUri: uri(storage),
  subscriptions: [],
  extension: { packageJSON: { version: '0.1.0' } },
  globalState: {
    values: new Map(),
    get(key) {
      return this.values.get(key);
    },
    async update(key, value) {
      this.values.set(key, value);
    },
  },
  secrets: {
    values: new Map(),
    async get(key) {
      return this.values.get(key);
    },
    async store(key, value) {
      this.values.set(key, value);
    },
    async delete(key) {
      this.values.delete(key);
    },
  },
};

try {
  const extension = await import('../dist/extension.js');
  extension.activate(context);

  if (!commands.has('budget.openDashboard')) throw new Error('openDashboard command missing');
  if (!commands.has('budget.importBankStatement')) throw new Error('import command missing');
  if (!commands.has('budget.openChat')) throw new Error('chat command missing');
  if (!viewProvider) throw new Error('webview view provider missing');

  await commands.get('budget.openDashboard')();
  if (!view.webview.html.includes('webview.js')) throw new Error('webview HTML missing script');
  if (!view.webview.html.includes('nonce-')) throw new Error('CSP nonce missing');
  if (!view.webview.html.includes('plotly.min.js')) throw new Error('plotly missing');
  if (typeof webviewReceive !== 'function') throw new Error('message handler missing');

  await webviewReceive({ type: 'ready' });
  const init = messages.find((message) => message.type === 'init');
  if (!init) throw new Error(`init not sent; messages=${messages.map((m) => m.type)}`);
  if (init.payload.dbInfo.dbPath !== join(storage, 'budget.db')) {
    throw new Error(`unexpected db path: ${init.payload.dbInfo.dbPath}`);
  }
  if (init.payload.dbInfo.merchantCount < 100) {
    throw new Error(`merchant seed not loaded: ${init.payload.dbInfo.merchantCount}`);
  }

  const row = {
    Year: 2025,
    MonthNum: 1,
    Month: 'January',
    Stipendio: 3000,
    'Reddito aggiuntivo': 0,
    Alimentari: 200,
    Bancomat: 0,
    Carburante: 0,
    'Cene, Pranzo': 0,
    'Immobili (affitto, mutuo, tasse, assicurazione)': 0,
    Investimenti: 0,
    Medicinali: 0,
    'PayPal + Abbonamenti': 0,
    'Spese Straordinarie': 0,
    'Acquisto Auto': 0,
    Trasporti: 0,
    'Viaggi, Divertimento': 0,
  };
  await webviewReceive({ type: 'saveMonthly', rows: [row], deleted: [] });
  const database = [...messages].reverse().find((message) => message.type === 'database');
  if (!database || database.rows.length !== 1) throw new Error('saveMonthly did not persist');

  await webviewReceive({ type: 'saveTargets', targets: { Alimentari: 250 } });
  const targetDb = [...messages].reverse().find((message) => message.type === 'database');
  if (targetDb.targets.Alimentari !== 250) throw new Error('targets not persisted');

  await webviewReceive({ type: 'loadMerchants' });
  const merchantMap = messages.find((message) => message.type === 'merchantMap');
  if (!merchantMap || merchantMap.count < 100) throw new Error('merchant map not sent');

  const csv = 'Buchungsdatum;Betrag;Kategorie;Name\n2026-10-15;-25,50;Lebensmittel;BILLA\n';
  const base64Csv = Buffer.from(csv, 'utf8').toString('base64');
  await webviewReceive({
    type: 'importStatement',
    fileName: 'statement.csv',
    dataBase64: base64Csv,
    classifyMode: 'hybrid',
  });
  const firstImport = [...messages].reverse().find((message) => message.type === 'importResult');
  if (!firstImport) {
    const failure = [...messages].reverse().find((message) => message.type === 'importError');
    throw new Error(`import failed: ${failure?.message ?? 'no result'}`);
  }
  await webviewReceive({
    type: 'importStatement',
    fileName: 'statement-2.csv',
    dataBase64: base64Csv,
    classifyMode: 'hybrid',
  });
  const imported = [...messages].reverse().find((message) => message.type === 'importResult');
  if (imported.result.rows.length !== 2) {
    throw new Error(`cumulative review rows: ${imported.result.rows.length}`);
  }
  if (!imported.result.sourceName.includes('+')) {
    throw new Error(`sourceName not cumulative: ${imported.result.sourceName}`);
  }
  await webviewReceive({ type: 'saveImport', rows: imported.result.rows });
  const saved = [...messages].reverse().find((message) => message.type === 'importSaved');
  if (!saved) throw new Error('importSaved missing');
  if (saved.monthRef !== 'October 2026') throw new Error(`monthRef: ${saved.monthRef}`);
  const savedDb = [...messages].reverse().find((message) => message.type === 'database');
  const october = savedDb.rows.find((row) => row.Month === 'October' && Number(row.Year) === 2026);
  if (!october) throw new Error('October 2026 not persisted');
  if (!(Number(october[imported.result.rows[0].newCategory]) > 0)) {
    throw new Error(`category not aggregated: ${imported.result.rows[0].newCategory}`);
  }
  if (!(savedDb.dbInfo.transactionCount >= 1)) throw new Error('transactions not persisted');

  view.dispose();
  if (!disposed) throw new Error('view dispose failed');
  extension.deactivate();
  console.log(
    `host smoke ok: init rows=${init.payload.rows.length}, seed=${init.payload.dbInfo.merchantCount}, messages=${messages.length}`,
  );
} finally {
  Module._load = originalLoad;
  rmSync(storage, { recursive: true, force: true });
  rmSync(workspace, { recursive: true, force: true });
}
