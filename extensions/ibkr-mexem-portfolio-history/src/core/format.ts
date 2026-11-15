/**
 * Amount formatting shared by the webview and the tests. No DOM and no `vscode`
 * import, so `node:test` covers the exact string the panel shows.
 */
import { isKnownCurrency, UNKNOWN_CURRENCY } from './currency.ts';

const formatters = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  const cached = formatters.get(currency);
  if (cached) {
    return cached;
  }
  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  formatters.set(currency, formatter);
  return formatter;
}

/**
 * Format a base-currency amount. A real ISO code renders its symbol (`€756.80`).
 * An unknown base currency renders a plain number plus ` base` and never a
 * currency symbol: `1234.56 base`.
 */
export function formatBaseAmount(value: number | null | undefined, baseCurrency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  if (!isKnownCurrency(baseCurrency)) {
    return `${value.toFixed(2)} base`;
  }
  return formatterFor(baseCurrency.toUpperCase()).format(value);
}

/** Format an amount in a trade currency. Unknown codes fall back to ` base`. */
export function formatTradeAmount(value: number | null | undefined, tradeCurrency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  if (!isKnownCurrency(tradeCurrency)) {
    return `${value.toFixed(2)} ${UNKNOWN_CURRENCY.toLowerCase()}`;
  }
  return formatterFor(tradeCurrency.toUpperCase()).format(value);
}
