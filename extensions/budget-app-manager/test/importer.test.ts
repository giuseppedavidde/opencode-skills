import { describe, expect, it } from 'vitest';
import {
  aggregatedFromReview,
  applyReviewEdits,
  buildTransactionRecords,
  combineImportResults,
  mergeAggregatedIntoMonthly,
  parseExtractedTransactions,
} from '../src/importer/bankImporter';
import { decodeBuffer, parseCsvTable } from '../src/importer/csv';
import {
  UNCLASSIFIED_PLACEHOLDER,
  type ImportReviewRow,
  type MonthlyRow,
} from '../src/types';

function reviewRow(overrides: Partial<ImportReviewRow> = {}): ImportReviewRow {
  return {
    index: 1,
    date: '2025-01-15',
    description: 'MCDONALDS WIEN',
    amount: -12.5,
    originalCategory: 'Freizeit & Genuss',
    aiCategory: 'Cene, Pranzo',
    proposedCategory: 'Cene, Pranzo',
    newCategory: 'Cene, Pranzo',
    deleted: false,
    stdName: 'MCDONALDS',
    stdType: '',
    year: 2025,
    monthNum: 1,
    month: 'January',
    ...overrides,
  };
}

function emptyRow(year: number, monthNum: number, month: string): MonthlyRow {
  return {
    Year: year,
    MonthNum: monthNum,
    Month: month,
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
}

const categories = ['Stipendio', 'Alimentari', 'Cene, Pranzo', 'Acquisto Auto', 'Escluso'];

describe('applyReviewEdits', () => {
  it('applies a valid category and learns the manual correction', () => {
    const result = applyReviewEdits(
      [reviewRow({ newCategory: 'Alimentari' })],
      categories,
    );
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]?.newCategory).toBe('Alimentari');
    expect(result.learning[0]?.category).toBe('Alimentari');
    expect(result.learning[0]?.keys).toContain('mcdonalds');
  });

  it('ignores the placeholder and keeps the AI proposal', () => {
    const result = applyReviewEdits(
      [reviewRow({ newCategory: UNCLASSIFIED_PLACEHOLDER })],
      categories,
    );
    expect(result.rows[0]?.newCategory).toBe('Cene, Pranzo');
    expect(result.learning).toHaveLength(0);
  });

  it('drops deleted rows', () => {
    const result = applyReviewEdits(
      [reviewRow({ deleted: true }), reviewRow({ index: 2 })],
      categories,
    );
    expect(result.deleted).toBe(1);
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]?.index).toBe(2);
  });
});

describe('aggregation', () => {
  const rows: ImportReviewRow[] = [
    reviewRow({ index: 1, description: 'Salary', amount: 3000, newCategory: 'Stipendio', proposedCategory: 'Stipendio' }),
    reviewRow({ index: 2, description: 'BILLA', amount: -300, newCategory: 'Alimentari', proposedCategory: 'Alimentari' }),
    reviewRow({ index: 3, description: 'Transfer', amount: -100, newCategory: 'Escluso', proposedCategory: 'Escluso' }),
    reviewRow({ index: 4, description: 'Car', amount: -2000, newCategory: 'Acquisto Auto', proposedCategory: 'Acquisto Auto' }),
  ];

  it('aggregates income, recurring expenses, capex and excluded rows', () => {
    const months = aggregatedFromReview(rows, categories.filter((c) => c !== 'Escluso'));
    expect(months).toHaveLength(1);
    const month = months[0]!;
    expect(month.values['Stipendio']).toBe(3000);
    expect(month.values['Alimentari']).toBe(300);
    expect(month.values['Acquisto Auto']).toBe(2000);
    expect(month.values['Escluso']).toBe(100);
    expect(month.totaleEntrate).toBe(3000);
    expect(month.totaleUscite).toBe(2300);
    expect(month.redditoMenoSpese).toBe(700);
    expect(month.risparmioPct).toBeCloseTo(23.3333, 3);
  });

  it('increments an existing month and creates a new one', () => {
    const existing = emptyRow(2025, 1, 'January');
    existing.Alimentari = 100;
    const months = aggregatedFromReview(rows, categories.filter((c) => c !== 'Escluso'));
    const merged = mergeAggregatedIntoMonthly([existing], months);
    expect(merged.updated).toBe(1);
    expect(merged.created).toBe(0);
    expect(merged.rows[0]?.Alimentari).toBe(400);
    expect(merged.rows[0]?.Stipendio).toBe(3000);
    expect(merged.rows[0]?.['Acquisto Auto']).toBe(2000);
  });

  it('creates a missing month with the right month name', () => {
    const months = aggregatedFromReview(rows, categories.filter((c) => c !== 'Escluso'));
    const merged = mergeAggregatedIntoMonthly([], months);
    expect(merged.created).toBe(1);
    expect(merged.rows[0]?.Month).toBe('January');
    expect(merged.rows[0]?.MonthNum).toBe(1);
  });

  it('builds transaction records with month_ref', () => {
    const records = buildTransactionRecords(rows);
    expect(records[0]?.month_ref).toBe('January 2025');
    expect(records[0]?.source).toBe('bank_import');
    expect(records[1]?.amount).toBe(-300);
  });
});

