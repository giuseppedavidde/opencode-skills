import {
  CAPEX_COLUMNS,
  EXPENSE_COLUMNS,
  INCOME_COLUMNS,
  MONTHS_EN,
  UNCLASSIFIED_PLACEHOLDER,
  type AggregatedMonth,
  type ImportResultPayload,
  type ImportReviewRow,
} from '../types';
import { arrayBufferToBase64, el, fmtEur, fmtPct, markdownToHtml, clear, confirmThen } from './dom';
import type { UiContext } from './context';

let pendingFile: { name: string; base64: string } | null = null;
let reviewEdits = new Map<number, { newCategory: string; deleted: boolean }>();
let manualValues: Record<string, number> = {};
let manualYear = new Date().getFullYear();
let manualMonth: string = MONTHS_EN[new Date().getMonth()] ?? 'January';
let manualInitialized = false;

export function resetPendingImport(): void {
  pendingFile = null;
  reviewEdits = new Map();
}

export function invalidateReviewEdits(): void {
  reviewEdits = new Map();
}

const MONTH_NUMBERS: Record<string, number> = Object.fromEntries(
  MONTHS_EN.map((month, index) => [month.toLowerCase(), index + 1]),
);

export function monthNumberOf(month: string): number {
  const clean = month.trim().toLowerCase();
  if (MONTH_NUMBERS[clean]) return MONTH_NUMBERS[clean];
  const prefix = clean.slice(0, 3);
  const match = Object.keys(MONTH_NUMBERS).find((name) => name.startsWith(prefix));
  return match ? MONTH_NUMBERS[match] : 0;
}

export function findMonthRow(
  rows: readonly { Year: string | number; MonthNum: string | number; Month: string }[],
  year: number,
  month: string,
): (typeof rows)[number] | undefined {
  const wanted = monthNumberOf(month);
  const wantedName = month.trim().toLowerCase();
  return rows.find((row) => {
    if (Number(row.Year) !== Number(year)) return false;
    if (wanted && Number(row.MonthNum) === wanted) return true;
    const name = String(row.Month ?? '').trim().toLowerCase();
    return name === wantedName || (name.slice(0, 3) === wantedName.slice(0, 3) && name.length > 0);
  });
}

export function focusMonth(year: number, month: string): void {
  manualInitialized = true;
  manualYear = Number(year);
  manualMonth = month;
  manualValues = {};
}

function latestMonth(rows: readonly { Year: string | number; MonthNum: string | number; Month: string }[]): {
  year: number;
  month: string;
} | null {
  if (rows.length === 0) return null;
  const sorted = [...rows].sort(
    (a, b) => Number(b.Year) * 12 + Number(b.MonthNum) - (Number(a.Year) * 12 + Number(a.MonthNum)),
  );
  const first = sorted[0];
  if (!first) return null;
  return { year: Number(first.Year), month: String(first.Month) };
}

function card(title: string, subtitle?: string): { section: HTMLElement; body: HTMLElement } {
  const section = el('section', { className: 'card' });
  section.append(
    el('div', { className: 'card-head' }, [
      el('h2', { text: title }),
      subtitle ? el('p', { className: 'muted', text: subtitle }) : null,
    ]),
  );
  const body = el('div', { className: 'card-body' });
  section.append(body);
  return { section, body };
}

function numberInput(value: number, onChange: (value: number) => void, step = '0.01'): HTMLInputElement {
  const input = el('input', {
    className: 'control cell-input',
    attrs: { type: 'number', step, value: String(Number.isFinite(value) ? value : 0) },
  }) as HTMLInputElement;
  input.addEventListener('change', () => onChange(Number(input.value) || 0));
  return input;
}

async function readFile(file: File, ctx: UiContext): Promise<void> {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith('.csv') && !lower.endsWith('.pdf')) {
    ctx.toast('warn', 'Formato non supportato: usa CSV o PDF.');
    return;
  }
  const buffer = await file.arrayBuffer();
  pendingFile = { name: file.name, base64: arrayBufferToBase64(buffer) };
  ctx.renderMain();
}

