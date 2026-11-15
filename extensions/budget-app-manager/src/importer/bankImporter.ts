import {
  BUDGET_COLUMNS,
  EXCLUDED_CATEGORY,
  INCOME_COLUMNS,
  MONTHS_EN,
  UNCLASSIFIED_PLACEHOLDER,
  type AggregatedMonth,
  type AiStats,
  type ClassifyMode,
  type ImportResultPayload,
  type ImportReviewRow,
  type MerchantEntry,
  type MonthlyRow,
  type TransactionRecord,
} from '../types';
import type { LlmClientLike } from '../ai/client';
import {
  assertClassifyMode,
  buildJsonPrompt,
  buildLetterIndex,
  buildLetterPrompt,
  cleanAmount,
  deterministicCategory,
  mapGermanCategory,
  mapTradeType,
  parseJsonMappings,
  parseLetterMappings,
  type BatchItem,
} from './classify';
import { merchantKeys } from './merchant';
import {
  monthNameEnglish,
  parseBankDate,
  parseCsvTable,
  standardizeColumns,
  type StandardRow,
} from './csv';

const BATCH_SIZE = 20;
const PLACEHOLDER = UNCLASSIFIED_PLACEHOLDER;

export interface BankImportOptions {
  targetCategories: string[];
  incomeColumns: string[];
  merchantMap: Record<string, MerchantEntry>;
  classifyMode: ClassifyMode;
  llm: LlmClientLike | null;
  progress?: (percent: number, message: string) => void;
  onLlmMapping?: (keys: string[], category: string) => void;
  pdfAssetsDir: string;
  sourceName: string;
}

interface WorkingRow extends StandardRow {
  analyzedCategory: string;
  newCategory: string;
  proposedCategory: string;
  amount: number;
  dateObj: Date | null;
  year: number | null;
  monthNum: number | null;
  month: string;
}

function stripFences(text: string): string {
  let cleaned = text.trim();
  if (cleaned.includes('```json')) cleaned = cleaned.split('```json')[1]?.split('```')[0] ?? cleaned;
  else if (cleaned.includes('```')) {
    const parts = cleaned.split('```');
    if (parts.length >= 2) cleaned = parts[1] ?? cleaned;
  }
  return cleaned.trim();
}

function readField(record: Record<string, unknown>, names: readonly string[]): string {
  const lower = new Map<string, unknown>();
  for (const [key, value] of Object.entries(record)) lower.set(key.toLowerCase(), value);
  for (const name of names) {
    const value = lower.get(name.toLowerCase());
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      return String(value);
    }
  }
  return '';
}

export function parseExtractedTransactions(text: string): Record<string, string>[] {
  const cleaned = stripFences(text);
  const start = cleaned.indexOf('[');
  const objectStart = cleaned.indexOf('{');
  let jsonText = cleaned;
  if (start >= 0 && (objectStart < 0 || start < objectStart)) {
    const end = cleaned.lastIndexOf(']');
    if (end > start) jsonText = cleaned.slice(start, end + 1);
  } else if (objectStart >= 0) {
    const end = cleaned.lastIndexOf('}');
    if (end > objectStart) jsonText = cleaned.slice(objectStart, end + 1);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText) as unknown;
  } catch {
    return [];
  }
  let list: unknown = parsed;
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const record = parsed as Record<string, unknown>;
    list = record.transactions ?? record.items ?? record.data ?? [];
  }
  if (!Array.isArray(list)) return [];
  return list
    .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === 'object')
    .map((entry) => ({
      Buchungsdatum: readField(entry, ['Buchungsdatum', 'date', 'datum', 'data', 'valuta']),
      Umsatztext: readField(entry, [
        'Umsatztext',
        'description',
        'descrizione',
        'name',
        'payee',
        'causale',
      ]),
      Betrag: readField(entry, ['Betrag', 'amount', 'importo', 'value']),
    }))
    .filter((entry) => entry.Buchungsdatum || entry.Umsatztext || entry.Betrag);
}

