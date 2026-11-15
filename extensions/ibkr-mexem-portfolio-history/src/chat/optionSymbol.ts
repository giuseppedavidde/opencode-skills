/**
 * OCC-style option symbols as the Flex report writes them, and the option
 * positions of one dataset.
 *
 * Layout: the root padded to six characters (it may contain spaces and a dot),
 * then YYMMDD, then `C` or `P`, then eight digits that hold the strike in
 * thousandths (`00320000` is 320.000). No `vscode` import, so `node --test`
 * covers the parser and the grouping without a host.
 */
import { displayPnlOf } from './context.ts';
import type { TradeRow } from '../panel/protocol.ts';

/** Standard multiplier of the US equity option contracts in this dataset. */
export const OPTION_MULTIPLIER = 100;

export interface OptionContract {
  /** Root without the padding, as written before the date. */
  readonly root: string;
  /** ISO `YYYY-MM-DD`; the century is 20xx. */
  readonly expiry: string;
  readonly kind: 'call' | 'put';
  /** Strike in trade-currency units, for example 320 for `00320000`. */
  readonly strike: number;
}

export interface OptionPosition {
  readonly contract: OptionContract;
  /** Arithmetic sum of the signed `quantity` of the rows of this contract. */
  readonly netQuantity: number;
  /** Trade currency of the rows of this contract. */
  readonly tradeCurrency: string;
  /** The rows of this contract, in dataset order. */
  readonly rows: readonly TradeRow[];
  /**
   * Trade currency. `price * 100 * quantity` summed over the rows. Positive
   * when the group paid money, negative when it received money.
   */
  readonly cashFlowPerContract: number;
  /** Display-currency sum of the per-row realized P&L. `null` when no row had a value. */
  readonly realizedPnlSum: number | null;
}

/** Root, date, kind and strike, with one or more spaces allowed between them. */
const OPTION_SYMBOL = /^(.+?)\s+(\d{2})(\d{2})(\d{2})\s*([CP])\s*(\d{8})$/;

function isoExpiry(year: string, month: string, day: string): string | null {
  const fullYear = 2000 + Number(year);
  const monthIndex = Number(month) - 1;
  const dayOfMonth = Number(day);
  if (monthIndex < 0 || monthIndex > 11 || dayOfMonth < 1 || dayOfMonth > 31) {
    return null;
  }
  const stamp = new Date(Date.UTC(fullYear, monthIndex, dayOfMonth));
  if (
    stamp.getUTCFullYear() !== fullYear ||
    stamp.getUTCMonth() !== monthIndex ||
    stamp.getUTCDate() !== dayOfMonth
  ) {
    return null;
  }
  return `${fullYear}-${String(monthIndex + 1).padStart(2, '0')}-${String(dayOfMonth).padStart(2, '0')}`;
}

/** A contract, or `null` for a stock symbol, an empty string or malformed text. */
export function parseOptionSymbol(symbol: string): OptionContract | null {
  if (typeof symbol !== 'string') {
    return null;
  }
  const match = OPTION_SYMBOL.exec(symbol.trim());
  if (!match) {
    return null;
  }
  const root = (match[1] ?? '').trim();
  const year = match[2];
  const month = match[3];
  const day = match[4];
  const kind = match[5];
  const digits = match[6];
  if (root.length === 0 || year === undefined || month === undefined || day === undefined) {
    return null;
  }
  if (digits === undefined || (kind !== 'C' && kind !== 'P')) {
    return null;
  }
  const expiry = isoExpiry(year, month, day);
  if (expiry === null) {
    return null;
  }
  const strike = Number(digits) / 1000;
  if (!Number.isFinite(strike) || strike <= 0) {
    return null;
  }
  return { root, expiry, kind: kind === 'C' ? 'call' : 'put', strike };
}

/** Identity of one contract inside one dataset: `root|expiry|kind|strike`. */
export function optionContractKey(contract: OptionContract): string {
  return `${contract.root}|${contract.expiry}|${contract.kind}|${contract.strike}`;
}

function finite(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function compareContracts(left: OptionContract, right: OptionContract): number {
  return (
    left.root.localeCompare(right.root) ||
    left.expiry.localeCompare(right.expiry) ||
    left.kind.localeCompare(right.kind) ||
    left.strike - right.strike
  );
}

interface Bucket {
  readonly contract: OptionContract;
  readonly rows: TradeRow[];
  netQuantity: number;
  cashFlowPerContract: number;
  realizedPnlSum: number;
  hasRealized: boolean;
}

/**
 * Every contract of the rows, including the closed ones, in a stable order:
 * root, expiry, kind, then strike.
 */
export function buildOptionPositions(rows: readonly TradeRow[]): OptionPosition[] {
  const buckets = new Map<string, Bucket>();
  for (const row of rows) {
    const contract = parseOptionSymbol(row.symbol);
    if (!contract) {
      continue;
    }
    const key = optionContractKey(contract);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = {
        contract,
        rows: [],
        netQuantity: 0,
        cashFlowPerContract: 0,
        realizedPnlSum: 0,
        hasRealized: false
      };
      buckets.set(key, bucket);
    }
    const quantity = finite(row.quantity);
    bucket.rows.push(row);
    bucket.netQuantity += quantity;
    bucket.cashFlowPerContract += finite(row.price) * OPTION_MULTIPLIER * quantity;
    const pnl = displayPnlOf(row);
    if (pnl !== null) {
      bucket.realizedPnlSum += pnl;
      bucket.hasRealized = true;
    }
  }
  return [...buckets.values()]
    .map((bucket) => ({
      contract: bucket.contract,
      netQuantity: bucket.netQuantity,
      tradeCurrency: bucket.rows[0]?.currency ?? '',
      rows: bucket.rows,
      cashFlowPerContract: bucket.cashFlowPerContract,
      realizedPnlSum: bucket.hasRealized ? bucket.realizedPnlSum : null
    }))
    .sort((left, right) => compareContracts(left.contract, right.contract));
}

/** The positions that are still open: a flat contract is dropped. */
export function openOptionPositions(rows: readonly TradeRow[]): OptionPosition[] {
  return buildOptionPositions(rows).filter((position) => position.netQuantity !== 0);
}