function buildEditedRows(result: ImportResultPayload): ImportReviewRow[] {
  return result.rows.map((row) => {
    const edit = reviewEdits.get(row.index);
    return {
      ...row,
      newCategory: edit?.newCategory ?? row.newCategory,
      deleted: edit?.deleted ?? false,
    };
  });
}

function aggregatedTable(months: readonly AggregatedMonth[]): HTMLElement {
  const wrapper = el('div', { className: 'table-scroll' });
  const table = el('table', { className: 'data-table' });
  const head = el('thead');
  const headRow = el('tr');
  for (const label of ['Anno', 'Mese', 'Entrate', 'Uscite', 'Netto', 'Risparmio %']) {
    headRow.append(el('th', { text: label }));
  }
  head.append(headRow);
  const body = el('tbody');
  for (const month of months) {
    const tr = el('tr');
    tr.append(
      el('td', { text: String(month.Year) }),
      el('td', { text: month.Month }),
      el('td', { text: fmtEur(month.totaleEntrate) }),
      el('td', { text: fmtEur(month.totaleUscite) }),
      el('td', { text: fmtEur(month.redditoMenoSpese) }),
      el('td', { text: fmtPct(month.risparmioPct) }),
    );
    body.append(tr);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function renderManageMonth(root: HTMLElement, ctx: UiContext): void {
  clear(root);
  const { state } = ctx;
  const modeLabel =
    state.classifyMode === 'llm_only'
      ? '🧠 Solo AI (forza LLM su tutte)'
      : '🔀 Ibrida (negozi + AI)';

  root.append(
    el('div', { className: 'page-head' }, [
      el('div', {}, [
        el('h1', { text: '➕ Gestione Mese' }),
        el('p', {
          className: 'muted',
          text: `Modalità di classificazione attiva: ${modeLabel}. Cambiala nella sidebar (AI Configuration).`,
        }),
      ]),
    ]),
  );

  // Import panel
  const importCard = card(
    '📂 Importa da Estratto Conto Banca (AI)',
    'Carica il file della banca (CSV o PDF). L’AI estrarrà e categorizzerà le spese.',
  );
  const fileInput = el('input', { className: 'hidden', attrs: { type: 'file', accept: '.csv,.pdf' } }) as HTMLInputElement;
  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) void readFile(file, ctx);
  });

  const dropZone = el('div', { className: 'drop-zone' }, [
    el('div', { className: 'drop-icon', text: '📄' }),
    el('div', { className: 'drop-title', text: 'Trascina qui il file CSV o PDF' }),
    el('div', { className: 'muted', text: pendingFile ? `Selezionato: ${pendingFile.name}` : 'oppure scegli un file dal disco' }),
  ]);
  const browse = el('button', { className: 'btn', text: 'Sfoglia file', attrs: { type: 'button' } });
  browse.addEventListener('click', () => fileInput.click());
  dropZone.append(browse);
  dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropZone.classList.add('drag');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
  dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropZone.classList.remove('drag');
    const file = event.dataTransfer?.files?.[0];
    if (file) void readFile(file, ctx);
  });

  const analyze = el('button', {
    className: 'btn primary',
    text: '🚀 Analizza e Categorizza',
    attrs: { type: 'button', ...(pendingFile ? {} : { disabled: 'true' }) },
  });
  analyze.addEventListener('click', () => {
    if (!pendingFile) {
      ctx.toast('warn', 'Seleziona prima un file.');
      return;
    }
    state.importError = null;
    state.importProgress = { percent: 0, message: 'Avvio analisi...' };
    ctx.post({
      type: 'importStatement',
      fileName: pendingFile.name,
      dataBase64: pendingFile.base64,
      classifyMode: state.classifyMode,
    });
    ctx.renderMain();
  });

  const progress = el('div', {
    className: `progress import ${state.importProgress ? '' : 'hidden'}`,
    attrs: { id: 'import-progress' },
  }, [
    el('div', {
      className: 'progress-bar',
      attrs: {
        id: 'import-progress-bar',
        style: `width:${Math.round((state.importProgress?.percent ?? 0) * 100)}%`,
      },
    }),
    el('span', {
      className: 'progress-text',
      text: state.importProgress?.message ?? '',
      attrs: { id: 'import-progress-text' },
    }),
  ]);
  if (state.importProgress) progress.classList.remove('hidden');

  importCard.body.append(
    dropZone,
    fileInput,
    el('div', { className: 'button-row' }, [analyze]),
    progress,
  );
  if (state.importError) {
    importCard.body.append(el('div', { className: 'alert error', text: state.importError }));
  }
  root.append(importCard.section);

  // Review
  if (state.importResult) {
    const result = state.importResult;
    const reviewCard = card(
      '🔍 Revisione Categorizzazione (cumulativa)',
      `File: ${result.sourceName}. Gli import successivi si sommano qui finché non salvi.`,
    );
    reviewCard.body.append(
      el('div', { className: 'alert info' }, [
        el('strong', { text: '🤖 Categorizzazione AI — ' }),
        el('span', {
          text: `${result.stats.llmSent} inviate all'AI, ${result.stats.llmMapped} categorizzate, ${result.stats.llmFailed} non categorizzate.`,
        }),
      ]),
    );
    if (result.stats.llmFailed > 0 || result.stats.errors.length > 0) {
      reviewCard.body.append(
        el('div', { className: 'alert warn' }, [
          el('div', {
            text: `⚠️ ${result.stats.llmFailed} transazioni non categorizzate dall'AI.`,
          }),
          el('div', {
            className: 'muted',
            text: result.stats.errors.length > 0 ? result.stats.errors.join(' | ') : 'Errore sconosciuto',
          }),
        ]),
      );
    }

    const options = [...result.categoryOptions];
    if (!options.includes(UNCLASSIFIED_PLACEHOLDER)) options.push(UNCLASSIFIED_PLACEHOLDER);
    const reviewScroll = el('div', { className: 'table-scroll tall' });
    const reviewTable = el('table', { className: 'data-table editable' });
    const thead = el('thead');
    const headRow = el('tr');
    for (const label of ['Data', 'Descrizione', 'Importo', 'Originale', 'Categoria AI', 'Elimina']) {
      headRow.append(el('th', { text: label }));
    }
    thead.append(headRow);
    const tbody = el('tbody');
    for (const row of result.rows) {
      const edit = reviewEdits.get(row.index);
      const selectedCategory = edit?.newCategory ?? row.newCategory;
      const displayCategory =
        selectedCategory && options.includes(selectedCategory)
          ? selectedCategory
          : UNCLASSIFIED_PLACEHOLDER;
      const tr = el('tr', { className: edit?.deleted ? 'deleted' : '' });
      tr.append(
        el('td', { text: row.date }),
        el('td', { text: row.description.slice(0, 50), title: row.description }),
        el('td', { text: fmtEur(row.amount) }),
        el('td', { text: row.originalCategory }),
      );
      const select = el('select', { className: 'control cell-input' });
      for (const category of options) {
        const option = el('option', { text: category });
        option.value = category;
        option.selected = category === displayCategory;
        select.append(option);
      }
      select.addEventListener('change', () => {
        reviewEdits.set(row.index, {
          newCategory: select.value,
          deleted: reviewEdits.get(row.index)?.deleted ?? false,
        });
      });
      tr.append(el('td', {}, [select]));
      const checkbox = el('input', { attrs: { type: 'checkbox' } }) as HTMLInputElement;
      checkbox.checked = edit?.deleted ?? false;
      checkbox.addEventListener('change', () => {
        reviewEdits.set(row.index, {
          newCategory: reviewEdits.get(row.index)?.newCategory ?? displayCategory,
          deleted: checkbox.checked,
        });
        tr.classList.toggle('deleted', checkbox.checked);
      });
      tr.append(el('td', {}, [checkbox]));
      tbody.append(tr);
    }
    reviewTable.append(thead, tbody);
    reviewScroll.append(reviewTable);

    const apply = el('button', { className: 'btn', text: '✅ Applica modifiche', attrs: { type: 'button' } });
    apply.addEventListener('click', () => {
      const rows = buildEditedRows(result);
      reviewEdits = new Map();
      ctx.post({ type: 'applyImportEdits', rows });
    });
    const save = el('button', { className: 'btn primary', text: '💾 Conferma e Salva nel Database', attrs: { type: 'button' } });
    save.title = 'I mesi esistenti vengono aggiornati in modalità incrementale.';
    save.addEventListener('click', () => {
      confirmThen(
        save as HTMLButtonElement,
        () => {
          const rows = buildEditedRows(result);
          reviewEdits = new Map();
          ctx.post({ type: 'saveImport', rows });
        },
        '⚠️ Conferma salvataggio?',
      );
    });
    const cancel = el('button', { className: 'btn ghost', text: 'Annulla', attrs: { type: 'button' } });
    cancel.addEventListener('click', () => {
      reviewEdits = new Map();
      state.importResult = null;
      state.importProgress = null;
      ctx.post({ type: 'cancelImport' });
      ctx.renderMain();
    });
    reviewCard.body.append(
      reviewScroll,
      el('div', { className: 'button-row' }, [apply, save, cancel]),
      el('p', {
        className: 'muted',
        text: 'Le correzioni manuali (categoria diversa dalla proposta AI) vengono apprese come source=manual.',
      }),
    );
    root.append(reviewCard.section);

    const totalsCard = card('📊 Totali Mensili (Anteprima)');
    totalsCard.body.append(
      aggregatedTable(result.aggregated),
      el('details', { className: 'expander' }, [
        el('summary', { text: 'Dettaglio completo per categoria' }),
        aggregatedDetailTable(result.aggregated),
      ]),
      el('details', { className: 'expander' }, [
        el('summary', { text: 'Report AI (markdown)' }),
        el('div', { className: 'markdown', html: markdownToHtml(result.report) }),
      ]),
    );
    root.append(totalsCard.section);
  }

  // Manual month
  if (!manualInitialized) {
    const latest = latestMonth(state.rows);
    if (latest) {
      manualYear = latest.year;
      manualMonth = latest.month;
    }
    manualInitialized = true;
  }
  const manualCard = card(
    '✍️ Gestione manuale del mese',
    'Se il mese esiste già, gli importi inseriti vengono SOMMATI (modalità incrementale).',
  );
  const existing = findMonthRow(state.rows, manualYear, manualMonth);
  const yearInput = el('input', {
    className: 'control',
    attrs: { type: 'number', min: '2020', max: '2030', value: String(manualYear) },
  }) as HTMLInputElement;
  yearInput.addEventListener('change', () => {
    manualYear = Number(yearInput.value) || new Date().getFullYear();
    ctx.renderMain();
  });
  const monthSelect = el('select', { className: 'control' });
  for (const month of MONTHS_EN) {
    const option = el('option', { text: month });
    option.value = month;
    option.selected = month === manualMonth;
    monthSelect.append(option);
  }
  monthSelect.addEventListener('change', () => {
    manualMonth = monthSelect.value;
    ctx.renderMain();
  });

  const manualGrid = el('div', { className: 'manual-grid' });
  manualGrid.append(
    el('div', { className: 'manual-group' }, [
      el('h3', { text: 'Entrate (aggiungi)' }),
      ...INCOME_COLUMNS.map((column) =>
        el('label', { className: 'field' }, [
          el('span', { text: column }),
          numberInput(manualValues[column] ?? 0, (value) => { manualValues[column] = value; }, '100'),
        ]),
      ),
    ]),
    el('div', { className: 'manual-group' }, [
      el('h3', { text: 'Uscite (aggiungi)' }),
      ...[...EXPENSE_COLUMNS, ...CAPEX_COLUMNS].map((column) =>
        el('label', { className: 'field' }, [
          el('span', { text: column }),
          numberInput(manualValues[column] ?? 0, (value) => { manualValues[column] = value; }, '10'),
        ]),
      ),
    ]),
  );

  const submit = el('button', {
    className: 'btn primary',
    text: existing ? 'Aggiorna Mese' : 'Crea Mese',
    attrs: { type: 'button' },
  });
  submit.addEventListener('click', () => {
    const values: Record<string, number> = {};
    for (const [key, value] of Object.entries(manualValues)) {
      if (Number.isFinite(value) && value !== 0) values[key] = value;
    }
    if (Object.keys(values).length === 0) {
      ctx.toast('warn', 'Inserisci almeno un importo.');
      return;
    }
    ctx.post({
      type: 'addManualMonth',
      year: manualYear,
      month: manualMonth,
      mode: existing ? 'increment' : 'create',
      values,
    });
    manualValues = {};
  });

  const existingValues: HTMLElement[] = [];
  if (existing) {
    const bag = existing as unknown as Record<string, number>;
    const filled = [...INCOME_COLUMNS, ...EXPENSE_COLUMNS, ...CAPEX_COLUMNS].filter(
      (column) => Number(bag[column] ?? 0) !== 0,
    );
    if (filled.length > 0) {
      const wrapper = el('div', { className: 'table-scroll' });
      const table = el('table', { className: 'data-table' });
      const head = el('thead');
      const headRow = el('tr');
      headRow.append(el('th', { text: 'Categoria' }), el('th', { text: 'Valore attuale' }));
      head.append(headRow);
      const body = el('tbody');
      for (const column of filled) {
        const tr = el('tr');
        tr.append(
          el('td', { text: column }),
          el('td', { text: fmtEur(Number(bag[column] ?? 0)) }),
        );
        body.append(tr);
      }
      table.append(head, body);
      wrapper.append(table);
      existingValues.push(
        el('details', { className: 'expander', attrs: { open: 'true' } }, [
          el('summary', { text: `📌 Valori attuali di ${manualMonth} ${manualYear}` }),
          wrapper,
        ]),
      );
    }
  }

  manualCard.body.append(
    el('div', { className: 'filter-row' }, [
      el('label', { className: 'field' }, [el('span', { text: 'Anno' }), yearInput]),
      el('label', { className: 'field' }, [el('span', { text: 'Mese' }), monthSelect]),
      el('div', { className: existing ? 'alert warn' : 'alert success' }, [
        el('strong', { text: existing ? '📅 Mese esistente: ' : '✨ Nuovo mese: ' }),
        el('span', {
          text: existing
            ? `${manualMonth} ${manualYear}. Gli importi inseriti vengono AGGIUNTI ai valori attuali.`
            : `${manualMonth} ${manualYear}. Il mese non esiste ancora: verrà creato.`,
        }),
      ]),
    ]),
    ...existingValues,
    manualGrid,
    el('div', { className: 'button-row' }, [submit]),
  );
  root.append(manualCard.section);
}

function aggregatedDetailTable(months: readonly AggregatedMonth[]): HTMLElement {
  const categories = [...new Set(months.flatMap((month) => Object.keys(month.values)))].sort();
  const wrapper = el('div', { className: 'table-scroll' });
  const table = el('table', { className: 'data-table' });
  const head = el('thead');
  const headRow = el('tr');
  for (const label of ['Anno', 'Mese', ...categories]) headRow.append(el('th', { text: label }));
  head.append(headRow);
  const body = el('tbody');
  for (const month of months) {
    const tr = el('tr');
    tr.append(el('td', { text: String(month.Year) }), el('td', { text: month.Month }));
    for (const category of categories) {
      tr.append(el('td', { text: fmtEur(month.values[category] ?? 0) }));
    }
    body.append(tr);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

export function updateImportProgress(percent: number, message: string): void {
  const bar = document.getElementById('import-progress-bar');
  const text = document.getElementById('import-progress-text');
  const container = document.getElementById('import-progress');
  if (container) container.classList.remove('hidden');
  if (bar) bar.style.width = `${Math.round(Math.max(0, Math.min(1, percent)) * 100)}%`;
  if (text) text.textContent = message;
}