function buildPdfExtractionPrompt(text: string): string {
  return `
        Extract ALL bank transactions from this bank statement text.
        Return a JSON list of objects with these exact fields:
        - "Buchungsdatum": Date DD.MM.YYYY
        - "Umsatztext": Description/Payee
        - "Betrag": Amount as string (e.g. "-12,50" or "1.200,00"). Use European format.

        Example JSON:
        [
          {"Buchungsdatum": "01.01.2024", "Umsatztext": "Amazon", "Betrag": "-25,90"},
          {"Buchungsdatum": "15.01.2024", "Umsatztext": "Salary", "Betrag": "2500,00"}
        ]

        BANK STATEMENT TEXT:
        ${text}
        `;
}

function aggregate(rows: readonly WorkingRow[], targetCategories: readonly string[]): AggregatedMonth[] {
  const groups = new Map<string, AggregatedMonth>();
  for (const row of rows) {
    if (row.year === null || row.monthNum === null) continue;
    const key = `${row.year}-${row.monthNum}`;
    let month = groups.get(key);
    if (!month) {
      month = {
        Year: row.year,
        MonthNum: row.monthNum,
        Month: row.month,
        values: {},
        totaleEntrate: 0,
        totaleUscite: 0,
        redditoMenoSpese: 0,
        risparmioPct: 0,
      };
      groups.set(key, month);
    }
    const category = row.newCategory;
    const raw = row.amount;
    const income = INCOME_COLUMNS.includes(category as (typeof INCOME_COLUMNS)[number]);
    const budgetAmount = income ? (raw > 0 ? raw : 0) : -raw;
    month.values[category] = (month.values[category] ?? 0) + budgetAmount;
  }

  const incomeSet = new Set<string>(INCOME_COLUMNS);
  const targetSet = new Set<string>(targetCategories);
  const result = [...groups.values()];
  for (const month of result) {
    for (const category of targetCategories) {
      if (!(category in month.values)) month.values[category] = 0;
    }
    const income = Object.entries(month.values)
      .filter(([category]) => incomeSet.has(category))
      .reduce((sum, [, value]) => sum + value, 0);
    const expense = Object.entries(month.values)
      .filter(([category]) => targetSet.has(category) && !incomeSet.has(category))
      .reduce((sum, [, value]) => sum + value, 0);
    month.totaleEntrate = round2(income);
    month.totaleUscite = round2(expense);
    month.redditoMenoSpese = round2(income - expense);
    month.risparmioPct = income !== 0 ? ((income - expense) / income) * 100 : 0;
  }
  return result.sort((a, b) => a.Year * 12 + a.MonthNum - (b.Year * 12 + b.MonthNum));
}

function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function buildReport(rows: readonly WorkingRow[]): string {
  let md = '| Date | Description | Amount | Original Category | **New AI Category** |\n';
  md += '|---|---|---|---|---|\n';
  for (const row of rows) {
    const description = row.Std_Description.slice(0, 40).replace(/\|/g, '-');
    const old = row.analyzedCategory;
    const next = row.newCategory;
    const display = old !== next ? `**:green[${next}]**` : next;
    md += `| ${row.Std_Date} | ${description} | ${(row.amount || 0).toFixed(2)} | ${old} | ${display} |\n`;
  }
  return md;
}

function toReviewRow(row: WorkingRow): ImportReviewRow {
  return {
    index: row.index,
    date: row.dateObj ? isoDate(row.dateObj) : row.Std_Date,
    description: row.Std_Description,
    amount: round2(row.amount),
    originalCategory: row.Std_Category,
    aiCategory: row.analyzedCategory,
    proposedCategory: row.proposedCategory,
    newCategory: row.newCategory,
    deleted: false,
    stdName: row.Std_Name,
    stdType: row.Std_Type,
    year: row.year,
    monthNum: row.monthNum,
    month: row.month,
  };
}

function isoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export async function processBankFile(
  data: Buffer,
  fileName: string,
  options: BankImportOptions,
): Promise<ImportResultPayload> {
  assertClassifyMode(options.classifyMode);
  const lowerName = fileName.toLowerCase();
  const isPdf = lowerName.endsWith('.pdf');
  const progress = options.progress ?? (() => undefined);

  progress(0, isPdf ? 'Estrazione testo dal PDF...' : 'Lettura file CSV...');

  let records: Record<string, string>[] = [];
  if (isPdf) {
    if (!options.llm) {
      throw new Error(
        'AI non configurata: il PDF richiede un modello per estrarre le transazioni. Configura provider, modello e API key nella sidebar.',
      );
    }
    const { extractPdfText } = await import('./pdf');
    const extracted = await extractPdfText(data, options.pdfAssetsDir);
    if (!extracted.text.trim()) {
      throw new Error('Il PDF non contiene testo estraibile (potrebbe essere una scansione).');
    }
    progress(0.1, `Testo estratto (${extracted.pages} pagine). Analisi AI...`);
    const response = await options.llm.categorize(buildPdfExtractionPrompt(extracted.text));
    try {
      records = parseExtractedTransactions(response);
    } catch (error) {
      throw new Error(`Risposta AI non valida per il PDF: ${(error as Error).message}`);
    }
    if (records.length === 0) {
      throw new Error('L’AI non ha restituito transazioni dal PDF.');
    }
  } else {
    const table = parseCsvTable(data);
    records = table.records;
  }

  if (records.length === 0) {
    throw new Error('Il file è vuoto o non leggibile.');
  }

  const standardized = standardizeColumns(records);
  const validCategories = new Set([...options.targetCategories, EXCLUDED_CATEGORY]);
  const merchantMap = options.classifyMode === 'hybrid' ? options.merchantMap : {};

  const analyzed: string[] = standardized.map((row) =>
    options.classifyMode === 'hybrid'
      ? deterministicCategory(row.Std_Type, row.Std_Category, row.Std_Description) ??
        row.Std_Category
      : row.Std_Category,
  );

  const mappings = new Map<number, string>();
  const itemsToProcess: BatchItem[] = [];
  const keyById = new Map<number, string[]>();

  standardized.forEach((row, index) => {
    const keys = merchantKeys(row.Std_Name, row.Std_Description);
    keyById.set(row.index, keys);
    if (options.classifyMode === 'hybrid') {
      const byType = mapTradeType(row.Std_Type);
      if (byType !== null) {
        mappings.set(row.index, byType);
        return;
      }
      for (const key of keys) {
        const entry = merchantMap[key];
        if (entry) {
          mappings.set(row.index, entry.category);
          return;
        }
      }
      const byGerman = mapGermanCategory(row.Std_Category, row.Std_Description);
      if (byGerman !== null) {
        mappings.set(row.index, byGerman);
        return;
      }
    }
    itemsToProcess.push({
      id: row.index,
      description: row.Std_Description,
      amount: row.Std_Amount,
      old_category: row.Std_Category,
    });
  });

  const stats: AiStats = {
    mode: options.classifyMode,
    llmSent: itemsToProcess.length,
    llmMapped: 0,
    llmFailed: 0,
    errors: [],
  };

  if (itemsToProcess.length > 0 && !options.llm) {
    stats.errors.push('AI non configurata: le transazioni residue restano da classificare.');
  }

  const totalBatches = Math.ceil(itemsToProcess.length / BATCH_SIZE);
  for (let offset = 0; offset < itemsToProcess.length; offset += BATCH_SIZE) {
    const batchNumber = Math.floor(offset / BATCH_SIZE) + 1;
    const base = isPdf ? 0.2 : 0;
    const percent = itemsToProcess.length
      ? base + (offset / itemsToProcess.length) * (0.9 - base)
      : 0.9;
    progress(percent, `Analisi AI: batch ${batchNumber}/${Math.max(totalBatches, 1)}...`);
    const batch = itemsToProcess.slice(offset, offset + BATCH_SIZE);
    if (!options.llm) break;
    try {
      const letterIndex = buildLetterIndex(options.targetCategories);
      let batchMappings: Record<number, string> = {};
      if (letterIndex) {
        const response = await options.llm.categorize(buildLetterPrompt(batch, letterIndex));
        batchMappings = parseLetterMappings(response, batch, letterIndex);
      }
      if (Object.keys(batchMappings).length === 0) {
        const response = await options.llm.categorize(
          buildJsonPrompt(batch, options.targetCategories),
        );
        batchMappings = parseJsonMappings(response, batch, options.targetCategories);
      }
      let batchMapped = 0;
      for (const [id, category] of Object.entries(batchMappings)) {
        const numericId = Number(id);
        if (!validCategories.has(category)) continue;
        mappings.set(numericId, category);
        batchMapped += 1;
        const keys = keyById.get(numericId) ?? [];
        if (keys.length > 0) options.onLlmMapping?.(keys, category);
      }
      stats.llmMapped += batchMapped;
      if (batchMapped === 0) {
        stats.errors.push(`Batch ${batchNumber}: nessuna categoria valida restituita.`);
      }
    } catch (error) {
      stats.errors.push(`Batch ${batchNumber}: ${(error as Error).message.slice(0, 400)}`);
    }
  }

  progress(0.92, 'Applicazione categorie e calcolo totali...');

  const working: WorkingRow[] = standardized.map((row) => {
    const dateObj = parseBankDate(row.Std_Date);
    const amount = cleanAmount(row.Std_Amount) + cleanAmount(row.Std_Fee) + cleanAmount(row.Std_Tax);
    const mapped = mappings.get(row.index);
    const newCategory = mapped && validCategories.has(mapped) ? mapped : analyzed[row.index] ?? row.Std_Category;
    return {
      ...row,
      amount,
      dateObj,
      year: dateObj ? dateObj.getFullYear() : null,
      monthNum: dateObj ? dateObj.getMonth() + 1 : null,
      month: dateObj ? monthNameEnglish(dateObj.getMonth() + 1) : '',
      analyzedCategory: analyzed[row.index] ?? row.Std_Category,
      newCategory,
      proposedCategory: newCategory,
    };
  });

  stats.llmFailed = Math.max(stats.llmSent - stats.llmMapped, 0);
  const aggregated = aggregate(working, options.targetCategories);
  const report = buildReport(working);
  progress(1, 'Fatto!');

  const categoryOptions = [...new Set([...options.targetCategories, EXCLUDED_CATEGORY])].sort();
  return {
    rows: working.map(toReviewRow),
    aggregated,
    report,
    stats,
    categoryOptions,
    sourceName: options.sourceName,
  };
}

