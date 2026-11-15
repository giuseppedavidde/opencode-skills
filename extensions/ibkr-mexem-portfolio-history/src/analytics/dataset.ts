import type { BaseCurrencySource, ConversionRate, DateRange, Trade } from '../core/types.ts';
import { RANGE_PRESET_LABELS } from '../core/types.ts';
import {
  commissionEstimateComplete,
  commissionsByTradeCurrency,
  estimateCommissionsInBase,
  isKnownCurrency,
  normaliseCurrencyCode,
  UNKNOWN_CURRENCY
} from '../core/currency.ts';
import { pnlInCurrency } from '../core/pnl.ts';
import type { PnlInCurrency } from '../core/pnl.ts';
import { RateTable } from '../core/rates.ts';
import { computeAnalytics } from './metrics.ts';
import type { CurrencyAnalytics } from './metrics.ts';
import type { DatasetPayload, PnlTotals, TradeRow } from '../panel/protocol.ts';

export interface BuildDatasetInput {
  /** Trades already filtered by date range and account. */
  readonly trades: readonly Trade[];
  /** Total rows returned by IBKR before filtering. */
  readonly rowsTotal: number;
  readonly range: DateRange;
  readonly accountFilter: string;
  readonly generatedAt: Date;
  /**
   * Safety ceiling on `payload.trades`, to keep the webview message channel sane.
   * The table shows every row up to this cap and reports the real total in
   * `meta.rowsInRange`. Defaults to 5000.
   */
  readonly maxTradeRows?: number;
  /** Detected or overridden account base currency. Defaults to `UNKNOWN`. */
  readonly baseCurrency?: string;
  readonly baseCurrencySource?: BaseCurrencySource;
  /** `<ConversionRate>` rows of the report, used for commissions and P&L conversion. */
  readonly conversionRates?: readonly ConversionRate[];
  /**
   * P&L display currency: `base` (default) or an ISO 4217 code. An unavailable
   * code falls back to the base currency, never to a silent cross rate.
   */
  readonly displayCurrency?: string;
}

