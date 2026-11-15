import type * as vscode from 'vscode';
import type { RangePreset } from '../core/types.ts';

const TOKEN_KEY = 'ibkrHistory.flexToken';
const QUERY_ID_KEY = 'ibkrHistory.queryId';
const ACCOUNT_FILTER_KEY = 'ibkrHistory.accountFilter';
const LAST_PRESET_KEY = 'ibkrHistory.lastPreset';
const LAST_FETCH_KEY = 'ibkrHistory.lastFetchIso';
const DISPLAY_CURRENCY_KEY = 'ibkrHistory.displayCurrency';

/**
 * Secrets live in VS Code SecretStorage (OS keyring backed). They are never
 * written to settings.json, never sent to the webview and never logged.
 */
export class CredentialStore {
  private readonly secrets: vscode.SecretStorage;
  private readonly state: vscode.Memento;

  constructor(secrets: vscode.SecretStorage, state: vscode.Memento) {
    this.secrets = secrets;
    this.state = state;
  }

  async getToken(): Promise<string | undefined> {
    return this.secrets.get(TOKEN_KEY);
  }

  async setToken(token: string): Promise<void> {
    await this.secrets.store(TOKEN_KEY, token);
  }

  async clearToken(): Promise<void> {
    await this.secrets.delete(TOKEN_KEY);
  }

  async getQueryId(): Promise<string | undefined> {
    return this.secrets.get(QUERY_ID_KEY);
  }

  async setQueryId(queryId: string): Promise<void> {
    await this.secrets.store(QUERY_ID_KEY, queryId);
  }

  async clearQueryId(): Promise<void> {
    await this.secrets.delete(QUERY_ID_KEY);
  }

  getAccountFilter(): string {
    return this.state.get<string>(ACCOUNT_FILTER_KEY, '') ?? '';
  }

  async setAccountFilter(value: string): Promise<void> {
    await this.state.update(ACCOUNT_FILTER_KEY, value);
  }

  getLastPreset(): RangePreset {
    return this.state.get<RangePreset>(LAST_PRESET_KEY, 'ytd') ?? 'ytd';
  }

  async setLastPreset(preset: RangePreset): Promise<void> {
    await this.state.update(LAST_PRESET_KEY, preset);
  }

  getLastFetchIso(): string | undefined {
    return this.state.get<string>(LAST_FETCH_KEY);
  }

  async setLastFetchIso(value: string): Promise<void> {
    await this.state.update(LAST_FETCH_KEY, value);
  }

  /** Last P&L currency chosen in the panel: `base` or an ISO 4217 code. */
  getDisplayCurrency(): string | undefined {
    return this.state.get<string>(DISPLAY_CURRENCY_KEY);
  }

  async setDisplayCurrency(value: string): Promise<void> {
    await this.state.update(DISPLAY_CURRENCY_KEY, value);
  }

  async hasToken(): Promise<boolean> {
    const token = await this.getToken();
    return Boolean(token && token.length > 0);
  }

  async hasQueryId(): Promise<boolean> {
    const queryId = await this.getQueryId();
    return Boolean(queryId && queryId.length > 0);
  }
}