export interface ReviewEditResult {
  rows: ImportReviewRow[];
  learning: Array<{ keys: string[]; category: string }>;
  deleted: number;
}

export function applyReviewEdits(
  rows: readonly ImportReviewRow[],
  validReviewCategories: readonly string[],
): ReviewEditResult {
  const valid = new Set(validReviewCategories);
  const learning: Array<{ keys: string[]; category: string }> = [];
  const kept: ImportReviewRow[] = [];
  let deleted = 0;
  for (const row of rows) {
    if (row.deleted) {
      deleted += 1;
      continue;
    }
    const chosen = row.newCategory;
    const finalCategory =
      chosen && chosen !== PLACEHOLDER && valid.has(chosen)
        ? chosen
        : row.proposedCategory;
    if (finalCategory && finalCategory !== row.proposedCategory) {
      const keys = merchantKeys(row.stdName, row.description);
      if (keys.length > 0) learning.push({ keys, category: finalCategory });
    }
    kept.push({ ...row, newCategory: finalCategory });
  }
  return { rows: kept, learning, deleted };
}

export function aggregatedFromReview(
  rows: readonly ImportReviewRow[],
  targetCategories: readonly string[],
): AggregatedMonth[] {
  const working: WorkingRow[] = rows.map((row) => {
    const dateObj = row.year !== null && row.monthNum !== null
      ? new Date(row.year, row.monthNum - 1, 1)
      : null;
    return {
      index: row.index,
      Std_Amount: String(row.amount),
      Std_Tax: '0',
      Std_Fee: '0',
      Std_Type: row.stdType,
      Std_Date: row.date,
      Std_Category: row.originalCategory,
      Std_Name: row.stdName,
      Std_Description: row.description,
      raw: {},
      analyzedCategory: row.aiCategory,
      newCategory: row.newCategory,
      proposedCategory: row.proposedCategory,
      amount: row.amount,
      dateObj,
      year: row.year,
      monthNum: row.monthNum,
      month: row.month,
    };
  });
  return aggregate(working, targetCategories);
}

