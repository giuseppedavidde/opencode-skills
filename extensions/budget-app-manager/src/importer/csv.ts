import iconv from 'iconv-lite';
import { MONTHS_EN } from '../types';

export function decodeBuffer(buffer: Buffer | Uint8Array): string {
  const bytes = Buffer.from(buffer);
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return text.replace(/^\uFEFF/, '');
  } catch {
    // not UTF-8, continue
  }
  try {
    return iconv.decode(bytes, 'cp1252');
  } catch {
    return iconv.decode(bytes, 'latin1');
  }
}

export function detectDelimiter(text: string): string {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  const sample = lines.slice(0, 5);
  const candidates = [';', ',', '\t', '|'];
  let best = ';';
  let bestScore = -1;
  for (const candidate of candidates) {
    let score = 0;
    for (const line of sample) {
      let count = 0;
      let inQuotes = false;
      for (const char of line) {
        if (char === '"') inQuotes = !inQuotes;
        else if (char === candidate && !inQuotes) count += 1;
      }
      score += count;
    }
    if (score > bestScore) {
      bestScore = score;
      best = candidate;
    }
  }
  return best;
}

export function parseCsv(text: string, delimiter?: string): string[][] {
  const sep = delimiter ?? detectDelimiter(text);
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  const source = text.replace(/^\uFEFF/, '');

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i] ?? '';
    if (inQuotes) {
      if (char === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') {
      inQuotes = true;
    } else if (char === sep) {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (char !== '\r') {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((values) => values.some((value) => value.trim().length > 0));
}

export interface CsvTable {
  headers: string[];
  records: Record<string, string>[];
}

export function parseCsvTable(buffer: Buffer | Uint8Array | string): CsvTable {
  const text = typeof buffer === 'string' ? buffer : decodeBuffer(buffer);
  const rows = parseCsv(text);
  if (rows.length === 0) return { headers: [], records: [] };
  const headers = (rows[0] ?? []).map((header) => header.trim());
  const records = rows.slice(1).map((values) => {
    const record: Record<string, string> = {};
    headers.forEach((header, index) => {
      record[header] = values[index] ?? '';
    });
    return record;
  });
  return { headers, records };
}

const AMOUNT_ALIASES = ['betrag', 'amount', 'importo', 'value', 'importo in eur'];
const DATE_ALIASES = [
  'buchungsdatum',
  'date',
  'data',
  'valuta',
  'datetime',
  'data contabile',
];
const DESC_ALIASES = [
  'umsatztext',
  'buchungstext',
  'description',
  'descrizione',
  'causale',
  'name',
  'payment_reference',
  'name des partners',
  'counterparty_name',
  'descrizione operazione',
];
const CATEGORY_ALIASES = ['kategorie', 'category', 'categoria'];
const NAME_ALIASES = ['name', 'counterparty_name', 'name des partners', 'descrizione operazione'];
const TYPE_ALIASES = ['type', 'transaction_type', 'tipo'];
const TAX_ALIASES = ['tax', 'tassa', 'steuer', 'imposta'];
const FEE_ALIASES = ['fee', 'commissione', 'gebühr', 'commission'];

export interface StandardRow {
  index: number;
  Std_Amount: string;
  Std_Tax: string;
  Std_Fee: string;
  Std_Type: string;
  Std_Date: string;
  Std_Category: string;
  Std_Name: string;
  Std_Description: string;
  raw: Record<string, string>;
}

function findColumn(lowerMap: Map<string, string>, aliases: readonly string[]): string | undefined {
  for (const alias of aliases) {
    const found = lowerMap.get(alias);
    if (found) return found;
  }
  return undefined;
}

export function standardizeColumns(records: readonly Record<string, string>[]): StandardRow[] {
  if (records.length === 0) return [];
  const headers = Object.keys(records[0] ?? {});
  const lowerMap = new Map<string, string>();
  for (const header of headers) lowerMap.set(header.toLowerCase(), header);

  const amountCol = findColumn(lowerMap, AMOUNT_ALIASES);
  const taxCol = findColumn(lowerMap, TAX_ALIASES);
  const feeCol = findColumn(lowerMap, FEE_ALIASES);
  const typeCol = findColumn(lowerMap, TYPE_ALIASES);
  const dateCol = findColumn(lowerMap, DATE_ALIASES);
  const categoryCol = findColumn(lowerMap, CATEGORY_ALIASES);
  const nameCol = findColumn(lowerMap, NAME_ALIASES);
  const descCols = DESC_ALIASES.map((alias) => lowerMap.get(alias)).filter(
    (value): value is string => Boolean(value),
  );

  return records.map((record, index) => ({
    index,
    Std_Amount: amountCol ? String(record[amountCol] ?? '') : '0',
    Std_Tax: taxCol ? String(record[taxCol] ?? '') : '0',
    Std_Fee: feeCol ? String(record[feeCol] ?? '') : '0',
    Std_Type: typeCol ? String(record[typeCol] ?? '') : '',
    Std_Date: dateCol ? String(record[dateCol] ?? '') : '',
    Std_Category: categoryCol ? String(record[categoryCol] ?? '') : 'Da Categorizzare',
    Std_Name: nameCol ? String(record[nameCol] ?? '') : '',
    Std_Description: descCols
      .map((col) => String(record[col] ?? ''))
      .join(' ')
      .trim(),
    raw: record,
  }));
}

export function parseBankDate(value: string): Date | null {
  const text = String(value ?? '').trim();
  if (!text) return null;
  let match = /^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/.exec(text);
  if (match) {
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);
    const date = new Date(year, month - 1, day);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  match = /^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$/.exec(text);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(year, month - 1, day);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function monthNameEnglish(monthNumber: number): string {
  return MONTHS_EN[monthNumber - 1] ?? '';
}

export function csvEscape(value: unknown, delimiter = ','): string {
  const text = value === null || value === undefined ? '' : String(value);
  if (text.includes('"') || text.includes(delimiter) || /[\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function toCsv(headers: readonly string[], rows: readonly (readonly unknown[])[], delimiter = ','): string {
  const lines = [headers.map((header) => csvEscape(header, delimiter)).join(delimiter)];
  for (const row of rows) {
    lines.push(row.map((value) => csvEscape(value, delimiter)).join(delimiter));
  }
  return `${lines.join('\n')}\n`;
}
