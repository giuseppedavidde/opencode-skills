import { RANGE_PRESETS } from './types.ts';
import type { DateRange, RangePreset } from './types.ts';

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const COMPACT_DATE = /^(\d{4})(\d{2})(\d{2})$/;

function pad(value: number, width = 2): string {
  return String(value).padStart(width, '0');
}

/** Format a Date as YYYY-MM-DD using its local calendar fields. */
export function formatIsoDate(date: Date): string {
  return `${pad(date.getFullYear(), 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Local midnight for the given date. Returns null for impossible calendar dates. */
export function parseIsoDate(value: string): Date | null {
  const match = ISO_DATE.exec(value.trim());
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day, 0, 0, 0, 0);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

/** Accepts both `2024-01-31` and `20240131` (IB emits both in different reports). */
export function parseFlexDate(value: string): Date | null {
  const direct = parseIsoDate(value);
  if (direct) {
    return direct;
  }
  const compact = COMPACT_DATE.exec(value.trim());
  if (!compact) {
    return null;
  }
  return parseIsoDate(`${compact[1]}-${compact[2]}-${compact[3]}`);
}

export function todayLocal(now: Date = new Date()): string {
  return formatIsoDate(now);
}

function addDays(date: Date, days: number): Date {
  const copy = new Date(date.getTime());
  copy.setDate(copy.getDate() + days);
  return copy;
}

export interface ResolveRangeFailure {
  readonly ok: false;
  readonly message: string;
}

export interface ResolveRangeSuccess {
  readonly ok: true;
  readonly range: DateRange;
}

export type ResolveRangeResult = ResolveRangeSuccess | ResolveRangeFailure;

/**
 * Resolve a preset (or a custom pair) against a reference "now".
 * `lastNN` means NN calendar days ending today, inclusive on both ends.
 */
export function resolveRange(
  preset: RangePreset,
  customStart = '',
  customEnd = '',
  now: Date = new Date()
): ResolveRangeResult {
  if (!RANGE_PRESETS.includes(preset)) {
    return { ok: false, message: `Unknown date range preset: ${String(preset)}` };
  }
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);

  switch (preset) {
    case 'ytd':
      return {
        ok: true,
        range: { preset, start: formatIsoDate(new Date(today.getFullYear(), 0, 1)), end: formatIsoDate(today) }
      };
    case 'last30':
      return { ok: true, range: { preset, start: formatIsoDate(addDays(today, -29)), end: formatIsoDate(today) } };
    case 'last90':
      return { ok: true, range: { preset, start: formatIsoDate(addDays(today, -89)), end: formatIsoDate(today) } };
    case 'last365':
      return { ok: true, range: { preset, start: formatIsoDate(addDays(today, -364)), end: formatIsoDate(today) } };
    case 'custom': {
      const start = parseIsoDate(customStart);
      const end = parseIsoDate(customEnd);
      if (!start) {
        return { ok: false, message: 'Custom start date must be a valid date in YYYY-MM-DD format.' };
      }
      if (!end) {
        return { ok: false, message: 'Custom end date must be a valid date in YYYY-MM-DD format.' };
      }
      if (start.getTime() > end.getTime()) {
        return { ok: false, message: 'Range start must be earlier than or equal to range end.' };
      }
      return {
        ok: true,
        range: { preset, start: formatIsoDate(start), end: formatIsoDate(end) }
      };
    }
    default:
      return { ok: false, message: `Unknown date range preset: ${String(preset)}` };
  }
}

/** Inclusive [start 00:00:00.000, end 23:59:59.999] window from ISO dates. */
export function rangeToMs(range: { start: string; end: string }): { startMs: number; endMs: number } {
  const start = parseIsoDate(range.start);
  const end = parseIsoDate(range.end);
  if (!start || !end) {
    throw new Error(`Invalid range: ${range.start}..${range.end}`);
  }
  return { startMs: start.getTime(), endMs: end.getTime() + 86_400_000 - 1 };
}

export function filterTradesByRange<T extends { readonly timestamp: number }>(
  trades: readonly T[],
  startMs: number,
  endMs: number
): T[] {
  return trades.filter((trade) => Number.isFinite(trade.timestamp) && trade.timestamp >= startMs && trade.timestamp <= endMs);
}

export function filterTradesByAccount<T extends { readonly accountId: string }>(
  trades: readonly T[],
  accountId: string
): T[] {
  const needle = accountId.trim().toUpperCase();
  if (!needle) {
    return [...trades];
  }
  return trades.filter((trade) => trade.accountId.toUpperCase() === needle);
}
