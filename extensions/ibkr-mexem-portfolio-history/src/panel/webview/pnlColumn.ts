/**
 * One decision point for the realized P&L column: the currency used to format
 * every cell, the table header label and the summary badge.
 *
 * The trades table, the header and the summary cards all read this model, so
 * the formatted cell currency cannot diverge from the header currency again
 * (the 0.7.0 bug: header in USD, cells in the base currency).
 *
 * No DOM and no `vscode` import, so `node:test` covers the exact strings.
 */

export interface PnlColumnModel {
  /** Currency used to format every P&L value of the column. */
  readonly currency: string;
  /** Table header, for example `Realized P&L (USD, excluding FX)`. */
  readonly header: string;
  /** Summary badge, for example `P&L in USD · trade currency, excluding FX`. */
  readonly badge: string;
  /** True when {@link currency} is the account base currency. */
  readonly isBaseView: boolean;
  /** False when the requested display currency is not a usable ISO code. */
  readonly known: boolean;
}

export interface PnlColumnInput {
  /** Account base currency of the dataset, for example `EUR`, or `UNKNOWN`. */
  readonly baseCurrency: string;
  /** Currency requested for the P&L series of this payload. */
  readonly displayCurrency: string;
  /** ISO-code predicate, injected so the module stays dependency free. */
  readonly isKnownCurrency: (code: string) => boolean;
}

/**
 * Resolve the currency, the header and the badge of the P&L column.
 *
 * `displayCurrency` wins when it is a known currency, otherwise the base
 * currency is used and the header says `(base)`.
 */
export function resolvePnlColumn(input: PnlColumnInput): PnlColumnModel {
  const base = input.baseCurrency;
  const requested = input.displayCurrency;
  const known = input.isKnownCurrency(requested);
  const currency = known ? requested : base;
  const isBaseView = currency === base;

  if (!known) {
    return {
      currency,
      header: 'Realized P&L (base)',
      badge: 'P&L currency unknown',
      isBaseView,
      known
    };
  }
  if (isBaseView) {
    return {
      currency,
      header: `Realized P&L (${currency} base, including FX)`,
      badge: `P&L in ${currency} · account base currency`,
      isBaseView,
      known
    };
  }
  return {
    currency,
    header: `Realized P&L (${currency}, excluding FX)`,
    badge: `P&L in ${currency} · trade currency, excluding FX`,
    isBaseView,
    known
  };
}
