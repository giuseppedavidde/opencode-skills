/**
 * Loads the built extension bundle with a mocked `vscode` module.
 * It proves that activation works, that all commands are registered, that the
 * sidebar webview view provider is registered for `ibkrHistory.panel` with
 * retainContextWhenHidden, that the editor panel and the view both get the same
 * nonce-based CSP HTML, and that no secret reaches any webview.
 */
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const work = mkdtempSync(join(tmpdir(), 'ibkr-smoke-'));
const stubDir = join(work, 'node_modules', 'vscode');
mkdirSync(stubDir, { recursive: true });

writeFileSync(join(stubDir, 'package.json'), JSON.stringify({ name: 'vscode', version: '1.90.0', main: 'index.js' }));
writeFileSync(
  join(stubDir, 'index.js'),
  `
const state = { logs: [], webviews: [], viewProviders: new Map(), config: {} };
const commands = new Map();

function createWebview() {
  const ws = { html: '', messages: [], onMessage: null };
  state.webviews.push(ws);
  return {
    ws,
    webview: {
      cspSource: 'vscode-resource://test',
      get html() { return ws.html; },
      set html(value) { ws.html = value; },
      asWebviewUri: (uri) => uri,
      onDidReceiveMessage: (callback) => { ws.onMessage = callback; return { dispose() {} }; },
      postMessage: async (message) => { ws.messages.push(message); return true; }
    }
  };
}

class Uri {
  constructor(value) { this.fsPath = value; this.path = value; this.scheme = 'file'; }
  static file(value) { return new Uri(value); }
  static parse(value) { return new Uri(value); }
  static joinPath(base, ...parts) { return new Uri([base.fsPath, ...parts].join('/')); }
  toString() { return this.fsPath; }
}

class Disposable {
  constructor(fn) { this._fn = fn; }
  static from(...items) {
    return new Disposable(() => { for (const item of items) { if (item && item.dispose) { item.dispose(); } } });
  }
  dispose() { if (this._fn) { this._fn(); this._fn = undefined; } }
}

module.exports = {
  __state: state,
  __commands: commands,
  __viewProviders: state.viewProviders,
  Uri,
  Disposable,
  ViewColumn: { One: 1 },
  ProgressLocation: { Notification: 15 },
  env: { openExternal: async () => true },
  commands: {
    registerCommand(name, callback) { commands.set(name, callback); return { dispose() {} }; },
    executeCommand: async () => undefined
  },
  window: {
    createOutputChannel() {
      return { appendLine: (line) => state.logs.push(line), dispose() {} };
    },
    createWebviewPanel() {
      const { webview } = createWebview();
      return { webview, onDidDispose: () => ({ dispose() {} }), reveal() {}, dispose() {} };
    },
    registerWebviewViewProvider(viewType, provider, options) {
      state.viewProviders.set(viewType, { provider, options });
      return { dispose() {} };
    },
    showErrorMessage: async () => undefined,
    showWarningMessage: async () => undefined,
    showInformationMessage: async () => undefined,
    showSaveDialog: async () => undefined,
    withProgress: async (_options, task) => task({ report() {} }, { onCancellationRequested: () => ({ dispose() {} }) })
  },
  workspace: {
    getConfiguration: () => ({
      get: (key, fallback) => (Object.prototype.hasOwnProperty.call(state.config, key) ? state.config[key] : fallback),
      update: async () => undefined
    }),
    fs: { writeFile: async () => undefined }
  },
  lm: {
    selectChatModels: async () => [
      { id: 'glm-5.3', name: 'GLM 5.3', vendor: 'opencode-go', family: 'glm', version: '1', maxInputTokens: 128000 },
      { id: 'deepseek-v4.1-flash', name: 'DeepSeek V4.1 Flash', vendor: 'opencode-go', family: 'deepseek', version: '1', maxInputTokens: 128000 }
    ].sort((left, right) => (left.name < right.name ? -1 : 1))
  },
  LanguageModelChatMessage: {
    User(content) { return { role: 1, content }; },
    Assistant(content) { return { role: 2, content }; }
  },
  CancellationTokenSource: class {
    constructor() { this.token = { isCancellationRequested: false, onCancellationRequested: () => ({ dispose() {} }) }; }
    cancel() { this.token.isCancellationRequested = true; }
    dispose() {}
  }
};
`
);

copyFileSync(join(root, 'dist', 'extension.cjs'), join(work, 'extension.cjs'));

const require = createRequire(import.meta.url);
const bundled = require(join(work, 'extension.cjs'));
const vscodeStub = require(join(stubDir, 'index.js'));
const state = vscodeStub.__state;

