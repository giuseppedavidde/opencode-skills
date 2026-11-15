import type { Trade } from '../core/types.ts';
import { normaliseCurrencyCode } from '../core/currency.ts';
import { pnlInCurrency } from '../core/pnl.ts';
import type { RateTable } from '../core/rates.ts';

export const CSV_COLUMNS = [
  'accountId',
  'currency',
  'symbol',
  'description',
  'assetCategory',
  'exchange',
  'tradeDate',
  'tradeTime',
  'buySell',
  'quantity',
  'tradePrice',
  'proceeds',
  'commission',
  'netCash',
  'openCloseIndicator',
  'fifoPnlRealized',
  'realizedPnl',
  'pnlSource',
  'orderReference'
] as const;

export interface CsvOptions {
  /** P&L display currency of the export. When absent no extra column is written. */
  readonly displayCurrency?: string;
  /** FX table of the report. Required for the extra column to carry a value. */
  readonly rateTable?: RateTable;
}

/**
 * Header of the export. `realizedPnl` is always the account base currency, as
 * IBKR reports it (and includes the FX result). When a display currency is
 * requested, one extra column carries the same row converted to that currency.
 */
export function csvColumns(options: CsvOptions = {}): string[] {
  const columns: string[] = [...CSV_COLUMNS];
  const extra = extraColumn(options);
  if (extra) {
    columns.push(extra);
  }
  return columns;
}

function extraColumn(options: CsvOptions): string | null {
  const currency = normaliseCurrencyCode(options.displayCurrency);
  if (!currency || !options.rateTable) {
    return null;
  }
  return `realized_pnl_${currency}`;
}

function needsQuoting(value: string): boolean {
  return /[",\r\n]/.test(value) || /^\s|\s$/.test(value);
}

export function escapeCsvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return '';
  }
  const text = typeof value === 'number' ? (Number.isFinite(value) ? String(value) : '') : value;
  if (needsQuoting(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function rowOf(trade: Trade, extra: number | null): string {
  const cells = [
    trade.accountId,
    trade.currency,
    trade.symbol,
    trade.description,
    trade.assetCategory,
    trade.exchange,
    trade.tradeDate,
    trade.tradeTime,
    trade.buySell,
    trade.quantity,
    trade.tradePrice,
    trade.proceeds,
    trade.commission,
    trade.netCash,
    trade.openCloseIndicator,
    trade.fifoPnlRealized,
    trade.realizedPnl,
    trade.pnlSource,
    trade.orderReference
  ];
  if (extra !== null) {
    cells.push(extra);
  }
  return cells.map(escapeCsvField).join(',');
}

/** Plain CSV with a header row and no metadata block, ready for Excel. */
export function tradesToCsv(trades: readonly Trade[], options: CsvOptions = {}): string {
  const column = extraColumn(options);
  const rates = options.rateTable;
  const currency = normaliseCurrencyCode(options.displayCurrency);
  const lines = [csvColumns(options).join(',')];
  for (const trade of trades) {
    const extra = column && rates ? pnlInCurrency(trade, currency, rates).value : null;
    lines.push(rowOf(trade, column ? extra : null));
  }
  return `${lines.join('\r\n')}\r\n`;
}
