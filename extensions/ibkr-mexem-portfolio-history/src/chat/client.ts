/**
 * OpenAI-compatible streaming client for the opencode-go provider.
 *
 * `vscode`-free on purpose: the extension injects the key and the fetch
 * implementation, and `node:test` drives every branch with fakes. The key is
 * never logged and never appears in an error message.
 */

export type ChatRole = 'system' | 'user' | 'assistant';

export interface ChatMessage {
  readonly role: ChatRole;
  readonly content: string;
}

export const DEFAULT_TEMPERATURE = 0.3;
export const DEFAULT_MAX_TOKENS = 2048;
export const DEFAULT_MAX_HISTORY_MESSAGES = 20;
export const DEFAULT_TIMEOUT_MS = 120_000;

/** Thrown for a mapping error. `message` is safe to show: it carries no key. */
export class ChatError extends Error {
  readonly status: number | undefined;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ChatError';
    this.status = status;
  }
}

/** Replace anything that looks like a bearer token or an `sk-` secret. */
export function redactTokens(text: string, secrets: readonly (string | undefined)[] = []): string {
  let result = text;
  for (const secret of secrets) {
    if (secret && secret.length >= 8) {
      result = result.split(secret).join('***');
    }
  }
  return result
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer ***')
    .replace(/\bsk-[A-Za-z0-9._-]{8,}/g, 'sk-***');
}

/**
 * One SSE line to its data payload, or `undefined` for a comment line, an empty
 * line, an `event:` line or any field other than `data`.
 * Accepts `data: {...}` and `data:{...}`.
 */
export function sseDataOf(line: string): string | undefined {
  if (line.length === 0 || line.startsWith(':')) {
    return undefined;
  }
  if (!line.startsWith('data:')) {
    return undefined;
  }
  const value = line.slice('data:'.length);
  return value.startsWith(' ') ? value.slice(1) : value;
}

export type SseParseResult =
  | { readonly kind: 'done' }
  | { readonly kind: 'delta'; readonly text: string }
  | { readonly kind: 'ignore' };

/** Parse one `data:` payload. A malformed JSON line is ignored, never thrown. */
export function parseSseData(data: string): SseParseResult {
  if (data.trim() === '[DONE]') {
    return { kind: 'done' };
  }
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return { kind: 'ignore' };
  }
  if (typeof payload !== 'object' || payload === null) {
    return { kind: 'ignore' };
  }
  const choices = (payload as { choices?: unknown }).choices;
  if (!Array.isArray(choices) || choices.length === 0) {
    return { kind: 'ignore' };
  }
  const first: unknown = choices[0];
  if (typeof first !== 'object' || first === null) {
    return { kind: 'ignore' };
  }
  const delta = (first as { delta?: unknown }).delta;
  if (typeof delta !== 'object' || delta === null) {
    return { kind: 'ignore' };
  }
  const content = (delta as { content?: unknown }).content;
  if (typeof content !== 'string' || content.length === 0) {
    return { kind: 'ignore' };
  }
  return { kind: 'delta', text: content };
}

/**
 * Incremental line splitter. An object split across two chunks is reassembled
 * because the buffer only emits complete lines.
 */
export class SseDecoder {
  private buffer = '';

  push(chunk: string): string[] {
    this.buffer += chunk;
    const payloads: string[] = [];
    let index = this.buffer.indexOf('\n');
    while (index >= 0) {
      const raw = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 1);
      const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
      const data = sseDataOf(line);
      if (data !== undefined) {
        payloads.push(data);
      }
      index = this.buffer.indexOf('\n');
    }
    return payloads;
  }

  /** Emit a final line that arrived without a trailing newline. */
  flush(): string[] {
    if (this.buffer.length === 0) {
      return [];
    }
    const line = this.buffer.endsWith('\r') ? this.buffer.slice(0, -1) : this.buffer;
    this.buffer = '';
    const data = sseDataOf(line);
    return data === undefined ? [] : [data];
  }
}

/** Human message for an HTTP status. Never includes the request headers. */
export function mapHttpError(status: number, detail = ''): string {
  const tail = detail.trim().length > 0 ? ` Detail: ${detail.trim().slice(0, 200)}` : '';
  if (status === 401) {
    return `API key rejected (HTTP 401). Run "IBKR History: Set Chat API Key" and check the key.${tail}`;
  }
  if (status === 402) {
    return `Quota exhausted (HTTP 402). Check your opencode-go plan, then retry.${tail}`;
  }
  if (status === 429) {
    return `Rate limit reached (HTTP 429). Wait a few seconds, then use Retry.${tail}`;
  }
  if (status === 404) {
    return `Model name unknown (HTTP 404). Pick another model in the dropdown.${tail}`;
  }
  if (status >= 500 && status <= 599) {
    return `The chat service returned an error (HTTP ${status}). Retry in a moment.${tail}`;
  }
  return `Chat request failed (HTTP ${status}).${tail}`;
}

