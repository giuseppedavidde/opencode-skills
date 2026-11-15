import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  runScripts: 'outside-only',
  pretendToBeVisual: true,
  url: 'https://example.test/',
});
const { window } = dom;
const posted = [];
window.acquireVsCodeApi = () => ({
  postMessage: (message) => posted.push(message),
  getState: () => undefined,
  setState: () => {},
});
window.Plotly = { react: async () => ({}), purge: () => {} };
window.confirm = () => true;
const errors = [];
window.addEventListener('error', (event) => errors.push(event.error ?? event.message));
window.addEventListener('unhandledrejection', (event) => errors.push(event.reason));

window.eval(readFileSync('dist/webview.js', 'utf8'));

const baseRow = {
  Year: 2025,
  MonthNum: 1,
  Month: 'January',
  Stipendio: 3000,
  'Reddito aggiuntivo': 0,
  Alimentari: 300,
  Bancomat: 0,
  Carburante: 50,
  'Cene, Pranzo': 100,
  'Immobili (affitto, mutuo, tasse, assicurazione)': 1200,
  Investimenti: 400,
  Medicinali: 0,
  'PayPal + Abbonamenti': 30,
  'Spese Straordinarie': 0,
  'Acquisto Auto': 0,
  Trasporti: 20,
  'Viaggi, Divertimento': 0,
};
const payload = {
  rows: [
    { ...baseRow, Year: 2025, MonthNum: 2, Month: 'February' },
    { ...baseRow },
  ],
  targets: { Alimentari: 350 },
  dbInfo: {
    dbPath: '/tmp/budget.db',
    dbSizeKb: 12,
    rowCount: 2,
    lastBackupTime: null,
    transactionCount: 0,
    merchantCount: 1,
  },
  transactions: [],
  ai: {
    provider: 'opencode',
    model: 'deepseek-v4-pro',
    keySet: true,
    models: ['deepseek-v4-pro'],
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
  defaultTimeWindow: '12',
  chat: [],
  extensionVersion: '0.1.0',
};

const send = (data) => window.dispatchEvent(new window.MessageEvent('message', { data }));
const bodyText = () => window.document.body.textContent ?? '';
const clickNav = (label) => {
  const button = [...window.document.querySelectorAll('button.nav-item')].find((node) =>
    (node.textContent ?? '').includes(label),
  );
  if (!button) throw new Error(`nav button not found: ${label}`);
  button.click();
};

send({ type: 'init', payload });
if (!bodyText().includes('Dashboard')) throw new Error('Dashboard did not render');
if (!bodyText().includes('PATRIMONIO TOTALE PROIETTATO')) throw new Error('KPI cards missing');

clickNav('Gestione Dati');
if (!bodyText().includes('Budget Mensile')) throw new Error('Manage data did not render');
if (!bodyText().includes('Target Mensili')) throw new Error('Targets editor missing');

clickNav('Gestione Mese');
if (!bodyText().includes('Importa da Estratto Conto')) throw new Error('Import panel missing');
if (!bodyText().includes('Gestione manuale del mese')) throw new Error('Manual month form missing');
if (!bodyText().includes('Mese esistente')) throw new Error('Existing month not detected in manual form');
if (!bodyText().includes('Valori attuali di February 2025')) throw new Error('Existing month values missing');

send({
  type: 'importResult',
  result: {
    rows: [
      {
        index: 0,
        date: '2025-01-15',
        description: 'BILLA DANKT 1234',
        amount: -25.5,
        originalCategory: 'Unkategorisiert',
        aiCategory: 'Alimentari',
        proposedCategory: 'Alimentari',
        newCategory: 'Alimentari',
        deleted: false,
        stdName: 'BILLA',
        stdType: '',
        year: 2025,
        monthNum: 1,
        month: 'January',
      },
    ],
    aggregated: [
      {
        Year: 2025,
        MonthNum: 1,
        Month: 'January',
        values: { Alimentari: 25.5 },
        totaleEntrate: 0,
        totaleUscite: 25.5,
        redditoMenoSpese: -25.5,
        risparmioPct: 0,
      },
    ],
    report: '| Date | Description |\n|---|---|\n| 15.01.2025 | BILLA |',
    stats: { mode: 'hybrid', llmSent: 1, llmMapped: 1, llmFailed: 0, errors: [] },
    categoryOptions: ['Alimentari', 'Escluso'],
    sourceName: 'statement.csv',
  },
});
if (!bodyText().includes('Revisione Categorizzazione')) throw new Error('Review table missing');
if (!bodyText().includes('Totali Mensili')) throw new Error('Aggregated preview missing');

send({
  type: 'importResult',
  result: {
    rows: [
      {
        index: 0,
        date: '2025-02-03',
        description: 'HOFER 5678',
        amount: -12,
        originalCategory: 'Lebensmittel',
        aiCategory: 'Alimentari',
        proposedCategory: 'Alimentari',
        newCategory: 'Alimentari',
        deleted: false,
        stdName: 'HOFER',
        stdType: '',
        year: 2025,
        monthNum: 2,
        month: 'February',
      },
    ],
    aggregated: [
      {
        Year: 2025,
        MonthNum: 2,
        Month: 'February',
        values: { Alimentari: 12 },
        totaleEntrate: 0,
        totaleUscite: 12,
        redditoMenoSpese: -12,
        risparmioPct: 0,
      },
    ],
    report: 'second file',
    stats: { mode: 'hybrid', llmSent: 1, llmMapped: 1, llmFailed: 0, errors: [] },
    categoryOptions: ['Alimentari', 'Escluso'],
    sourceName: 'statement-2.csv',
  },
});
const reviewRows = window.document.querySelectorAll('table.editable tbody tr');
if (reviewRows.length !== 1) throw new Error(`review rows after second import: ${reviewRows.length}`);

const saveButton = [...window.document.querySelectorAll('button')].find((node) =>
  (node.textContent ?? '').includes('Conferma e Salva'),
);
if (!saveButton) throw new Error('save button missing');
saveButton.click();
if (posted.some((message) => message.type === 'saveImport')) throw new Error('save must need confirmation');
if (!(saveButton.textContent ?? '').includes('Conferma salvataggio')) throw new Error('confirmation prompt missing');
saveButton.click();
const saveMessage = posted.find((message) => message.type === 'saveImport');
if (!saveMessage) throw new Error('saveImport not posted after confirmation');
if (saveMessage.rows.length !== 1) throw new Error(`saveImport rows: ${saveMessage.rows.length}`);


clickNav('Assistant AI');
if (!bodyText().includes('Financial Assistant')) throw new Error('Chat did not render');
const input = window.document.getElementById('chat-input');
input.value = 'Analizza i miei mesi';
const sendButton = [...window.document.querySelectorAll('button')].find(
  (node) => node.textContent === 'Invia',
);
sendButton.click();
if (!posted.some((message) => message.type === 'chatSend')) throw new Error('chatSend not posted');
send({ type: 'chatChunk', requestId: posted.find((m) => m.type === 'chatSend').requestId, text: '**Ciao** dal' });
send({ type: 'chatChunk', requestId: posted.find((m) => m.type === 'chatSend').requestId, text: ' modello' });
send({ type: 'chatDone', requestId: posted.find((m) => m.type === 'chatSend').requestId, text: '**Ciao** dal modello' });
if (!bodyText().includes('Ciao dal modello')) throw new Error('Streaming chat did not render');

send({ type: 'merchantMap', entries: [], categories: ['Alimentari'], count: 0 });
send({ type: 'cloudState', state: payload.cloud, status: 'ok' });
send({ type: 'toast', level: 'info', message: 'test toast' });

if (errors.length > 0) {
  throw new Error(`webview errors: ${errors.map((error) => String(error)).join(' | ')}`);
}
const types = [...new Set(posted.map((message) => message.type))].sort();
console.log(`webview smoke ok; posted: ${types.join(', ')}`);
