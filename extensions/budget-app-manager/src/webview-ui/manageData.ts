import {
  BUDGET_COLUMNS,
  EXPENSE_COLUMNS,
  INCOME_COLUMNS,
  MONTHS_EN,
  type MonthlyKey,
  type MonthlyRow,
} from '../types';
import { el, fmtEur, fmtNum, clear } from './dom';
import type { UiContext } from './context';

let draftRows: MonthlyRow[] | null = null;
let deletedKeys: MonthlyKey[] = [];
let targetsDraft: Record<string, number> | null = null;
let merchantEdits = new Map<string, string>();

export function invalidateDataDrafts(): void {
  draftRows = null;
  deletedKeys = [];
  targetsDraft = null;
}

export function invalidateMerchantEdits(): void {
  merchantEdits = new Map();
}

function cloneRow(row: MonthlyRow): MonthlyRow {
  return { ...row };
}

function sameKey(a: { Year: number; MonthNum: number }, b: { Year: number; MonthNum: number }): boolean {
  return Number(a.Year) === Number(b.Year) && Number(a.MonthNum) === Number(b.MonthNum);
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

function textInput(value: string, onChange: (value: string) => void): HTMLInputElement {
  const input = el('input', {
    className: 'control cell-input',
    attrs: { type: 'text', value },
  }) as HTMLInputElement;
  input.addEventListener('change', () => onChange(input.value));
  return input;
}

export function renderManageData(root: HTMLElement, ctx: UiContext): void {
  clear(root);
  const { state } = ctx;

  const header = el('div', { className: 'page-head' }, [
    el('div', {}, [
      el('h1', { text: '📝 Gestione Dati' }),
      el('p', {
        className: 'muted',
        text: 'Modifica i valori direttamente nella tabella. Le colonne dei totali sono calcolate automaticamente.',
      }),
    ]),
  ]);
  root.append(header);

  // Database info
  const dbCard = card('💾 Database', 'Informazioni sul file SQLite e backup.');
  const exportButton = el('button', { className: 'btn', text: '📥 Export CSV', attrs: { type: 'button' } });
  exportButton.addEventListener('click', () => ctx.post({ type: 'exportCsv' }));
  dbCard.body.append(
    el('div', { className: 'metric-grid' }, [
      infoCard('File', state.dbInfo.dbPath),
      infoCard('Dimensione', `${state.dbInfo.dbSizeKb.toFixed(1)} KB`),
      infoCard('Records', fmtNum(state.dbInfo.rowCount)),
      infoCard('Transazioni', fmtNum(state.dbInfo.transactionCount)),
      infoCard('Mappature', fmtNum(state.dbInfo.merchantCount)),
      infoCard('Ultimo backup', state.dbInfo.lastBackupTime ?? 'n/a'),
    ]),
    el('div', { className: 'button-row' }, [exportButton]),
  );
  root.append(dbCard.section);

  // Monthly budget table
  if (draftRows === null) draftRows = state.rows.map(cloneRow);
  const monthlyCard = card(
    '📅 Budget Mensile',
    'Anno, mese e importi. Aggiungi o elimina righe, poi salva.',
  );
  const tableScroll = el('div', { className: 'table-scroll' });
  const table = el('table', { className: 'data-table editable' });
  const thead = el('thead');
  const headRow = el('tr');
  for (const column of BUDGET_COLUMNS) {
    headRow.append(el('th', { text: shortLabel(column), title: column }));
  }
  headRow.append(el('th', { text: 'Azioni' }));
  thead.append(headRow);
  const tbody = el('tbody');

  draftRows.forEach((row, index) => {
    const tr = el('tr');
    // Year
    tr.append(el('td', {}, [numberInput(row.Year, (value) => { row.Year = Math.trunc(value); }, '1')]));
    // MonthNum
    tr.append(el('td', {}, [numberInput(row.MonthNum, (value) => { row.MonthNum = Math.trunc(value); }, '1')]));
    // Month
    tr.append(el('td', {}, [textInput(row.Month, (value) => { row.Month = value; })]));
    for (const column of BUDGET_COLUMNS) {
      if (column === 'Year' || column === 'MonthNum' || column === 'Month') continue;
      tr.append(
        el('td', {}, [
          numberInput(Number(row[column]) || 0, (value) => {
            (row as unknown as Record<string, number>)[column] = value;
          }),
        ]),
      );
    }
    const remove = el('button', { className: 'btn icon danger', text: '🗑️', title: 'Elimina riga', attrs: { type: 'button' } });
    remove.addEventListener('click', () => {
      const existed = state.rows.some((original) => sameKey(original, row));
      if (existed) deletedKeys.push({ Year: Number(row.Year), MonthNum: Number(row.MonthNum) });
      draftRows = draftRows?.filter((_, position) => position !== index) ?? null;
      ctx.renderMain();
    });
    tr.append(el('td', {}, [remove]));
    tbody.append(tr);
  });

  if (draftRows.length === 0) {
    const tr = el('tr');
    tr.append(el('td', { className: 'muted', text: 'Nessuna riga. Aggiungi un mese.' }, []));
    tr.firstElementChild?.setAttribute('colspan', String(BUDGET_COLUMNS.length + 1));
    tbody.append(tr);
  }
  table.append(thead, tbody);
  tableScroll.append(table);

  const addButton = el('button', { className: 'btn', text: '➕ Aggiungi mese', attrs: { type: 'button' } });
  addButton.addEventListener('click', () => {
    const latest = draftRows && draftRows.length > 0 ? draftRows[0] : null;
    let year = new Date().getFullYear();
    let monthNum = new Date().getMonth() + 1;
    if (latest) {
      year = Number(latest.Year);
      monthNum = Number(latest.MonthNum) + 1;
      if (monthNum > 12) {
        monthNum = 1;
        year += 1;
      }
    }
    const row: MonthlyRow = {
      Year: year,
      MonthNum: monthNum,
      Month: MONTHS_EN[monthNum - 1] ?? 'January',
      Stipendio: 0,
      'Reddito aggiuntivo': 0,
      Alimentari: 0,
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
    draftRows = [row, ...(draftRows ?? [])];
    ctx.renderMain();
  });

  const saveButton = el('button', { className: 'btn primary', text: '💾 Salva modifiche', attrs: { type: 'button' } });
  saveButton.addEventListener('click', () => {
    const rows = (draftRows ?? []).filter((row) => Number(row.Year) > 0 && Number(row.MonthNum) > 0);
    ctx.post({ type: 'saveMonthly', rows, deleted: deletedKeys });
    draftRows = null;
    deletedKeys = [];
  });

  monthlyCard.body.append(
    tableScroll,
    el('div', { className: 'button-row' }, [
      addButton,
      saveButton,
      el('span', {
        className: 'muted',
        text: deletedKeys.length > 0 ? `${deletedKeys.length} righe da eliminare al salvataggio.` : '',
      }),
    ]),
  );
  root.append(monthlyCard.section);

  // Targets
  if (targetsDraft === null) {
    const historical = new Map<string, { sum: number; count: number }>();
    for (const row of state.rows) {
      for (const column of EXPENSE_COLUMNS) {
        const entry = historical.get(column) ?? { sum: 0, count: 0 };
        entry.sum += Number(row[column]) || 0;
        entry.count += 1;
        historical.set(column, entry);
      }
    }
    targetsDraft = {};
    for (const column of EXPENSE_COLUMNS) {
      const entry = historical.get(column);
      targetsDraft[column] = state.targets[column] ?? (entry && entry.count > 0 ? entry.sum / entry.count : 0);
    }
  }
  const targetsCard = card(
    '🎯 Target Mensili per Categoria',
    'Prefill con la media storica. Salva per attivare il benchmark in dashboard.',
  );
  const targetGrid = el('div', { className: 'targets-grid' });
  for (const column of EXPENSE_COLUMNS) {
    targetGrid.append(
      el('label', { className: 'field' }, [
        el('span', { text: shortLabel(column), title: column }),
        numberInput(targetsDraft[column] ?? 0, (value) => {
          if (targetsDraft) targetsDraft[column] = value;
        }),
      ]),
    );
  }
  const saveTargets = el('button', { className: 'btn primary', text: '💾 Salva Target', attrs: { type: 'button' } });
  saveTargets.addEventListener('click', () => {
    const payload: Record<string, number> = {};
    for (const column of EXPENSE_COLUMNS) {
      payload[column] = Number(targetsDraft?.[column] ?? 0);
    }
    ctx.post({ type: 'saveTargets', targets: payload });
    targetsDraft = null;
  });
  targetsCard.body.append(targetGrid, el('div', { className: 'button-row' }, [saveTargets]));
  root.append(targetsCard.section);

  // Merchant mapping
  const merchantCard = card(
    '🏪 Mappatura Negozi → Categorie',
    'Le modifiche manuali hanno priorità assoluta e vengono apprese al prossimo import.',
  );
  if (!state.merchant) {
    const load = el('button', { className: 'btn', text: 'Carica mappatura', attrs: { type: 'button' } });
    load.addEventListener('click', () => ctx.post({ type: 'loadMerchants' }));
    merchantCard.body.append(
      el('p', { className: 'muted', text: 'Mappatura non ancora caricata.' }),
      load,
    );
  } else {
    const entries = state.merchant.entries;
    const categories = state.merchant.categories;
    const mapScroll = el('div', { className: 'table-scroll tall' });
    const mapTable = el('table', { className: 'data-table editable' });
    const head = el('thead');
    const headRow = el('tr');
    for (const label of ['Negozio (normalizzato)', 'Categoria', 'Origine', 'Volte', 'Confidenza', 'Azioni']) {
      headRow.append(el('th', { text: label }));
    }
    head.append(headRow);
    const body = el('tbody');
    for (const entry of entries) {
      const tr = el('tr');
      tr.append(el('td', { text: entry.merchant }));
      const select = el('select', { className: 'control cell-input' });
      const options = [...new Set([...categories, entry.category])];
      for (const category of options) {
        const option = el('option', { text: category });
        option.value = category;
        option.selected = category === (merchantEdits.get(entry.merchant) ?? entry.category);
        select.append(option);
      }
      select.addEventListener('change', () => {
        merchantEdits.set(entry.merchant, select.value);
      });
      tr.append(el('td', {}, [select]));
      tr.append(el('td', { text: entry.source }));
      tr.append(el('td', { text: String(entry.times_seen) }));
      const bar = el('div', { className: 'confidence' }, [
        el('div', {
          className: 'confidence-bar',
          attrs: { style: `width:${Math.max(0, Math.min(1, entry.confidence)) * 100}%` },
        }),
      ]);
      tr.append(el('td', {}, [bar, el('span', { className: 'muted', text: entry.confidence.toFixed(2) })]));
      const remove = el('button', { className: 'btn icon danger', text: '🗑️', title: 'Elimina', attrs: { type: 'button' } });
      remove.addEventListener('click', () => ctx.post({ type: 'deleteMerchant', merchant: entry.merchant }));
      tr.append(el('td', {}, [remove]));
      body.append(tr);
    }
    mapTable.append(head, body);
    mapScroll.append(mapTable);

    const addMerchant = el('input', { className: 'control', attrs: { type: 'text', placeholder: 'Negozio (es. BILLA)' } }) as HTMLInputElement;
    const addCategory = el('select', { className: 'control' });
    for (const category of categories) {
      const option = el('option', { text: category });
      option.value = category;
      addCategory.append(option);
    }
    const addButton = el('button', { className: 'btn', text: '➕ Aggiungi manuale', attrs: { type: 'button' } });
    addButton.addEventListener('click', () => {
      if (!addMerchant.value.trim()) {
        ctx.toast('warn', 'Inserisci il nome del negozio.');
        return;
      }
      ctx.post({ type: 'addMerchantManual', merchant: addMerchant.value.trim(), category: addCategory.value });
      addMerchant.value = '';
    });

    const saveMap = el('button', { className: 'btn primary', text: '💾 Salva modifiche', attrs: { type: 'button' } });
    saveMap.addEventListener('click', () => {
      if (merchantEdits.size === 0) {
        ctx.toast('info', 'Nessuna modifica da salvare.');
        return;
      }
      for (const [merchant, category] of merchantEdits.entries()) {
        ctx.post({ type: 'setMerchantManual', merchant, category });
      }
      merchantEdits = new Map();
      ctx.toast('success', 'Correzioni manuali inviate.');
    });

    const importSeed = el('button', { className: 'btn', text: '📥 Importa seed', attrs: { type: 'button' } });
    importSeed.addEventListener('click', () => ctx.post({ type: 'importSeed' }));
    const exportMap = el('button', { className: 'btn', text: '📤 Esporta mappatura', attrs: { type: 'button' } });
    exportMap.addEventListener('click', () => ctx.post({ type: 'exportMerchants' }));

    merchantCard.body.append(
      mapScroll,
      el('div', { className: 'inline-form' }, [addMerchant, addCategory, addButton]),
      el('div', { className: 'button-row' }, [
        saveMap,
        importSeed,
        exportMap,
        el('span', { className: 'muted', text: `${entries.length} voci in mappatura` }),
      ]),
    );
  }
  root.append(merchantCard.section);
}

function infoCard(label: string, value: string): HTMLElement {
  return el('div', { className: 'metric-card compact' }, [
    el('div', { className: 'metric-label', text: label }),
    el('div', { className: 'info-value', text: value }),
  ]);
}

function shortLabel(column: string): string {
  const known: Record<string, string> = {
    'Immobili (affitto, mutuo, tasse, assicurazione)': 'Immobili',
    'PayPal + Abbonamenti': 'PayPal + Abb.',
    'Spese Straordinarie': 'Sp. Straord.',
    'Acquisto Auto': 'Acquisto Auto',
    'Cene, Pranzo': 'Cene, Pranzo',
    'Viaggi, Divertimento': 'Viaggi, Divert.',
    'Reddito aggiuntivo': 'Reddito agg.',
  };
  return known[column] ?? column;
}

export function targetsSummary(rows: readonly MonthlyRow[]): number {
  return rows.length > 0 ? Number(rows[0]?.Stipendio ?? 0) : 0;
}

export function moneyColumnsForForm(): string[] {
  return [...INCOME_COLUMNS, ...EXPENSE_COLUMNS, 'Acquisto Auto'];
}

export function formatMoney(value: number): string {
  return fmtEur(value);
}
