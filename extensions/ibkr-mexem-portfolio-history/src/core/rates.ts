/**
 * FX lookup built from the report's `<ConversionRate>` rows. Pure: no `vscode`
 * import, no I/O, so `node:test` covers every rule.
 *
 * Direction rule: a row says how many units of `toCurrency` one unit of
 * `fromCurrency` is worth. `<ConversionRate fromCurrency="USD" toCurrency="EUR"
 * rate="0.90455" />` therefore means **1 USD = 0.90455 EUR**.
 *
 * Fallback rule: an exact `reportDate` match wins. Without an exact match the
 * table uses the row with the closest **earlier** report date. A later row is
 * never used, because that would price a trade with information the account did
 * not have yet.
 */
import type { ConversionRate } from './types.ts';
import { normaliseCurrencyCode } from './currency.ts';
import { parseFlexDate } from './dates.ts';

interface RatePoint {
  readonly time: number;
  readonly rate: number;
}

function timeOf(reportDate: string): number {
  const parsed = parseFlexDate(reportDate);
  return parsed ? parsed.getTime() : Number.NaN;
}

/**
 * One direction of one currency pair: all rows sharing `(from, to)`, sorted by
 * `reportDate` ascending so the nearest earlier row is the last one that is not
 * after the target date.
 */
class RateSeries {
  private readonly points: RatePoint[];

  constructor(rows: readonly ConversionRate[]) {
    this.points = rows
      .map((row) => ({ time: timeOf(row.reportDate), rate: row.rate }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.rate) && point.rate > 0)
      .sort((a, b) => a.time - b.time);
  }

  get isEmpty(): boolean {
    return this.points.length === 0;
  }

  /** Exact date, else the nearest earlier date; `null` when neither exists. */
  at(date: string): number | null {
    const target = timeOf(date);
    if (!Number.isFinite(target) || this.points.length === 0) {
      return null;
    }
    let candidate: number | null = null;
    for (const point of this.points) {
      if (point.time === target) {
        return point.rate;
      }
      if (point.time < target) {
        candidate = point.rate;
      }
    }
    return candidate;
  }

  /** The newest rate of the series, used only to answer "is this pair present". */
  get newest(): number | null {
    const last = this.points[this.points.length - 1];
    return last ? last.rate : null;
  }
}

export class RateTable {
  private readonly direct = new Map<string, RateSeries>();
  private readonly inverse = new Map<string, RateSeries>();
  /** Account base currency, so a caller can label the result without a second argument. */
  readonly baseCurrency: string;

  constructor(rates: readonly ConversionRate[], baseCurrency: string) {
    this.baseCurrency = normaliseCurrencyCode(baseCurrency);
    const groups = new Map<string, ConversionRate[]>();
    for (const row of rates) {
      const from = normaliseCurrencyCode(row.fromCurrency);
      const to = normaliseCurrencyCode(row.toCurrency);
      if (!from || !to || from === to || !Number.isFinite(row.rate) || row.rate <= 0) {
        continue;
      }
      const key = `${from}->${to}`;
      const bucket = groups.get(key);
      if (bucket) {
        bucket.push(row);
      } else {
        groups.set(key, [row]);
      }
    }
    for (const [key, rows] of groups) {
      const series = new RateSeries(rows);
      if (series.isEmpty) {
        continue;
      }
      this.direct.set(key, series);
      // The inverse direction answers 1/rate with the same date rule.
      const [from, to] = key.split('->');
      const inverseKey = `${to}->${from}`;
      if (!groups.has(inverseKey)) {
        this.inverse.set(inverseKey, series);
      }
    }
  }

  /** True when at least one row can price the pair, directly or inverted. */
  has(from: string, to: string): boolean {
    const source = normaliseCurrencyCode(from);
    const target = normaliseCurrencyCode(to);
    if (!source || !target) {
      return false;
    }
    if (source === target) {
      return true;
    }
    return this.direct.has(`${source}->${target}`) || this.inverse.has(`${source}->${target}`);
  }

  /**
   * Units of `to` per one unit of `from` on `date`.
   * - Same currency: `1`.
   * - No row for the pair, directly or inverted: `null`. The table never guesses
   *   a cross rate through a third currency.
   */
  rate(from: string, to: string, date: string): number | null {
    const source = normaliseCurrencyCode(from);
    const target = normaliseCurrencyCode(to);
    if (!source || !target) {
      return null;
    }
    if (source === target) {
      return 1;
    }
    const directSeries = this.direct.get(`${source}->${target}`);
    if (directSeries) {
      return directSeries.at(date);
    }
    const inverseSeries = this.inverse.get(`${source}->${target}`);
    if (inverseSeries) {
      const value = inverseSeries.at(date);
      return value === null || value <= 0 ? null : 1 / value;
    }
    return null;
  }
}