describe('parseExtractedTransactions', () => {
  it('parses plain and wrapped JSON', () => {
    const plain = parseExtractedTransactions(
      '[{"Buchungsdatum":"01.01.2024","Umsatztext":"Amazon","Betrag":"-25,90"}]',
    );
    expect(plain).toHaveLength(1);
    expect(plain[0]?.Umsatztext).toBe('Amazon');
    const wrapped = parseExtractedTransactions(
      '```json\n{"transactions":[{"date":"2024-01-02","description":"Salary","amount":"2500"}]}\n```',
    );
    expect(wrapped[0]?.Buchungsdatum).toBe('2024-01-02');
    expect(wrapped[0]?.Betrag).toBe('2500');
  });

  it('returns an empty list for invalid output', () => {
    expect(parseExtractedTransactions('not json')).toEqual([]);
  });
});

import { processBankFile } from '../src/importer/bankImporter';
import type { ImportResultPayload, MerchantEntry } from '../src/types';

const billaEntry: MerchantEntry = {
  merchant: 'billa',
  category: 'Alimentari',
  source: 'seeded',
  confidence: 0.9,
  times_seen: 1,
};

const CSV_STATEMENT = [
  'Buchungsdatum;Umsatztext;Betrag;Kategorie',
  '15.01.2025;BILLA DANKT 1234;-25,50;Unkategorisiert',
  '16.01.2025;Unbekannter Laden;-10,00;Unkategorisiert',
].join('\n');

describe('classification mode selection', () => {
  it('hybrid mode uses the merchant map and skips the LLM for known shops', async () => {
    let calls = 0;
    const result = await processBankFile(Buffer.from(CSV_STATEMENT, 'utf8'), 'statement.csv', {
      targetCategories: ['Alimentari', 'Trasporti'],
      incomeColumns: ['Stipendio'],
      merchantMap: { billa: billaEntry },
      classifyMode: 'hybrid',
      llm: {
        categorize: async () => {
          calls += 1;
          throw new Error('LLM non deve essere chiamato per BILLA');
        },
      },
      pdfAssetsDir: '.',
      sourceName: 'statement.csv',
    });
    expect(result.rows[0]?.newCategory).toBe('Alimentari');
    expect(result.rows[1]?.newCategory).toBe('Unkategorisiert');
    expect(result.stats.llmSent).toBe(1);
    expect(result.stats.llmFailed).toBe(1);
    expect(calls).toBe(1);
    expect(result.aggregated[0]?.values['Alimentari']).toBe(25.5);
  });

  it('llm_only mode bypasses deterministic shortcuts and forces the model', async () => {
    let calls = 0;
    const result = await processBankFile(Buffer.from(CSV_STATEMENT, 'utf8'), 'statement.csv', {
      targetCategories: ['Alimentari', 'Trasporti'],
      incomeColumns: ['Stipendio'],
      merchantMap: { billa: billaEntry },
      classifyMode: 'llm_only',
      llm: {
        categorize: async () => {
          calls += 1;
          return '{"0":"A","1":"B"}';
        },
      },
      pdfAssetsDir: '.',
      sourceName: 'statement.csv',
    });
    expect(calls).toBe(1);
    expect(result.stats.llmSent).toBe(2);
    expect(result.stats.llmMapped).toBe(2);
    expect(result.rows[0]?.newCategory).toBe('Alimentari');
    expect(result.rows[1]?.newCategory).toBe('Trasporti');
  });
});


describe('CSV decoding', () => {
  it('decodes cp1252 fallback and parses semicolon files', () => {
    const cp1252 = Buffer.from([0x42, 0x49, 0x4c, 0x4c, 0x41, 0x20, 0x80]);
    expect(decodeBuffer(cp1252)).toBe('BILLA €');
    const table = parseCsvTable('a;b\n1;2\n');
    expect(table.records[0]).toEqual({ a: '1', b: '2' });
  });
});

function resultPayload(overrides: Partial<ImportResultPayload> = {}): ImportResultPayload {
  const rows = overrides.rows ?? [reviewRow()];
  return {
    rows,
    aggregated: aggregatedFromReview(rows, ['Alimentari', 'Cene, Pranzo', 'Escluso']),
    report: 'report',
    stats: { mode: 'hybrid', llmSent: 1, llmMapped: 1, llmFailed: 0, errors: [] },
    categoryOptions: ['Alimentari', 'Cene, Pranzo', 'Escluso'],
    sourceName: 'a.csv',
    ...overrides,
  };
}

describe('combineImportResults', () => {
  it('keeps previous rows and appends new rows with fresh indices', () => {
    const first = resultPayload({ sourceName: 'a.csv' });
    const second = resultPayload({
      sourceName: 'b.csv',
      rows: [reviewRow({ index: 0, description: 'BILLA', amount: -9 })],
    });
    const merged = combineImportResults(first, second, ['Alimentari', 'Cene, Pranzo', 'Escluso']);
    expect(merged.rows).toHaveLength(2);
    expect(merged.rows[0]?.index).toBe(1);
    expect(merged.rows[1]?.index).toBe(2);
    expect(merged.rows[1]?.description).toBe('BILLA');
    expect(merged.sourceName).toBe('a.csv + b.csv');
    expect(merged.stats.llmSent).toBe(2);
    expect(merged.categoryOptions).toEqual(['Alimentari', 'Cene, Pranzo', 'Escluso']);
  });

  it('recomputes the aggregated preview from all rows', () => {
    const first = resultPayload({
      rows: [reviewRow({ index: 0, aiCategory: 'Alimentari', newCategory: 'Alimentari', amount: -10 })],
    });
    const second = resultPayload({
      rows: [reviewRow({ index: 0, aiCategory: 'Alimentari', newCategory: 'Alimentari', amount: -5 })],
    });
    const merged = combineImportResults(first, second, ['Alimentari', 'Cene, Pranzo', 'Escluso']);
    const month = merged.aggregated[0];
    expect(month?.values.Alimentari).toBe(15);
  });
});
