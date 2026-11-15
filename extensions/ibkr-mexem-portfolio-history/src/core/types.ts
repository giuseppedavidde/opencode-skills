/**
 * Where a realized P&L value came from.
 * - `fifo`: read directly from the Flex `fifoPnlRealized` field.
 * - `proceeds`: approximated from the closing leg's `netCashInBase` (base currency).
 * - `none`: no realized P&L is attributable to the row (typically an opening trade).
 */
export type PnlSource = 'fifo' | 'proceeds' | 'none';

/**
 * Where the account base currency came from.
 * - `account`: `<AccountInformation currency="...">` in the report.
 * - `conversionRates`: the unanimous `toCurrency` of every `<ConversionRate>`.
 * - `override`: the `ibkrHistory.baseCurrency` setting.
 * - `unknown`: the report carries no base currency evidence.
 */
export type BaseCurrencySource = 'account' | 'conversionRates' | 'override' | 'unknown';

/** One `<ConversionRate>` row. `toCurrency` is the account base currency. */
export interface ConversionRate {
  /** Raw `reportDate` as written by IBKR (`20260102` or `2026-01-02`). */
  readonly reportDate: string;
  readonly fromCurrency: string;
  readonly toCurrency: string;
  readonly rate: number;
}

/**
 * Currency invariant, valid for every parsed row:
 * - `realizedPnl`, `fifoPnlRealized`, `netCashInBase` and `cost` are **base currency**.
 * - `commission`, `netCash`, `proceeds` and `tradePrice` are **trade currency**
 *   (`currency`). Never add a trade-currency amount to a base-currency amount.
 */
export interface Trade {
  readonly symbol: string;
  readonly description: string;
  readonly assetCategory: string;
  readonly tradeDate: string;
  readonly tradeTime: string;
  /** Local (naive) epoch milliseconds built from tradeDate + tradeTime. */
  readonly timestamp: number;
  readonly buySell: string;
  readonly quantity: number;
  /** Trade currency. */
  readonly tradePrice: number;
  /** Trade currency. */
  readonly proceeds: number;
  /** Commission exactly as reported by IB (normally negative), trade currency. */
  readonly commission: number;
  /** Absolute commission cost, trade currency. */
  readonly commissionCost: number;
  /** Net cash of the execution, trade currency. */
  readonly netCash: number;
  /** Net cash of the execution converted by IBKR to the account base currency. */
  readonly netCashInBase: number | null;
  /** Trade currency code (`USD`, `EUR`, ...). Never the base currency by construction. */
  readonly currency: string;
  readonly exchange: string;
  readonly orderReference: string;
  readonly accountId: string;
  readonly openCloseIndicator: string;
  /** Base currency. Same unit as {@link realizedPnl}. */
  readonly fifoPnlRealized: number | null;
  /**
   * Base currency. Realized capital gain, excluding the FX result. IBKR writes it
   * only when the Flex query includes the field, so it is `null` otherwise.
   * `capitalGainsPnl + fxPnl = fifoPnlRealized` for a closing row.
   */
  readonly capitalGainsPnl: number | null;
  /** Base currency. FX result of the enclosing round trip; `null` when absent. */
  readonly fxPnl: number | null;
  /** Base currency. See the currency invariant above. */
  readonly realizedPnl: number | null;
  readonly pnlSource: PnlSource;
  /** Epoch ms of the opening execution, only when the report carries openDate/openDateTime. */
  readonly openTimestamp: number | null;
}

export interface DateRange {
  readonly preset: RangePreset;
  readonly start: string;
  readonly end: string;
}

export type RangePreset = 'ytd' | 'last30' | 'last90' | 'last365' | 'custom';

export const RANGE_PRESETS: readonly RangePreset[] = ['ytd', 'last30', 'last90', 'last365', 'custom'];

export const RANGE_PRESET_LABELS: Readonly<Record<RangePreset, string>> = {
  ytd: 'Year to date',
  last30: 'Last 30 days',
  last90: 'Last 90 days',
  last365: 'Last 365 days',
  custom: 'Custom range'
};

/** Structural checks shared with the webview, so both sides reject the same input. */
export interface FormState {
  readonly token: string;
  readonly queryId: string;
  readonly preset: RangePreset;
  readonly customStart: string;
  readonly customEnd: string;
  readonly accountId: string;
}
