import type { TradeRow } from '../protocol.ts';

/** Rows per page offered by the trades table. `all` renders in incremental chunks. */
export type TradePageSize = 50 | 100 | 250 | 'all';

export type TradeSortKey = 'date' | 'symbol' | 'quantity' | 'price' | 'pnl';

export type SortDirection = 'asc' | 'desc';

export const TRADE_PAGE_SIZES: readonly TradePageSize[] = [50, 100, 250, 'all'];

export const DEFAULT_TRADE_PAGE_SIZE: TradePageSize = 100;

export const DEFAULT_TRADE_SORT_KEY: TradeSortKey = 'date';

export const DEFAULT_TRADE_SORT_DIRECTION: SortDirection = 'desc';

export interface Page<T> {
  /** Rows of the requested page, already sliced. Never the full set. */
  readonly rows: readonly T[];
  /** Clamped 1-based page number. */
  readonly page: number;
  /** Always at least 1, even for an empty set. */
  readonly pageCount: number;
  /** Number of rows the page was built from. */
  readonly total: number;
  /** 0-based index of the first returned row, inclusive. */
  readonly startIndex: number;
  /** 0-based index after the last returned row, exclusive. */
  readonly endIndex: number;
}

/**
 * Slice `rows` into a page. A page below 1 clamps to the first page, a page
 * beyond the end clamps to the last page, and `all` returns everything as page 1.
 */
export function paginate<T>(rows: readonly T[], page: number, pageSize: TradePageSize): Page<T> {
  const total = rows.length;
  if (pageSize === 'all') {
    return { rows: [...rows], page: 1, pageCount: 1, total, startIndex: 0, endIndex: total };
  }
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const requested = Number.isFinite(page) ? Math.trunc(page) : 1;
  const clamped = Math.min(Math.max(1, requested), pageCount);
  const startIndex = (clamped - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, total);
  return { rows: rows.slice(startIndex, endIndex), page: clamped, pageCount, total, startIndex, endIndex };
}

/** Parse a `<select>` value. Unknown values fall back to the default page size. */
export function parsePageSize(value: string): TradePageSize {
  if (value === 'all') {
    return 'all';
  }
  const parsed = Number.parseInt(value, 10);
  return parsed === 50 || parsed === 100 || parsed === 250 ? parsed : DEFAULT_TRADE_PAGE_SIZE;
}

/** Case-insensitive match on symbol, side and P&L source. */
export function filterTrades(rows: readonly TradeRow[], query: string): TradeRow[] {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) {
    return [...rows];
  }
  return rows.filter(
    (row) =>
      row.symbol.toLowerCase().includes(needle) ||
      row.buySell.toLowerCase().includes(needle) ||
      row.pnlSource.toLowerCase().includes(needle)
  );
}

function compareText(left: string, right: string): number {
  return left.localeCompare(right, undefined, { sensitivity: 'base' });
}

/** Stable sort. Rows without a realized P&L stay last in both directions. */
export function sortTrades(rows: readonly TradeRow[], key: TradeSortKey, direction: SortDirection): TradeRow[] {
  const factor = direction === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    switch (key) {
      case 'date':
        return compareText(`${a.date} ${a.time}`, `${b.date} ${b.time}`) * factor;
      case 'symbol':
        return (compareText(a.symbol, b.symbol) || compareText(a.date, b.date)) * factor;
      case 'quantity':
        return (a.quantity - b.quantity) * factor;
      case 'price':
        return (a.price - b.price) * factor;
      case 'pnl': {
        // The visible column is the display-currency value; fall back to the base
        // figure when a caller builds rows without it.
        const left = a.displayPnl ?? a.realizedPnl;
        const right = b.displayPnl ?? b.realizedPnl;
        if (left === null && right === null) {
          return 0;
        }
        if (left === null) {
          return 1;
        }
        if (right === null) {
          return -1;
        }
        return (left - right) * factor;
      }
      default:
        return 0;
    }
  });
}
