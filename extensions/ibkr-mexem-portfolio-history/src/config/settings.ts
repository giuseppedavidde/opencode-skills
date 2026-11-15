import * as vscode from 'vscode';
import type { RetrySettings } from './settingsCore.ts';
import {
  resolveBaseCurrencyOverride,
  resolveDisplayCurrencySetting,
  resolveRequestTimeoutMs,
  resolveRetrySettings
} from './settingsCore.ts';

export interface ExtensionSettings extends RetrySettings {
  readonly requestTimeoutMs: number;
  readonly fallbackFromProceeds: boolean;
  /** `null` means `auto`: detect the base currency from the report. */
  readonly baseCurrency: string | null;
  /** P&L display currency: `base` or an ISO 4217 code. */
  readonly displayCurrency: string;
}

/**
 * Reads user settings. `FlexClient` never touches the configuration itself: the
 * values are injected by the panel controller, which keeps the client pure.
 */
export function readSettings(): ExtensionSettings {
  const config = vscode.workspace.getConfiguration('ibkrHistory');
  return {
    ...resolveRetrySettings({
      maxAttempts: config.get<number>('retry.maxAttempts'),
      maxSendAttempts: config.get<number>('retry.maxSendAttempts'),
      initialDelayMs: config.get<number>('retry.initialDelayMs'),
      maxDelayMs: config.get<number>('retry.maxDelayMs'),
      deadlineMs: config.get<number>('retry.deadlineMs')
    }),
    requestTimeoutMs: resolveRequestTimeoutMs(config.get<number>('requestTimeoutMs')),
    fallbackFromProceeds: config.get<boolean>('pnl.fallbackFromProceeds', true),
    baseCurrency: resolveBaseCurrencyOverride(config.get<string>('baseCurrency', 'auto')),
    displayCurrency: resolveDisplayCurrencySetting(config.get<string>('displayCurrency', 'base'))
  };
}