/**
 * Keep the system message(s) and the newest `maxMessages` turns. The oldest
 * messages go first; a leading assistant message is dropped so the history
 * always starts with a user turn.
 */
export function trimHistory(messages: readonly ChatMessage[], maxMessages: number): ChatMessage[] {
  const system = messages.filter((message) => message.role === 'system');
  const turns = messages.filter((message) => message.role !== 'system');
  const limit = Math.max(2, Math.trunc(maxMessages));
  let kept = turns.length > limit ? turns.slice(turns.length - limit) : [...turns];
  while (kept.length > 0 && kept[0]?.role !== 'user') {
    kept = kept.slice(1);
  }
  return [...system, ...kept];
}

export interface RequestBodyOptions {
  readonly model: string;
  readonly messages: readonly ChatMessage[];
  readonly temperature?: number;
  readonly maxTokens?: number;
}

export function buildChatRequestBody(options: RequestBodyOptions): Record<string, unknown> {
  return {
    model: options.model,
    stream: true,
    temperature: options.temperature ?? DEFAULT_TEMPERATURE,
    max_tokens: options.maxTokens ?? DEFAULT_MAX_TOKENS,
    messages: options.messages.map((message) => ({ role: message.role, content: message.content }))
  };
}

export function chatCompletionsUrl(baseUrl: string): string {
  return `${baseUrl.replace(/\/+$/, '')}/chat/completions`;
}

export interface ChatCompletionOptions extends RequestBodyOptions {
  readonly baseUrl: string;
  readonly apiKey: string;
  readonly timeoutMs?: number;
  readonly signal?: AbortSignal;
  readonly fetchImpl?: typeof globalThis.fetch;
  readonly onDelta?: (text: string) => void;
}

export interface ChatCompletionResult {
  readonly text: string;
}

async function readErrorBody(response: Response): Promise<string> {
  try {
    return redactTokens(await response.text());
  } catch {
    return '';
  }
}

/** POST one streaming completion. Resolves with the full assistant text. */
export async function streamChatCompletion(options: ChatCompletionOptions): Promise<ChatCompletionResult> {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error('timeout')), timeoutMs);
  const onCallerAbort = (): void => controller.abort(options.signal?.reason);
  if (options.signal) {
    if (options.signal.aborted) {
      clearTimeout(timer);
      throw new ChatError('The chat request was cancelled.');
    }
    options.signal.addEventListener('abort', onCallerAbort, { once: true });
  }

  const cleanup = (): void => {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', onCallerAbort);
  };

  try {
    const response = await fetchImpl(chatCompletionsUrl(options.baseUrl), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${options.apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'text/event-stream'
      },
      body: JSON.stringify(buildChatRequestBody(options)),
      signal: controller.signal
    });

    if (!response.ok) {
      const detail = redactTokens(await readErrorBody(response), [options.apiKey]);
      throw new ChatError(mapHttpError(response.status, detail), response.status);
    }

    const decoder = new SseDecoder();
    const textDecoder = new TextDecoder();
    let text = '';
    let done = false;

    const consume = (payloads: readonly string[]): void => {
      for (const payload of payloads) {
        const parsed = parseSseData(payload);
        if (parsed.kind === 'done') {
          done = true;
          continue;
        }
        if (parsed.kind === 'delta') {
          text += parsed.text;
          options.onDelta?.(parsed.text);
        }
      }
    };

    if (response.body === null) {
      consume(decoder.push(await response.text()));
      consume(decoder.flush());
      return { text };
    }

    const reader = response.body.getReader();
    while (!done) {
      const chunk = await reader.read();
      if (chunk.done) {
        break;
      }
      consume(decoder.push(textDecoder.decode(chunk.value, { stream: true })));
    }
    if (!done) {
      consume(decoder.push(textDecoder.decode()));
      consume(decoder.flush());
    }
    await reader.cancel().catch(() => undefined);
    return { text };
  } catch (error) {
    if (error instanceof ChatError) {
      throw error;
    }
    if (controller.signal.aborted) {
      if (options.signal?.aborted) {
        throw new ChatError('The chat request was cancelled.');
      }
      throw new ChatError(`The chat request timed out after ${timeoutMs} ms. Use Retry.`);
    }
    const message = error instanceof Error ? error.message : String(error);
    throw new ChatError(`Network error: ${redactTokens(message, [options.apiKey])}`);
  } finally {
    cleanup();
  }
}