export function reviewReport(rows: readonly ImportReviewRow[]): string {
  return buildReport(
    rows.map((row) => ({
      index: row.index,
      Std_Amount: String(row.amount),
      Std_Tax: '0',
      Std_Fee: '0',
      Std_Type: row.stdType,
      Std_Date: row.date,
      Std_Category: row.originalCategory,
      Std_Name: row.stdName,
      Std_Description: row.description,
      raw: {},
      analyzedCategory: row.aiCategory,
      newCategory: row.newCategory,
      proposedCategory: row.proposedCategory,
      amount: row.amount,
      dateObj: null,
      year: row.year,
      monthNum: row.monthNum,
      month: row.month,
    })),
  );
}

export function buildTransactionRecords(
  rows: readonly ImportReviewRow[],
  source = 'bank_import',
): TransactionRecord[] {
  return rows.map((row) => ({
    date: row.date,
    description: row.description,
    amount: row.amount,
    category: row.newCategory,
    source,
    month_ref: row.year !== null ? `${row.month} ${row.year}` : '',
  }));
}

export interface MergeResult {
  rows: MonthlyRow[];
  updated: number;
  created: number;
}

export function mergeAggregatedIntoMonthly(
  existing: readonly MonthlyRow[],
  aggregated: readonly AggregatedMonth[],
): MergeResult {
  const rows = existing.map((row) => ({ ...row }));
  const moneyColumns = new Set<string>(
    BUDGET_COLUMNS.filter(
      (column) => column !== 'Year' && column !== 'MonthNum' && column !== 'Month',
    ),
  );
  let updated = 0;
  let created = 0;
  for (const month of aggregated) {
    const target = rows.find(
      (row) => Number(row.Year) === month.Year && Number(row.MonthNum) === month.MonthNum,
    );
    if (target) {
      for (const [category, value] of Object.entries(month.values)) {
        if (!moneyColumns.has(category)) continue;
        const bag = target as unknown as Record<string, number>;
        bag[category] = round2(Number(bag[category] ?? 0) + value);
      }
      updated += 1;
    } else {
      const row: MonthlyRow = {
        Year: month.Year,
        MonthNum: month.MonthNum,
        Month: month.Month || MONTHS_EN[month.MonthNum - 1] || '',
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
      for (const [category, value] of Object.entries(month.values)) {
        if (!moneyColumns.has(category)) continue;
        (row as unknown as Record<string, number>)[category] = round2(value);
      }
      rows.push(row);
      created += 1;
    }
  }
  return { rows, updated, created };
}

export function combineImportResults(
  previous: ImportResultPayload,
  next: ImportResultPayload,
  categories: readonly string[],
): ImportResultPayload {
  const offset = previous.rows.reduce((max, row) => Math.max(max, row.index), -1) + 1;
  const rows = [
    ...previous.rows,
    ...next.rows.map((row, index) => ({ ...row, index: offset + index })),
  ];
  const categoryOptions = [...previous.categoryOptions];
  for (const category of next.categoryOptions) {
    if (!categoryOptions.includes(category)) categoryOptions.push(category);
  }
  const stats = {
    mode: next.stats.mode,
    llmSent: previous.stats.llmSent + next.stats.llmSent,
    llmMapped: previous.stats.llmMapped + next.stats.llmMapped,
    llmFailed: previous.stats.llmFailed + next.stats.llmFailed,
    errors: [...previous.stats.errors, ...next.stats.errors],
  };
  return {
    rows,
    aggregated: aggregatedFromReview(rows, categories),
    report: `${previous.report}\n\n---\n\n${next.report}`,
    stats,
    categoryOptions,
    sourceName: `${previous.sourceName} + ${next.sourceName}`,
  };
}
