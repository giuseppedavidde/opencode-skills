import * as fs from 'node:fs';
import * as path from 'node:path';
import {
  DEFAULT_BASE_URL,
  DEFAULT_USER_AGENT,
  MODELS_PATH,
  buildChatRequest,
  createToolCallState,
  finalizeToolCalls,
  mergeToolCallDeltas,
  parseAuthKey,
  parseCompletionJson,
  parseSseLine,
  splitSseLines,
  type OpenAiMessage,
  type ParsedToolCall,
  type ToolCallDelta,
  type ToolSpec,
  type UsageInfo,
} from './opencodeGo';

export const DEFAULT_TIMEOUT_MS = 120_000;
export const AUTH_FILE_RELATIVE = path.join('.local', 'share', 'opencode', 'auth.json');

export function defaultAuthPath(homeDir: string): string {
  return path.join(homeDir, AUTH_FILE_RELATIVE);
}

export function readAuthKeyFromFile(file: string): string | null {
  try {
    return parseAuthKey(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

export function authKeyPresence(file: string): { exists: boolean; hasKey: boolean } {
  const exists = fs.existsSync(file);
  return { exists, hasKey: exists && readAuthKeyFromFile(file) !== null };
}

export interface HttpErrorInfo {
  status: number;
  retryable: boolean;
  message: string;
}

export function describeHttpError(status: number, bodyText: string): HttpErrorInfo {
  const body = bodyText.trim().slice(0, 500);
  if (status === 401 || status === 403) {
    return {
      status,
      retryable: false,
      message:
        'OpenCode Go rejected the API key. Run "opencode auth login" to refresh ~/.local/share/opencode/auth.json, then reload the window.',
    };
  }
  if (status === 400 && /MissingSessionID/i.test(body)) {
    return {
      status,
      retryable: false,
      message: 'OpenCode Go requires the x-opencode-session header, but the request did not send it.',
    };
  }
  if (status === 404) {
    return {
      status,
      retryable: false,
      message: `OpenCode Go endpoint or model not found (HTTP 404). Check tradeAssistant.chat.model. ${body}`,
    };
  }
  if (status === 429) {
    return {
      status,
      retryable: false,
      message:
        'OpenCode Go quota is exhausted (HTTP 429). Retry later or set tradeAssistant.chat.provider to copilot.',
    };
  }
  if (status >= 500) {
    return { status, retryable: true, message: `OpenCode Go is temporarily unavailable (HTTP ${status}). Retry in a moment.` };
  }
  return { status, retryable: false, message: `OpenCode Go request failed (HTTP ${status}). ${body}` };
}

export interface OpencodeGoClientOptions {
  apiKey: string;
  model: string;
  sessionId: string;
  baseUrl?: string;
  timeoutMs?: number;
  userAgent?: string;
  fetchImpl?: typeof fetch;
}

export interface StreamChatInput {
  messages: OpenAiMessage[];
  tools?: ToolSpec[];
  temperature?: number;
  signal?: AbortSignal;
  onDelta?: (text: string) => void;
  onToolCallDelta?: (delta: ToolCallDelta) => void;
}

export interface StreamChatResult {
  text: string;
  toolCalls: ParsedToolCall[];
  finishReason: string;
  usage: UsageInfo | null;
}

export class OpencodeGoClient {
  private readonly options: OpencodeGoClientOptions;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(options: OpencodeGoClientOptions) {
    this.options = options;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const globalFetch = (globalThis as { fetch?: typeof fetch }).fetch;
    const impl = options.fetchImpl ?? globalFetch;
    if (!impl) {
      throw new Error('Global fetch is not available. Update VS Code to 1.95 or newer.');
    }
    this.fetchImpl = impl;
  }

  get model(): string {
    return this.options.model;
  }

  get sessionId(): string {
    return this.options.sessionId;
  }

  async listModels(): Promise<string[]> {
    const url = `${this.baseUrl}${MODELS_PATH}`;
    const response = await this.request(url, { method: 'GET' }, undefined, true);
    let parsed: unknown;
    try {
      parsed = await response.json();
    } catch {
      throw new Error('OpenCode Go returned a models response that is not JSON.');
    }
    const data = parsed && typeof parsed === 'object' ? (parsed as { data?: unknown }).data : undefined;
    if (!Array.isArray(data)) {
      return [];
    }
    const ids: string[] = [];
    for (const entry of data) {
      if (entry && typeof entry === 'object') {
        const id = (entry as { id?: unknown }).id;
        if (typeof id === 'string' && id.trim().length > 0) {
          ids.push(id.trim());
        }
      }
    }
    return ids;
  }

  async streamChat(input: StreamChatInput): Promise<StreamChatResult> {
    const request = buildChatRequest({
      baseUrl: this.baseUrl,
      apiKey: this.options.apiKey,
      model: this.options.model,
      sessionId: this.options.sessionId,
      messages: input.messages,
      tools: input.tools ?? [],
      stream: true,
      temperature: input.temperature,
      userAgent: this.options.userAgent ?? DEFAULT_USER_AGENT,
    });
    const controller = new AbortController();
    this.controller = controller;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);
    const onExternalAbort = (): void => controller.abort();
    input.signal?.addEventListener('abort', onExternalAbort, { once: true });
    try {
      const response = await this.request(
        request.url,
        { method: 'POST', body: JSON.stringify(request.body) },
        controller.signal,
        false
      );
      const result = await this.consume(response, input);
      return result;
    } catch (error) {
      if (timedOut) {
        throw new Error(`OpenCode Go request timed out after ${this.timeoutMs} ms.`);
      }
      if (input.signal?.aborted) {
        throw new Error('Stopped by user.');
      }
      throw error;
    } finally {
      clearTimeout(timer);
      input.signal?.removeEventListener('abort', onExternalAbort);
      if (this.controller === controller) {
        this.controller = undefined;
      }
    }
  }

  abort(): void {
    this.controller?.abort();
  }

  dispose(): void {
    this.disposed = true;
    this.abort();
  }

  private async consume(response: Response, input: StreamChatInput): Promise<StreamChatResult> {
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.toLowerCase().includes('text/event-stream')) {
      const bodyText = await response.text();
      const parsed = parseCompletionJson(bodyText);
      if (parsed.parseError) {
        throw new Error(parsed.parseError);
      }
      if (parsed.text.length > 0) {
        input.onDelta?.(parsed.text);
      }
      for (const call of parsed.toolCalls) {
        input.onToolCallDelta?.({
          index: call.index,
          id: call.id,
          name: call.name,
          argumentsText: call.argumentsText,
        });
      }
      return {
        text: parsed.text,
        toolCalls: parsed.toolCalls,
        finishReason: parsed.finishReason,
        usage: parsed.usage,
      };
    }
    const bodyStream = response.body;
    if (!bodyStream) {
      throw new Error('OpenCode Go returned an empty streaming response body.');
    }
    const reader = bodyStream.getReader();
    const decoder = new TextDecoder();
    const textParts: string[] = [];
    const state = createToolCallState();
    let finishReason = '';
    let usage: UsageInfo | null = null;
    let buffer = '';
    let complete = false;
    const handleLine = (line: string): void => {
      const event = parseSseLine(line);
      if (!event) {
        return;
      }
      if (event.done) {
        complete = true;
        return;
      }
      if (event.deltaText) {
        textParts.push(event.deltaText);
        input.onDelta?.(event.deltaText);
      }
      if (event.finishReason) {
        finishReason = event.finishReason;
      }
      if (event.usage) {
        usage = event.usage;
      }
      const deltas = event.toolCallDeltas;
      if (deltas && deltas.length > 0) {
        for (const delta of deltas) {
          input.onToolCallDelta?.(delta);
        }
        mergeToolCallDeltas(state, deltas);
      }
    };
    try {
      while (!complete) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        const chunkText = decoder.decode(value, { stream: true });
        const split = splitSseLines(buffer, chunkText);
        buffer = split.rest;
        for (const line of split.lines) {
          handleLine(line);
          if (complete) {
            break;
          }
        }
      }
      if (!complete && buffer.trim().length > 0) {
        handleLine(buffer);
      }
    } finally {
      try {
        await reader.cancel();
      } catch {
        // the stream is already closed
      }
    }
    return {
      text: textParts.join(''),
      toolCalls: finalizeToolCalls(state),
      finishReason: finishReason || (state.calls.length > 0 ? 'tool_calls' : 'stop'),
      usage,
    };
  }

  private async request(
    url: string,
    init: RequestInit,
    signal: AbortSignal | undefined,
    includeClientHeader: boolean
  ): Promise<Response> {
    if (this.disposed) {
      throw new Error('OpenCode Go client is disposed.');
    }
    if (this.options.apiKey.trim().length === 0) {
      throw new Error(
        `OpenCode Go key not found in ~/${AUTH_FILE_RELATIVE}. Run "opencode auth login" or set tradeAssistant.chat.provider to copilot.`
      );
    }
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.options.apiKey}`,
      'content-type': 'application/json',
      'user-agent': this.options.userAgent ?? DEFAULT_USER_AGENT,
      'x-opencode-session': this.options.sessionId,
    };
    if (includeClientHeader || this.options.sessionId.length === 0) {
      headers['x-opencode-client'] = 'trade-assistant';
    }
    let lastError: Error | undefined;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      let response: Response;
      try {
        response = await this.fetchImpl(url, { ...init, headers, signal });
      } catch (error) {
        if (signal?.aborted) {
          throw error;
        }
        throw new Error(`Cannot reach OpenCode Go: ${messageOf(error)}`);
      }
      if (response.ok) {
        return response;
      }
      const bodyText = await response.text().catch(() => '');
      const info = describeHttpError(response.status, bodyText);
      if (!info.retryable || attempt === 1) {
        throw new Error(info.message);
      }
      lastError = new Error(info.message);
      await delay(750);
    }
    throw lastError ?? new Error('OpenCode Go request failed.');
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
