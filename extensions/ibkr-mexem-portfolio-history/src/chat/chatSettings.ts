/**
 * Chat settings resolution. `vscode`-free on purpose: `readChatSettings` in the
 * view provider passes the VS Code configuration, `node --test` passes a fake.
 * The defaults mirror `contributes.configuration` in `package.json`.
 */
import { DEFAULT_CHAT_BACKEND, DEFAULT_CHAT_MODEL } from './protocol.ts';
import type { ChatBackend } from './protocol.ts';

export const DEFAULT_CHAT_BASE_URL = 'https://opencode.ai/zen/go/v1';
export const DEFAULT_CHAT_TEMPERATURE = 0.3;
export const DEFAULT_CHAT_MAX_TOKENS = 2048;
export const DEFAULT_CHAT_MAX_CONTEXT_TRADES = 400;
export const DEFAULT_CHAT_MAX_HISTORY_MESSAGES = 20;
export const DEFAULT_CHAT_MARKET_DATA = true;
/**
 * The local trading CLI that already fetches option chains on this machine.
 * `marketDataService.ts` appends `fetch options <TICKER> --expiry <DATE>`.
 */
export const DEFAULT_CHAT_MARKET_DATA_COMMAND =
  '~/.local/share/opencode/trading-mcp-venv/bin/python -m trading_mcp.trading_cli';

export interface ChatSettings {
  readonly backend: ChatBackend;
  readonly model: string;
  readonly baseUrl: string;
  readonly temperature: number;
  readonly maxTokens: number;
  readonly maxContextTrades: number;
  readonly maxHistoryMessages: number;
  /** Append the live option block of the open option positions to the context. */
  readonly marketData: boolean;
  /** Whitespace-separated command template of the local trading CLI. */
  readonly marketDataCommand: string;
}

/** The `get` overload of `vscode.WorkspaceConfiguration` this module needs. */
export interface ChatSettingsSource {
  get<T>(section: string, defaultValue: T): T;
}

function clamp(value: number | undefined, min: number, max: number, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, value));
}

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : fallback;
}

/** Only a real boolean turns the live option block on or off; anything else keeps the default. */
export function resolveMarketData(value: unknown): boolean {
  return typeof value === 'boolean' ? value : DEFAULT_CHAT_MARKET_DATA;
}

/** Only `http` selects the HTTP backend; anything else falls back to `lm`. */
export function resolveChatBackend(value: unknown): ChatBackend {
  return value === 'http' ? 'http' : DEFAULT_CHAT_BACKEND;
}

export function resolveChatSettings(config: ChatSettingsSource): ChatSettings {
  return {
    backend: resolveChatBackend(config.get<unknown>('chat.backend', DEFAULT_CHAT_BACKEND)),
    model: text(config.get<unknown>('chat.model', DEFAULT_CHAT_MODEL), DEFAULT_CHAT_MODEL),
    baseUrl: text(config.get<unknown>('chat.baseUrl', DEFAULT_CHAT_BASE_URL), DEFAULT_CHAT_BASE_URL),
    temperature: clamp(config.get<number>('chat.temperature', DEFAULT_CHAT_TEMPERATURE), 0, 2, DEFAULT_CHAT_TEMPERATURE),
    maxTokens: Math.round(clamp(config.get<number>('chat.maxTokens', DEFAULT_CHAT_MAX_TOKENS), 64, 32_000, DEFAULT_CHAT_MAX_TOKENS)),
    maxContextTrades: Math.round(
      clamp(
        config.get<number>('chat.maxContextTrades', DEFAULT_CHAT_MAX_CONTEXT_TRADES),
        10,
        5000,
        DEFAULT_CHAT_MAX_CONTEXT_TRADES
      )
    ),
    maxHistoryMessages: Math.round(
      clamp(
        config.get<number>('chat.maxHistoryMessages', DEFAULT_CHAT_MAX_HISTORY_MESSAGES),
        2,
        200,
        DEFAULT_CHAT_MAX_HISTORY_MESSAGES
      )
    ),
    marketData: resolveMarketData(config.get<unknown>('chat.marketData', DEFAULT_CHAT_MARKET_DATA)),
    marketDataCommand: text(
      config.get<unknown>('chat.marketDataCommand', DEFAULT_CHAT_MARKET_DATA_COMMAND),
      DEFAULT_CHAT_MARKET_DATA_COMMAND
    )
  };
}
