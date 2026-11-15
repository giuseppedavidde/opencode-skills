import {
  PROVIDER_MODELS,
  type HostMessage,
  type TimeWindow,
  type WebviewMessage,
} from '../types';
import { el } from './dom';
import type { Page, PersistedState, UiContext, UiState } from './context';
import { renderSidebar } from './sidebar';
import { renderDashboard } from './dashboard';
import { invalidateDataDrafts, renderManageData, invalidateMerchantEdits } from './manageData';
import {
  focusMonth,
  invalidateReviewEdits,
  renderManageMonth,
  resetPendingImport,
  updateImportProgress,
} from './manageMonth';
import { renderChat, updateChatStreaming } from './chat';

interface VsCodeApi {
  postMessage(message: WebviewMessage): void;
  getState(): PersistedState | undefined;
  setState(state: PersistedState): void;
}

declare function acquireVsCodeApi(): VsCodeApi;

const api = acquireVsCodeApi();
const persisted = api.getState() ?? {};
const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element mancante');
const root = rootElement;

function parseWindow(value: string | TimeWindow | undefined): TimeWindow {
  if (value === 'All') return 'All';
  const numeric = Number(value);
  return numeric === 3 || numeric === 6 || numeric === 12 || numeric === 24
    ? numeric
    : 12;
}

function initialPage(): Page {
  const page = persisted.page;
  return page === 'dashboard' || page === 'data' || page === 'month' || page === 'chat'
    ? page
    : 'dashboard';
}

const state: UiState = {
  rows: [],
  targets: {},
  dbInfo: {
    dbPath: '',
    dbSizeKb: 0,
    rowCount: 0,
    lastBackupTime: null,
    transactionCount: 0,
    merchantCount: 0,
  },
  transactions: [],
  ai: {
    provider: 'opencode',
    model: 'deepseek-v4-pro',
    keySet: false,
    models: PROVIDER_MODELS.opencode,
    envKeyAvailable: false,
  },
  cloud: {
    enabled: false,
    repo: '',
    branch: 'main',
    path: 'budget.db',
    csvPath: 'budget_database.csv',
    tokenSet: false,
  },
  chat: [],
  defaultWindow: 12,
  page: initialPage(),
  window: parseWindow(persisted.window),
  selectedMonth: persisted.selectedMonth ?? '',
  filters: persisted.filters ?? { investimenti: true, straordinarie: true, capex: false },
  classifyMode: persisted.classifyMode ?? 'hybrid',
  merchant: null,
  importResult: null,
  importProgress: null,
  importError: null,
  cloudStatus: '',
  chatStreaming: null,
  version: '0.1.0',
};

let sidebarElement: HTMLElement | null = null;
let mainElement: HTMLElement | null = null;
let toastBox: HTMLElement | null = null;

function persist(): void {
  api.setState({
    page: state.page,
    window: state.window,
    selectedMonth: state.selectedMonth,
    filters: state.filters,
    classifyMode: state.classifyMode,
  });
}

function toast(level: 'info' | 'warn' | 'error' | 'success', message: string): void {
  if (!toastBox) return;
  const node = el('div', { className: `toast ${level}`, text: message });
  toastBox.append(node);
  while (toastBox.children.length > 5) toastBox.firstElementChild?.remove();
  setTimeout(() => node.remove(), 5000);
}

function renderMain(): void {
  if (!mainElement) return;
  const main = mainElement;
  switch (state.page) {
    case 'data':
      renderManageData(main, ctx);
      if (!state.merchant) api.postMessage({ type: 'loadMerchants' });
      break;
    case 'month':
      renderManageMonth(main, ctx);
      break;
    case 'chat':
      renderChat(main, ctx);
      break;
    case 'dashboard':
    default:
      renderDashboard(main, ctx);
      break;
  }
}

function renderAll(): void {
  if (sidebarElement) renderSidebar(sidebarElement, ctx);
  renderMain();
}

const ctx: UiContext = {
  state,
  post: (message) => api.postMessage(message),
  toast,
  renderMain,
  renderAll,
  persist,
};

function buildShell(): void {
  root.replaceChildren();
  const app = el('div', { className: 'app' });
  sidebarElement = el('aside', { className: 'sidebar', attrs: { id: 'sidebar' } });
  mainElement = el('main', { className: 'main', attrs: { id: 'main' } });
  app.append(sidebarElement, mainElement);
  root.append(app);
  toastBox = el('div', { className: 'toasts', attrs: { id: 'toasts' } });
  document.body.append(toastBox);
}