function createWebviewState() {
  const ws = { html: '', messages: [], onMessage: null };
  return {
    ws,
    webview: {
      cspSource: 'vscode-resource://test',
      get html() {
        return ws.html;
      },
      set html(value) {
        ws.html = value;
      },
      asWebviewUri: (uri) => uri,
      onDidReceiveMessage: (callback) => {
        ws.onMessage = callback;
        return { dispose() {} };
      },
      postMessage: async (message) => {
        ws.messages.push(message);
        return true;
      }
    }
  };
}

function assertCspHtml(html, label) {
  assert.match(html, /Content-Security-Policy/, `${label} must carry a CSP meta tag`);
  assert.match(html, /default-src 'none'/, `${label} must deny by default`);
  assert.match(html, /script-src 'nonce-[A-Za-z0-9+/=]+'/, `${label} must restrict scripts to the nonce`);
  assert.equal(/<script[^>]+src="https?:/.test(html), false, `${label} must not load a remote script`);
  assert.match(html, /<script nonce="[A-Za-z0-9+/=]+" src="[^"]*media\/webview\.js">/, `${label} must load media/webview.js`);
  assert.match(html, /<link rel="stylesheet" href="[^"]*media\/webview\.css" \/>/, `${label} must load media/webview.css`);
  const nonce = /script-src 'nonce-([A-Za-z0-9+/=]+)'/.exec(html)?.[1];
  assert.ok(nonce, `${label} must have a nonce`);
  assert.match(html, new RegExp(`<script nonce="${nonce.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`), `${label} script tag must use the CSP nonce`);
}

function assertChatCspHtml(html, label) {
  assert.match(html, /Content-Security-Policy/, `${label} must carry a CSP meta tag`);
  assert.match(html, /default-src 'none'/, `${label} must deny by default`);
  assert.match(html, /script-src 'nonce-[A-Za-z0-9+/=]+'/, `${label} must restrict scripts to the nonce`);
  assert.equal(/<script[^>]+src="https?:/.test(html), false, `${label} must not load a remote script`);
  assert.match(html, /<script nonce="[A-Za-z0-9+/=]+" src="[^"]*media\/chat\.js">/, `${label} must load media/chat.js`);
  assert.match(html, /<link rel="stylesheet" href="[^"]*media\/chat\.css" \/>/, `${label} must load media/chat.css`);
  assert.match(
    html,
    /Portfolio data is sent to the VS Code language model provider\. Option prices, when enabled, come from yfinance\./,
    `${label} must show the privacy notice`
  );
  assert.equal(html.includes('https://cdn'), false, `${label} must not reference a CDN`);
}

assert.equal(typeof bundled.activate, 'function', 'activate must be exported');
assert.equal(typeof bundled.deactivate, 'function', 'deactivate must be exported');

const storedToken = '528191644107458877539776';
const secrets = new Map([
  ['ibkrHistory.flexToken', storedToken],
  ['ibkrHistory.queryId', '800969']
]);
const context = {
  subscriptions: [],
  extensionUri: vscodeStub.Uri.file(work),
  globalStorageUri: vscodeStub.Uri.file(join(work, 'globalStorage')),
  secrets: {
    get: async (key) => secrets.get(key),
    store: async (key, value) => void secrets.set(key, value),
    delete: async (key) => void secrets.delete(key)
  },
  globalState: {
    get: (_key, fallback) => fallback,
    update: async () => undefined
  }
};

bundled.activate(context);

const expected = [
  'ibkrHistory.open',
  'ibkrHistory.fetch',
  'ibkrHistory.exportCsv',
  'ibkrHistory.copyDiagnostics',
  'ibkrHistory.clearCredentials',
  'ibkrHistory.openChat',
  'ibkrHistory.analyzeWithTradeAgent',
  'ibkrHistory.setChatApiKey',
  'ibkrHistory.clearChatApiKey',
  'ibkrHistory.resetChatConsent'
];
for (const name of expected) {
  assert.ok(vscodeStub.__commands.has(name), `command ${name} must be registered`);
}

const viewEntry = vscodeStub.__viewProviders.get('ibkrHistory.panel');
assert.ok(viewEntry, 'registerWebviewViewProvider must be called with ibkrHistory.panel');
assert.equal(viewEntry.options?.webviewOptions?.retainContextWhenHidden, true, 'the sidebar view must retain context when hidden');
assert.equal(typeof viewEntry.provider.resolveWebviewView, 'function', 'the provider must resolve webview views');

await vscodeStub.__commands.get('ibkrHistory.open')();
const panelWs = state.webviews[0];
assert.ok(panelWs, 'the open command must create the editor panel webview');
assertCspHtml(panelWs.html, 'the editor panel HTML');

assert.equal(typeof panelWs.onMessage, 'function', 'the panel must listen to webview messages');
await panelWs.onMessage({ type: 'ready' });
await new Promise((resolve) => setTimeout(resolve, 20));

const stateMessage = panelWs.messages.find((message) => message.type === 'state');
assert.ok(stateMessage, 'the panel must answer ready with a state message');
assert.equal(stateMessage.settings.hasToken, true);
assert.equal(stateMessage.settings.hasQueryId, true);
assert.equal(stateMessage.settings.queryIdMasked.includes('800969'), false, 'the full query id must not be sent');
assert.equal(stateMessage.deadlineMs, 900000, 'the retry deadline must reach the webview');
assert.equal(stateMessage.maxAttempts, 120, 'the retry attempt budget must reach the webview');

const sidebar = createWebviewState();
viewEntry.provider.resolveWebviewView({
  webview: sidebar.webview,
  show() {},
  onDidDispose: () => ({ dispose() {} })
});
assertCspHtml(sidebar.ws.html, 'the sidebar view HTML');
assert.equal(typeof sidebar.ws.onMessage, 'function', 'the sidebar view must listen to webview messages');
await sidebar.ws.onMessage({ type: 'ready' });
await new Promise((resolve) => setTimeout(resolve, 20));
const sidebarState = sidebar.ws.messages.find((message) => message.type === 'state');
assert.ok(sidebarState, 'the sidebar view must answer ready with a state message');
assert.equal(sidebarState.settings.hasToken, true);
assert.equal(sidebarState.settings.queryIdMasked.includes('800969'), false, 'the full query id must not reach the sidebar view');

const chatEntry = vscodeStub.__viewProviders.get('ibkrHistory.chat');
assert.ok(chatEntry, 'registerWebviewViewProvider must be called with ibkrHistory.chat');
assert.equal(chatEntry.options?.webviewOptions?.retainContextWhenHidden, true, 'the chat view must retain context when hidden');
assert.equal(typeof chatEntry.provider.resolveWebviewView, 'function', 'the chat provider must resolve webview views');

const chat = createWebviewState();
chatEntry.provider.resolveWebviewView({
  webview: chat.webview,
  show() {},
  onDidDispose: () => ({ dispose() {} })
});
assertChatCspHtml(chat.ws.html, 'the chat view HTML');
assert.equal(typeof chat.ws.onMessage, 'function', 'the chat view must listen to webview messages');
await chat.ws.onMessage({ type: 'ready' });
await new Promise((resolve) => setTimeout(resolve, 20));

const chatState = chat.ws.messages.find((message) => message.type === 'state');
assert.ok(chatState, 'the chat view must answer ready with a state message');
assert.equal(chatState.backend, 'lm', 'the default backend is the VS Code language model API');
assert.deepEqual(
  chatState.models.map((model) => model.id),
  ['deepseek-v4.1-flash', 'glm-5.3'],
  'the lm dropdown is the dynamic vscode.lm list, sorted by label'
);
assert.match(chatState.notice, /VS Code language model provider/, 'the notice follows the lm backend');
assert.equal(typeof chatState.hasApiKey, 'boolean');
const contextMessage = chat.ws.messages.find((message) => message.type === 'context');
assert.ok(contextMessage, 'the chat view must publish the portfolio context');
assert.equal(contextMessage.available, false, 'no dataset exists before a fetch');

// The http backend keeps the static fallback list and the opencode.ai notice.
state.config['chat.backend'] = 'http';
await chatEntry.provider.refreshState();
await new Promise((resolve) => setTimeout(resolve, 20));
const httpState = chat.ws.messages.filter((message) => message.type === 'state').at(-1);
assert.ok(httpState, 'the http backend must post a state message');
assert.equal(httpState.backend, 'http');
assert.equal(httpState.models.length, 15, 'the http dropdown carries the 15 opencode-go models');
assert.match(httpState.notice, /opencode\.ai/, 'the notice follows the http backend');
delete state.config['chat.backend'];

const serialised = JSON.stringify([...panelWs.messages, ...sidebar.ws.messages, ...chat.ws.messages]);
assert.equal(serialised.includes(storedToken), false, 'the Flex token must never reach a webview');
assert.equal(serialised.includes('800969'), false, 'the full query id must never reach a webview');
assert.equal(state.logs.join('\n').includes(storedToken), false, 'the Flex token must never be logged');

bundled.deactivate();
console.log(
  `smoke OK: ${expected.length} commands, sidebar and chat views registered (retainContextWhenHidden), CSP nonce in panel, view and chat, ` +
    `dynamic lm models plus the 15 http fallback models, retry defaults wired, no secrets in ` +
    `${panelWs.messages.length + sidebar.ws.messages.length + chat.ws.messages.length} messages`
);
