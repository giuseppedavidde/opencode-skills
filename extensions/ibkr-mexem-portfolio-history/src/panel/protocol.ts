import type { CurrencyAnalytics } from '../analytics/metrics.ts';
import type { CommissionCurrencyRow } from '../core/currency.ts';
import type { BaseCurrencySource, ConversionRate, FormState, RangePreset } from '../core/types.ts';

/** One row of the "Trades in range" table. */
export interface TradeRow {
  readonly date: string;
  readonly time: string;
  readonly symbol: string;
  readonly buySell: string;
  readonly quantity: number;
  /** Trade currency price. */
  readonly price: number;
  /** TRADE currency of the row. Never the base currency by construction. */
  readonly currency: string;
  /** BASE currency realized P&L, or null when no result is attributable. */
  readonly realizedPnl: number | null;
  readonly pnlSource: string;
  /**
   * Realized P&L in the display currency of this payload (`DatasetPayload.displayCurrency`).
   * `null` when the row has no result or no usable FX rate.
   */
  readonly displayPnl?: number | null;
  /** False when {@link displayPnl} is a fallback or a derived conversion. */
  readonly displayPnlExact?: boolean;
  /** How {@link displayPnl} was obtained: `base`, `no-fx` or `derived`. */
  readonly displayPnlBasis?: string;
  /** Why a non-exact value is approximate, for the table tooltip. */
  readonly displayPnlNote?: string;
}

export interface DatasetMeta {
  readonly generatedAt: string;
  readonly range: { readonly preset: RangePreset; readonly start: string; readonly end: string; readonly label: string };
  readonly accountFilter: string | null;
  readonly accounts: readonly string[];
  readonly rowsTotal: number;
  readonly rowsInRange: number;
  readonly rowsWithPnl: number;
  readonly rowsPnlFromFifo: number;
  readonly rowsPnlFromProceeds: number;
  /** Account base currency (`EUR`), or `UNKNOWN` when the report carries no evidence. */
  readonly baseCurrency: string;
  readonly baseCurrencySource: BaseCurrencySource;
  /** Trade currencies present in range. P&L is NOT split by these. */
  readonly tradeCurrencies: readonly string[];
  readonly warnings: readonly string[];
}

/** Sums that make the FX effect visible, all in the account base currency. */
export interface PnlTotals {
  /** Sum of realized P&L as reported: includes the FX result. */
  readonly baseTotal: number;
  /** Sum of `capitalGainsPnl`: excludes the FX result. `null` when no row carries it. */
  readonly capitalGainsTotal: number | null;
  /** Sum of `fxPnl`. `null` when no row carries it. */
  readonly fxTotal: number | null;
  readonly rowsWithCapitalGains: number;
  readonly rowsWithFx: number;
  /** True when `baseTotal` equals `capitalGainsTotal + fxTotal` within 0.01. */
  readonly identityHolds: boolean;
}

export interface DatasetPayload {
  readonly meta: DatasetMeta;
  /** Realized P&L series is a single series in this currency. */
  readonly baseCurrency: string;
  readonly baseCurrencySource: BaseCurrencySource;
  /** Trade currencies present in range. Commissions are reported per currency. */
  readonly currencies: readonly string[];
  /** Currency the P&L series is expressed in. Equals `baseCurrency` in the base view. */
  readonly displayCurrency: string;
  /** Selectable display currencies: base first, then trade currencies with a usable rate. */
  readonly displayCurrencies: readonly string[];
  /** Every `<ConversionRate>` row of the report, for transparency and re-derivation. */
  readonly conversionRates: readonly ConversionRate[];
  /** FX-exclusion sums in the base currency, shown in every view. */
  readonly pnlTotals: PnlTotals;
  /** Analytics of the per-row values in `displayCurrency`, never a scaled base total. */
  readonly analytics: CurrencyAnalytics;
  /** Every trade in range, newest first, capped at `tradesCap` for the message channel. */
  readonly trades: readonly TradeRow[];
  /** True when `meta.rowsInRange` is larger than `tradesCap` and `trades` is capped. */
  readonly tradesTruncated: boolean;
  /** Safety ceiling applied to `trades` (the configured `maxTradeRows`). */
  readonly tradesCap: number;
  readonly commissions: readonly CommissionCurrencyRow[];
  /** Estimated total commissions in base currency. Never exact. */
  readonly commissionEstimateBase: number | null;
  readonly commissionEstimateComplete: boolean;
}

export interface SettingsSnapshot {
  readonly hasToken: boolean;
  readonly hasQueryId: boolean;
  readonly queryIdMasked: string;
  readonly accountFilter: string;
  readonly preset: RangePreset;
  readonly customStart: string;
  readonly customEnd: string;
  readonly lastFetchIso: string | null;
  readonly fallbackFromProceeds: boolean;
  /** `ibkrHistory.displayCurrency`: `base` or an ISO 4217 code. */
  readonly displayCurrency: string;
}

export type HostMessage =
  | { readonly type: 'state'; readonly settings: SettingsSnapshot; readonly deadlineMs: number; readonly maxAttempts: number }
  | { readonly type: 'busy'; readonly busy: boolean; readonly message: string }
  | {
      readonly type: 'progress';
      readonly message: string;
      readonly attempt: number;
      readonly maxAttempts: number;
      /** `send` counts SendRequest attempts; `poll` counts GetStatement polls. */
      readonly phase?: 'send' | 'poll';
      readonly elapsedMs?: number;
      readonly lastStatus?: string;
    }
  | {
      readonly type: 'data';
      readonly dataset: DatasetPayload;
      /** `fetch` replaces the dataset; `currency` only re-expresses the same rows. */
      readonly reason?: 'fetch' | 'currency';
    }
  | { readonly type: 'error'; readonly message: string; readonly fieldErrors: Readonly<Record<string, string>> }
  | { readonly type: 'info'; readonly message: string }
  | { readonly type: 'requestFetch' };

export type WebviewMessage =
  | { readonly type: 'ready' }
  | { readonly type: 'fetch'; readonly form: FormState }
  | { readonly type: 'export' }
  | { readonly type: 'displayCurrency'; readonly currency: string }
  | { readonly type: 'clearCredentials' }
  | { readonly type: 'openDocs' }
  | { readonly type: 'copyDiagnostics' }
  | { readonly type: 'cancel' };
