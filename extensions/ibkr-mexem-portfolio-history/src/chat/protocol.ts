/** Message protocol between the chat view (webview) and its host. */

export interface ModelOption {
  readonly id: string;
  readonly label: string;
}

/** `lm` uses `vscode.lm` and the provider signed in to VS Code; `http` posts to `baseUrl`. */
export type ChatBackend = 'lm' | 'http';

export interface ContextBadge {
  readonly trades: number;
  readonly baseCurrency: string;
  readonly generatedAt: string;
  readonly approxTokens: number;
  readonly presetLabel: string;
}

export interface ChatStateMessage {
  readonly type: 'state';
  readonly backend: ChatBackend;
  readonly notice: string;
  readonly models: readonly ModelOption[];
  readonly model: string;
  readonly hasApiKey: boolean;
  readonly keySource: string | null;
}

export type ChatHostMessage =
  | ChatStateMessage
  | { readonly type: 'context'; readonly available: boolean; readonly badge: ContextBadge | null }
  | { readonly type: 'delta'; readonly text: string }
  | { readonly type: 'done'; readonly text: string }
  | { readonly type: 'error'; readonly message: string }
  | { readonly type: 'busy'; readonly busy: boolean }
  | { readonly type: 'cleared' }
  | { readonly type: 'info'; readonly message: string };

export type ChatWebviewMessage =
  | { readonly type: 'ready' }
  | { readonly type: 'send'; readonly text: string }
  | { readonly type: 'stop' }
  | { readonly type: 'clear' }
  | { readonly type: 'copyTranscript'; readonly text: string }
  | { readonly type: 'fetchReport' }
  | { readonly type: 'handoff' }
  | { readonly type: 'setModel'; readonly model: string };

/** Default backend: the VS Code Language Model API. */
export const DEFAULT_CHAT_BACKEND: ChatBackend = 'lm';

/** Persistent notice for the `lm` backend. */
export const CHAT_NOTICE_LM =
  'Portfolio data is sent to the VS Code language model provider. Option prices, when enabled, come from yfinance.';

/** Persistent notice for the `http` backend. */
export const CHAT_NOTICE_HTTP = 'Portfolio data is sent to opencode.ai. Option prices, when enabled, come from yfinance.';

/** The persistent notice that matches the active backend. */
export function chatNotice(backend: ChatBackend): string {
  return backend === 'http' ? CHAT_NOTICE_HTTP : CHAT_NOTICE_LM;
}

/** Shown when `vscode.lm.selectChatModels` returns nothing. */
export const NO_LANGUAGE_MODEL_MESSAGE =
  'No VS Code language model is available. Install and sign in to a language model provider, or set ibkrHistory.chat.backend to http.';

/**
 * Fallback model list for the `http` backend only.
 *
 * @deprecated The `lm` backend reads the list from `vscode.lm.selectChatModels`.
 * Keep this list for `ibkrHistory.chat.backend = http`; do not grow it.
 */
export const MODEL_OPTIONS: readonly ModelOption[] = [
  { id: 'glm-5.3', label: 'GLM 5.3' },
  { id: 'glm-5.2', label: 'GLM 5.2' },
  { id: 'glm-5.1', label: 'GLM 5.1' },
  { id: 'kimi-k2.7-code', label: 'Kimi K2.7 Code' },
  { id: 'kimi-k2.6', label: 'Kimi K2.6' },
  { id: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
  { id: 'deepseek-v4-flash-vision-exp', label: 'DeepSeek V4 Flash Vision (experimental)' },
  { id: 'deepseek-v4-pro', label: 'DeepSeek V4 Pro' },
  { id: 'mimo-v2.5', label: 'MiMo v2.5' },
  { id: 'mimo-v2.5-pro', label: 'MiMo v2.5 Pro' },
  { id: 'minimax-m3', label: 'MiniMax M3' },
  { id: 'minimax-m2.7', label: 'MiniMax M2.7' },
  { id: 'qwen3.7-max', label: 'Qwen 3.7 Max' },
  { id: 'qwen3.7-plus', label: 'Qwen 3.7 Plus' },
  { id: 'qwen3.6-plus', label: 'Qwen 3.6 Plus' }
];

/**
 * Preferred model id. In `lm` mode it is a preference: `selectModel` falls back
 * to an exact family match, then to the first available model, so an id this
 * list does not know still works.
 *
 * TODO: confirm the id that the opencode-go Copilot provider exposes for
 * DeepSeek V4.1 Flash (`vscode.lm.selectChatModels` at runtime) and use it here.
 * The value below is a valid id for the `http` backend.
 */
export const DEFAULT_CHAT_MODEL = 'deepseek-v4-pro';