function round4(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function toTradeRow(trade: Trade, view: PnlInCurrency): TradeRow {
  return {
    date: trade.tradeDate,
    time: trade.tradeTime,
    symbol: trade.symbol,
    buySell: trade.buySell,
    quantity: trade.quantity,
    price: trade.tradePrice,
    currency: trade.currency,
    realizedPnl: trade.realizedPnl,
    pnlSource: trade.pnlSource,
    displayPnl: view.value,
    displayPnlExact: view.exact,
    displayPnlBasis: view.basis,
    displayPnlNote: view.reason
  };
}

/** Default ceiling on `payload.trades`. Never a silent drop: `tradesTruncated` reports it. */
export const DEFAULT_MAX_TRADE_ROWS = 5000;

/** Stable descending sort. Rows without a timestamp go last, as in `sortByTimestamp`. */
export function sortByTimestampDescending(trades: readonly Trade[]): Trade[] {
  return [...trades].sort((a, b) => {
    const left = Number.isFinite(a.timestamp) ? a.timestamp : Number.MIN_SAFE_INTEGER;
    const right = Number.isFinite(b.timestamp) ? b.timestamp : Number.MIN_SAFE_INTEGER;
    return right - left;
  });
}

/**
 * Resolve the display currency a request asks for. `base` (or anything that is
 * not offered) means the account base currency.
 */
export function resolveDisplayCurrency(
  requested: string | null | undefined,
  baseCurrency: string,
  available: readonly string[]
): string {
  const raw = (requested ?? '').trim();
  const wanted = normaliseCurrencyCode(raw);
  if (wanted && available.includes(wanted)) {
    return wanted;
  }
  if (available.includes(baseCurrency)) {
    return baseCurrency;
  }
  return available[0] ?? baseCurrency;
}

/**
 * Selectable display currencies: the account base currency first, then every
 * trade currency of the dataset whose pair with the base currency has a rate.
 */
export function resolveDisplayCurrencies(
  baseCurrency: string,
  tradeCurrencies: readonly string[],
  rates: RateTable
): string[] {
  const options: string[] = [];
  if (isKnownCurrency(baseCurrency)) {
    options.push(baseCurrency);
  }
  for (const code of tradeCurrencies) {
    if (options.includes(code)) {
      continue;
    }
    if (isKnownCurrency(baseCurrency) && (rates.has(code, baseCurrency) || rates.has(baseCurrency, code))) {
      options.push(code);
    }
  }
  return options;
}

/** FX-exclusion sums over the filtered rows, always in the account base currency. */
export function computePnlTotals(trades: readonly Trade[]): PnlTotals {
  let baseTotal = 0;
  let capitalGains = 0;
  let fx = 0;
  let rowsWithCapitalGains = 0;
  let rowsWithFx = 0;
  for (const trade of trades) {
    if (trade.realizedPnl !== null && Number.isFinite(trade.realizedPnl)) {
      baseTotal += trade.realizedPnl;
    }
    if (trade.capitalGainsPnl !== null && Number.isFinite(trade.capitalGainsPnl)) {
      capitalGains += trade.capitalGainsPnl;
      rowsWithCapitalGains += 1;
    }
    if (trade.fxPnl !== null && Number.isFinite(trade.fxPnl)) {
      fx += trade.fxPnl;
      rowsWithFx += 1;
    }
  }
  const capitalGainsTotal = rowsWithCapitalGains > 0 ? round4(capitalGains) : null;
  const fxTotal = rowsWithFx > 0 ? round4(fx) : null;
  const rounded = round4(baseTotal);
  return {
    baseTotal: rounded,
    capitalGainsTotal,
    fxTotal,
    rowsWithCapitalGains,
    rowsWithFx,
    identityHolds:
      capitalGainsTotal !== null && fxTotal !== null && Math.abs(rounded - (capitalGainsTotal + fxTotal)) <= 0.01
  };
}

/**
 * One dataset, one P&L series, in the selected display currency. Realized P&L,
 * gross profit/loss, profit factor, win rate, drawdown, the cumulative curve,
 * monthly bars, P&L by symbol and the histogram all use the per-row value of
 * that currency, never a scaled base total. Only commissions are kept per trade
 * currency.
 */
export function buildDataset(input: BuildDatasetInput): DatasetPayload {
  const tradesCap = Math.max(1, Math.trunc(input.maxTradeRows ?? DEFAULT_MAX_TRADE_ROWS));
  const tradesNewestFirst = sortByTimestampDescending(input.trades);
  const tradesTruncated = tradesNewestFirst.length > tradesCap;
  const baseCurrency = input.baseCurrency ?? UNKNOWN_CURRENCY;
  const baseCurrencySource: BaseCurrencySource =
    input.baseCurrencySource ?? (isKnownCurrency(baseCurrency) ? 'conversionRates' : 'unknown');
  const conversionRates = input.conversionRates ?? [];
  const rates = new RateTable(conversionRates, baseCurrency);

  const tradeCurrencies = [...new Set(input.trades.map((trade) => trade.currency).filter((code) => code.length > 0))].sort(
    (a, b) => a.localeCompare(b)
  );
  const accounts = [...new Set(input.trades.map((trade) => trade.accountId).filter((id) => id.length > 0))].sort();
  const rowsPnlFromFifo = input.trades.filter((trade) => trade.pnlSource === 'fifo').length;
  const rowsPnlFromProceeds = input.trades.filter((trade) => trade.pnlSource === 'proceeds').length;
  const warnings: string[] = [];

  const displayCurrencies = resolveDisplayCurrencies(baseCurrency, tradeCurrencies, rates);
  const displayCurrency = resolveDisplayCurrency(input.displayCurrency, baseCurrency, displayCurrencies);

  if (!isKnownCurrency(baseCurrency)) {
    warnings.push(
      'The account base currency could not be detected: the report has no AccountInformation currency and no ConversionRate rows. ' +
        'P&L values are shown as plain numbers with the suffix "base". Set ibkrHistory.baseCurrency to override detection.'
    );
  }
  if (tradeCurrencies.length > 1) {
    warnings.push(
      `This report covers ${tradeCurrencies.length} trade currencies (${tradeCurrencies.join(', ')}). ` +
        `Realized P&L is reported by IBKR in the account base currency (${baseCurrency}) and is shown as one series. ` +
        'Commissions and notional amounts remain in their own trade currency.'
    );
  }
  if (rowsPnlFromProceeds > 0) {
    warnings.push(
      `${rowsPnlFromProceeds} closing trade(s) had no fifoPnlRealized value, so realized P&L was approximated from ` +
        'netCashInBase. The approximation is in the base currency and is not an IBKR figure. ' +
        'Add the "FIFO P/L Realized" field to the Flex query to avoid the approximation.'
    );
  }
  if (input.trades.length === 0) {
    warnings.push('No trades fall inside the selected date range and account filter.');
  }
  if (tradesTruncated) {
    warnings.push(
      `The trades table is capped at maxTradeRows (${tradesCap}): only the newest ${tradesCap} of ` +
        `${tradesNewestFirst.length} trades in range are sent to the panel. The charts and statistics use all ` +
        `${tradesNewestFirst.length} rows. Narrow the date range or the account filter to see the rest in the table.`
    );
  }
  if (accounts.length > 1) {
    warnings.push(`Trades from ${accounts.length} accounts are included: ${accounts.join(', ')}. Use the account filter to isolate one.`);
  }
  warnings.push(
    'The Flex Web Service has no date-range parameter: IBKR returned the period configured in the saved query, ' +
      `and this panel filtered it locally to ${input.range.start} → ${input.range.end}.`
  );

  // Per-row value in the selected currency. The base view keeps fifoPnlRealized
  // untouched, so the fast path cannot drift from the reported figure.
  const views = input.trades.map((trade) => pnlInCurrency(trade, displayCurrency, rates));
  const unconverted = input.trades.filter(
    (trade, index) => trade.realizedPnl !== null && (views[index]?.value ?? null) === null
  ).length;
  const fallbackRows =
    displayCurrency === baseCurrency
      ? 0
      : input.trades.filter((trade, index) => views[index]?.exact === false && views[index]?.value !== null).length;

  if (displayCurrency !== baseCurrency && unconverted > 0) {
    warnings.push(
      `${unconverted} trade(s) could not be converted to ${displayCurrency}. ` +
        'Those rows are excluded from the P&L statistics and charts of this view; the count is reported here, not hidden.'
    );
  }
  if (fallbackRows > 0) {
    warnings.push(
      `${fallbackRows} trade(s) in ${displayCurrency} use an approximate conversion, marked ~ in the table. ` +
        'Either capitalGainsPnl is absent, or the row is in a third currency: in both cases the base figure was ' +
        'converted through the report rates, so the FX result is included in that figure.'
    );
  }

  const adjustedTrades =
    displayCurrency === baseCurrency
      ? input.trades
      : input.trades.map((trade, index) => ({ ...trade, realizedPnl: views[index]?.value ?? null }));

  let analytics: CurrencyAnalytics = computeAnalytics(adjustedTrades, { currency: displayCurrency });
  if (displayCurrency !== baseCurrency) {
    // Holding period and commissions do not depend on the P&L currency: keep the
    // base-view values instead of letting the converted series change them.
    const reference = computeAnalytics(input.trades, { currency: baseCurrency });
    analytics = {
      ...analytics,
      stats: {
        ...analytics.stats,
        totalCommissions: reference.stats.totalCommissions,
        averageHoldingDays: reference.stats.averageHoldingDays
      }
    };
  }

  const commissions = commissionsByTradeCurrency(input.trades, conversionRates, baseCurrency);
  const viewsByTrade = new Map(input.trades.map((trade, index) => [trade, views[index]]));

  const cappedTrades = tradesTruncated ? tradesNewestFirst.slice(0, tradesCap) : tradesNewestFirst;

  return {
    meta: {
      generatedAt: input.generatedAt.toISOString(),
      range: {
        preset: input.range.preset,
        start: input.range.start,
        end: input.range.end,
        label: RANGE_PRESET_LABELS[input.range.preset]
      },
      accountFilter: input.accountFilter.trim() || null,
      accounts,
      rowsTotal: input.rowsTotal,
      rowsInRange: input.trades.length,
      rowsWithPnl: input.trades.filter((trade) => trade.realizedPnl !== null).length,
      rowsPnlFromFifo,
      rowsPnlFromProceeds,
      baseCurrency,
      baseCurrencySource,
      tradeCurrencies,
      warnings
    },
    baseCurrency,
    baseCurrencySource,
    currencies: tradeCurrencies,
    displayCurrency,
    displayCurrencies,
    conversionRates: [...conversionRates],
    pnlTotals: computePnlTotals(input.trades),
    analytics,
    trades: cappedTrades.map((trade) => toTradeRow(trade, viewsByTrade.get(trade) ?? pnlInCurrency(trade, displayCurrency, rates))),
    tradesTruncated,
    tradesCap,
    commissions,
    commissionEstimateBase: estimateCommissionsInBase(commissions, baseCurrency),
    commissionEstimateComplete: commissionEstimateComplete(commissions, baseCurrency)
  };
}
