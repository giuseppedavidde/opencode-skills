/**
 * Base-currency helpers. No `vscode` import: the parser, the dataset builder,
 * the webview and `node:test` all share this module.
 */
import type { ConversionRate, Trade } from './types.ts';
import { parseFlexDate } from './dates.ts';

/** Sentinel used when the report carries no base-currency evidence. */
export const UNKNOWN_CURRENCY = 'UNKNOWN';

const ISO_CURRENCY = /^[A-Z]{3}$/;

export function normaliseCurrencyCode(value: string | null | undefined): string {
  const trimmed = (value ?? '').trim().toUpperCase();
  return ISO_CURRENCY.test(trimmed) ? trimmed : '';
}

/** True for a real three-letter ISO code, false for `UNKNOWN` and blanks. */
export function isKnownCurrency(value: string | null | undefined): boolean {
  return normaliseCurrencyCode(value).length === 3;
}

/**
 * Apply the `ibkrHistory.baseCurrency` setting to the detected value.
 * `auto` (or an invalid override) keeps detection. The returned code is always
 * upper case and is `UNKNOWN` when neither source provides one.
 */
export function resolveBaseCurrency(detected: string | null | undefined, override?: string | null): string {
  const overrideCode = normaliseCurrencyCode(override);
  if (overrideCode && (override ?? '').trim().toLowerCase() !== 'auto') {
    return overrideCode;
  }
  const detectedCode = normaliseCurrencyCode(detected);
  return detectedCode || UNKNOWN_CURRENCY;
}

/** Normalise the `ibkrHistory.baseCurrency` setting: `null` means "use detection". */
export function resolveBaseCurrencyOverride(value: string | null | undefined): string | null {
  const trimmed = (value ?? '').trim();
  if (!trimmed || trimmed.toLowerCase() === 'auto') {
    return null;
  }
  return normaliseCurrencyCode(trimmed) || null;
}

/**
 * Pick the conversion rate for one trade: the rate row whose `reportDate` is
 * closest to the trade date, for the same currency pair. Returns `null` when no
 * rate covers the pair, or `1` when the currencies already match.
 */
export function selectConversionRate(
  rates: readonly ConversionRate[],
  fromCurrency: string,
  toCurrency: string,
  tradeDate: string
): number | null {
  const from = normaliseCurrencyCode(fromCurrency);
  const to = normaliseCurrencyCode(toCurrency);
  if (!from || !to) {
    return null;
  }
  if (from === to) {
    return 1;
  }
  const target = parseFlexDate(tradeDate);
  let bestRate: number | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const row of rates) {
    if (row.fromCurrency !== from || row.toCurrency !== to || !Number.isFinite(row.rate) || row.rate <= 0) {
      continue;
    }
    const reportDate = parseFlexDate(row.reportDate);
    const distance =
      target && reportDate ? Math.abs(reportDate.getTime() - target.getTime()) : Number.POSITIVE_INFINITY;
    if (bestRate === null || distance < bestDistance) {
      bestRate = row.rate;
      bestDistance = distance;
    }
  }
  return bestRate;
}

export interface CommissionCurrencyRow {
  /** Trade currency of the commission amounts. */
  readonly currency: string;
  readonly trades: number;
  /** Sum of `commissionCost` in the trade currency. */
  readonly commissionCost: number;
  /** Rate applied to the newest trade of this currency, for transparency. */
  readonly fxRate: number | null;
  /** Sum in the base currency, converted per trade with the nearest report rate. */
  readonly estimatedBase: number | null;
  /** False when at least one trade of this currency had no usable conversion rate. */
  readonly complete: boolean;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Commissions ARE per trade currency, unlike realized P&L. This groups them and
 * adds a clearly-labelled estimate in the base currency, converted per trade
 * with the `ConversionRate` whose `reportDate` is closest to that trade.
 */
export function commissionsByTradeCurrency(
  trades: readonly Trade[],
  rates: readonly ConversionRate[],
  baseCurrency: string
): CommissionCurrencyRow[] {
  const base = normaliseCurrencyCode(baseCurrency);
  const groups = new Map<string, { trades: number; commissionCost: number; estimatedBase: number; complete: boolean; fxRate: number | null }>();

  for (const trade of trades) {
    const currency = normaliseCurrencyCode(trade.currency) || UNKNOWN_CURRENCY;
    const bucket = groups.get(currency) ?? { trades: 0, commissionCost: 0, estimatedBase: 0, complete: true, fxRate: null };
    bucket.trades += 1;
    bucket.commissionCost += trade.commissionCost;
    const rate = base ? selectConversionRate(rates, currency, base, trade.tradeDate) : null;
    if (rate === null) {
      bucket.complete = false;
    } else {
      bucket.estimatedBase += trade.commissionCost * rate;
      bucket.fxRate = rate;
    }
    groups.set(currency, bucket);
  }

  return [...groups.entries()]
    .map(([currency, bucket]) => ({
      currency,
      trades: bucket.trades,
      commissionCost: round2(bucket.commissionCost),
      fxRate: bucket.fxRate,
      estimatedBase: base ? round2(bucket.estimatedBase) : null,
      complete: bucket.complete
    }))
    .sort((a, b) => a.currency.localeCompare(b.currency));
}

/** Sum of the per-currency estimates. `null` when the base currency is unknown. */
export function estimateCommissionsInBase(rows: readonly CommissionCurrencyRow[], baseCurrency: string): number | null {
  if (!isKnownCurrency(baseCurrency)) {
    return null;
  }
  return round2(rows.reduce((sum, row) => sum + (row.estimatedBase ?? 0), 0));
}

/** True when every commission row has a base estimate. */
export function commissionEstimateComplete(rows: readonly CommissionCurrencyRow[], baseCurrency: string): boolean {
  return isKnownCurrency(baseCurrency) && rows.every((row) => row.estimatedBase !== null && row.complete);
}
