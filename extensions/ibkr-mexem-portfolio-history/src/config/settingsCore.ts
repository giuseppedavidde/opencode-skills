/**
 * Pure settings normalisation. No `vscode` import, so `node:test` can cover it.
 * {@link readSettings} in `settings.ts` only adds the configuration lookup.
 */
import {
  DEFAULT_DEADLINE_MS,
  DEFAULT_INITIAL_DELAY_MS,
  DEFAULT_MAX_ATTEMPTS,
  DEFAULT_MAX_DELAY_MS,
  DEFAULT_MAX_SEND_ATTEMPTS
} from '../flex/client.ts';

import { normaliseCurrencyCode } from '../core/currency.ts';

export { resolveBaseCurrencyOverride } from '../core/currency.ts';

export interface RetrySettings {
  readonly maxAttempts: number;
  readonly maxSendAttempts: number;
  readonly initialDelayMs: number;
  readonly maxDelayMs: number;
  readonly deadlineMs: number;
}

export interface RawRetrySettings {
  readonly maxAttempts?: number | undefined;
  readonly maxSendAttempts?: number | undefined;
  readonly initialDelayMs?: number | undefined;
  readonly maxDelayMs?: number | undefined;
  readonly deadlineMs?: number | undefined;
}

export interface NumberBounds {
  readonly min: number;
  readonly max: number;
}

/** Bounds mirrored by `contributes.configuration` in package.json. */
export const RETRY_BOUNDS: Readonly<Record<keyof RetrySettings, NumberBounds>> = {
  maxAttempts: { min: 5, max: 1_000 },
  maxSendAttempts: { min: 1, max: 10 },
  initialDelayMs: { min: 250, max: 60_000 },
  maxDelayMs: { min: 1_000, max: 120_000 },
  deadlineMs: { min: 30_000, max: 3_600_000 }
};

export const REQUEST_TIMEOUT_BOUNDS: NumberBounds = { min: 1_000, max: 120_000 };
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

export function clampNumber(value: number | undefined, min: number, max: number, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, Math.round(value)));
}

export function resolveRetrySettings(raw: RawRetrySettings): RetrySettings {
  const initialDelayMs = clampNumber(
    raw.initialDelayMs,
    RETRY_BOUNDS.initialDelayMs.min,
    RETRY_BOUNDS.initialDelayMs.max,
    DEFAULT_INITIAL_DELAY_MS
  );
  const maxDelayMs = clampNumber(
    raw.maxDelayMs,
    RETRY_BOUNDS.maxDelayMs.min,
    RETRY_BOUNDS.maxDelayMs.max,
    DEFAULT_MAX_DELAY_MS
  );
  return {
    maxAttempts: clampNumber(
      raw.maxAttempts,
      RETRY_BOUNDS.maxAttempts.min,
      RETRY_BOUNDS.maxAttempts.max,
      DEFAULT_MAX_ATTEMPTS
    ),
    maxSendAttempts: clampNumber(
      raw.maxSendAttempts,
      RETRY_BOUNDS.maxSendAttempts.min,
      RETRY_BOUNDS.maxSendAttempts.max,
      DEFAULT_MAX_SEND_ATTEMPTS
    ),
    initialDelayMs,
    // A cap below the initial delay would make the backoff shrink instead of grow.
    maxDelayMs: Math.max(initialDelayMs, maxDelayMs),
    deadlineMs: clampNumber(
      raw.deadlineMs,
      RETRY_BOUNDS.deadlineMs.min,
      RETRY_BOUNDS.deadlineMs.max,
      DEFAULT_DEADLINE_MS
    )
  };
}

/**
 * Normalise `ibkrHistory.displayCurrency`. `base` means the account base
 * currency; any real ISO 4217 code is kept; anything else falls back to `base`.
 */
export function resolveDisplayCurrencySetting(value: string | null | undefined): string {
  const trimmed = (value ?? '').trim();
  if (!trimmed || trimmed.toLowerCase() === 'base') {
    return 'base';
  }
  return normaliseCurrencyCode(trimmed) || 'base';
}

export function resolveRequestTimeoutMs(value: number | undefined): number {
  return clampNumber(value, REQUEST_TIMEOUT_BOUNDS.min, REQUEST_TIMEOUT_BOUNDS.max, DEFAULT_REQUEST_TIMEOUT_MS);
}