function handleMessage(message: HostMessage): void {
  switch (message.type) {
    case 'init': {
      const payload = message.payload;
      state.rows = payload.rows;
      state.targets = payload.targets;
      state.dbInfo = payload.dbInfo;
      state.transactions = payload.transactions;
      state.ai = payload.ai;
      state.cloud = payload.cloud;
      state.chat = payload.chat;
      state.defaultWindow = parseWindow(payload.defaultTimeWindow);
      state.version = payload.extensionVersion;
      if (!persisted.window) state.window = state.defaultWindow;
      if (!state.selectedMonth) {
        const first = payload.rows[0];
        state.selectedMonth = first ? `${first.Month} ${first.Year}` : '';
      }
      invalidateDataDrafts();
      invalidateMerchantEdits();
      invalidateReviewEdits();
      renderAll();
      if (state.selectedMonth) {
        const hasTransactions = state.transactions.some(
          (row) => row.month_ref === state.selectedMonth,
        );
        if (!hasTransactions) {
          api.postMessage({ type: 'loadTransactions', monthRef: state.selectedMonth });
        }
      }
      persist();
      break;
    }
    case 'database': {
      state.rows = message.rows;
      state.targets = message.targets;
      state.dbInfo = message.dbInfo;
      invalidateDataDrafts();
      if (!state.rows.some((row) => `${row.Month} ${row.Year}` === state.selectedMonth)) {
        const first = state.rows[0];
        state.selectedMonth = first ? `${first.Month} ${first.Year}` : '';
      }
      renderAll();
      if (state.selectedMonth) {
        api.postMessage({ type: 'loadTransactions', monthRef: state.selectedMonth });
      }
      break;
    }
    case 'transactions':
      state.transactions = message.rows;
      if (state.page === 'dashboard') renderMain();
      break;
    case 'aiConfig':
      state.ai = message.config;
      if (sidebarElement) renderSidebar(sidebarElement, ctx);
      if (state.page === 'chat') renderMain();
      break;
    case 'merchantMap':
      state.merchant = {
        entries: message.entries,
        categories: message.categories,
        count: message.count,
      };
      invalidateMerchantEdits();
      if (state.page === 'data') renderMain();
      break;
    case 'importProgress':
      state.importProgress = { percent: message.percent, message: message.message };
      if (state.page === 'month') updateImportProgress(message.percent, message.message);
      break;
    case 'importResult':
      state.importResult = message.result;
      state.importProgress = { percent: 1, message: 'Analisi completata.' };
      if (state.page === 'month') renderMain();
      toast('success', `Analisi completata: ${message.result.rows.length} transazioni.`);
      break;
    case 'importSaved': {
      state.importResult = null;
      state.importProgress = null;
      state.importError = null;
      resetPendingImport();
      if (message.monthRef) {
        const [month = '', year = ''] = message.monthRef.split(' ');
        focusMonth(Number(year), month);
        state.selectedMonth = message.monthRef;
        state.transactions = [];
      }
      toast('success', message.message);
      if (message.monthRef) {
        persist();
        renderAll();
        api.postMessage({ type: 'loadTransactions', monthRef: message.monthRef });
      } else if (state.page === 'month') {
        renderMain();
      }
      break;
    }
      break;
    case 'importError':
      state.importProgress = null;
      state.importError = message.message;
      toast('error', message.message);
      if (state.page === 'month') renderMain();
      break;
    case 'chatChunk':
      if (state.chatStreaming && state.chatStreaming.requestId === message.requestId) {
        state.chatStreaming.text += message.text;
        if (state.page === 'chat') updateChatStreaming(state.chatStreaming.text);
      }
      break;
    case 'chatDone': {
      const existing = state.chat[state.chat.length - 1];
      if (!existing || existing.role !== 'assistant' || existing.content !== message.text) {
        state.chat.push({ role: 'assistant', content: message.text });
      }
      state.chatStreaming = null;
      if (state.page === 'chat') renderMain();
      break;
    }
    case 'chatError': {
      state.chatStreaming = null;
      state.chat.push({ role: 'assistant', content: `Errore: ${message.message}` });
      toast('error', message.message);
      if (state.page === 'chat') renderMain();
      break;
    }
    case 'chatHistory':
      state.chat = message.messages;
      state.chatStreaming = null;
      if (state.page === 'chat') renderMain();
      break;
    case 'cloudState':
      state.cloud = message.state;
      state.cloudStatus = message.status;
      if (sidebarElement) renderSidebar(sidebarElement, ctx);
      break;
    case 'cloudResult':
      toast(message.ok ? 'success' : 'error', message.message);
      break;
    case 'navigate':
      state.page = message.page;
      persist();
      renderAll();
      break;
    case 'toast':
      toast(message.level, message.message);
      break;
    case 'saved':
      toast('success', message.message);
      break;
    default:
      break;
  }
}

window.addEventListener('message', (event: MessageEvent<HostMessage>) => {
  handleMessage(event.data);
});

buildShell();
renderAll();
api.postMessage({ type: 'ready' });
