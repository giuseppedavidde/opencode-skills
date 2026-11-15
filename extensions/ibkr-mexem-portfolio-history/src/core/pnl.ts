/**
 * Per-row realized P&L in a requested display currency. Pure: no `vscode`
 * import, so the panel, the CSV export and `node:test` share one rule.
 *
 * Why a conversion and not a scale factor: IBKR reports `fifoPnlRealized` in the
 * account base currency and that figure INCLUDES the FX result (`fxPnl`).
 * `capitalGainsPnl` excludes it. A trade-currency P&L is the capital gain
 * divided by the FX rate of the trade date, so the FX effect is not counted
 * twice. The two totals are therefore not a unit conversion of each other.
 */
import type { Trade } from './types.ts';
import { normaliseCurrencyCode } from './currency.ts';
import type { RateTable } from './rates.ts';

/** How a row figure was obtained. */
export type PnlBasis =
  /** `fifoPnlRealized` as reported, base currency, includes the FX result. */
  | 'base'
  /** `capitalGainsPnl / rate(tradeCcy → base)`, excludes the FX result. */
  | 'no-fx'
  /** Base-currency figure converted through the table into a third currency. */
  | 'derived';

export interface PnlInCurrency {
  readonly value: number | null;
  readonly basis: PnlBasis;
  /** False when the value is a conversion of a conversion, or a fallback. */
  readonly exact: boolean;
  /** Short human reason for a non-exact value, for the table tooltip. */
  readonly reason?: string;
}

function basisFor(trade: Trade, target: string, base: string): PnlBasis {
  if (target === base) {
    return 'base';
  }
  return target === normaliseCurrencyCode(trade.currency) ? 'no-fx' : 'derived';
}

/**
 * Realized P&L of one row in `target`, or `null` when no rate is available.
 * Rows without a realized P&L (`realizedPnl === null`) stay `null` in every
 * currency: an opening trade has no result to convert.
 */
export function pnlInCurrency(trade: Trade, target: string, rates: RateTable): PnlInCurrency {
  const wanted = normaliseCurrencyCode(target);
  const base = normaliseCurrencyCode(rates.baseCurrency);
  const tradeCurrency = normaliseCurrencyCode(trade.currency);
  const basis = basisFor(trade, wanted, base);

  if (trade.realizedPnl === null || !Number.isFinite(trade.realizedPnl)) {
    return { value: null, basis, exact: true };
  }
  // A currency the report does not name can never be derived.
  if (!wanted || !base) {
    return { value: null, basis: 'derived', exact: false, reason: 'the account base currency is unknown' };
  }
  if (wanted === base) {
    return { value: trade.realizedPnl, basis: 'base', exact: true };
  }

  if (wanted === tradeCurrency) {
    const rate = rates.rate(tradeCurrency, base, trade.tradeDate);
    if (rate === null) {
      return {
        value: null,
        basis: 'no-fx',
        exact: false,
        reason: `no ${tradeCurrency}→${base} rate on or before ${trade.tradeDate}`
      };
    }
    if (trade.capitalGainsPnl !== null && Number.isFinite(trade.capitalGainsPnl)) {
      return { value: trade.capitalGainsPnl / rate, basis: 'no-fx', exact: true };
    }
    return {
      value: trade.realizedPnl / rate,
      basis: 'no-fx',
      exact: false,
      reason: 'capitalGainsPnl is absent: the base figure was converted, so the FX result is included'
    };
  }

  const rate = rates.rate(base, wanted, trade.tradeDate);
  if (rate === null) {
    return {
      value: null,
      basis: 'derived',
      exact: false,
      reason: `no ${base}→${wanted} rate on or before ${trade.tradeDate}`
    };
  }
  return {
    value: trade.realizedPnl * rate,
    basis: 'derived',
    exact: false,
    reason: 'converted from the base-currency figure, so the FX result is included'
  };
}
