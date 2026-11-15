import {
  PROVIDER_MODELS,
  type AiConfig,
  type ProviderType,
} from '../types';
import type { StreamingLlmClient } from './client';

const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta';
const OPENAI_BASES: Partial<Record<ProviderType, string>> = {
  groq: 'https://api.groq.com/openai/v1',
  ollama: 'http://localhost:11434/v1',
  openrouter: 'https://openrouter.ai/api/v1',
  puter: 'https://api.puter.com/puterai/openai/v1',
  opencode: 'https://opencode.ai/zen/go/v1',
  llamacpp: 'http://localhost:8080/v1',
};

export interface AiProviderOptions {
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

function normalizeModel(provider: ProviderType, model: string): string {
  const trimmed = model.trim();
  if (provider === 'gemini') return trimmed.replace(/^models\//, '');
  if (provider === 'opencode') {
    return trimmed.startsWith('opencode-go/') ? trimmed : `opencode-go/${trimmed}`;
  }
  return trimmed;
}

function joinUrl(base: string, suffix: string): string {
  return `${base.replace(/\/+$/, '')}/${suffix.replace(/^\/+/, '')}`;
}

function extractErrorMessage(body: string): string {
  try {
    const parsed = JSON.parse(body) as Record<string, unknown>;
    const error = parsed.error;
    if (typeof error === 'string') return error;
    if (error && typeof error === 'object') {
      const message = (error as Record<string, unknown>).message;
      if (typeof message === 'string') return message;
    }
    const message = parsed.message;
    if (typeof message === 'string') return message;
  } catch {
    // use raw body
  }
  return body.slice(0, 500);
}

export class AiProvider implements StreamingLlmClient {
  readonly provider: ProviderType;
  readonly model: string;
  private readonly apiKey: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(config: AiConfig, apiKey: string, options: AiProviderOptions = {}) {
    this.provider = config.provider;
    this.model = normalizeModel(config.provider, config.model || PROVIDER_MODELS[config.provider][0] || '');
    this.apiKey = apiKey;
    this.timeoutMs = options.timeoutMs ?? 300_000;
    this.fetchImpl = options.fetchImpl ?? fetch;
    if (!this.model) throw new Error(`Nessun modello configurato per ${config.provider}.`);
    if (requiresApiKey(config.provider) && !this.apiKey) {
      throw new Error(
        `API key mancante per ${config.provider}. Salvala nella sezione AI Configuration (SecretStorage) o in .env (${envKeyFor(config.provider)}).`,
      );
    }
  }

  async categorize(prompt: string): Promise<string> {
    return this.generate(prompt, true);
  }

  async generate(prompt: string, jsonMode = false): Promise<string> {
    if (this.provider === 'gemini') return this.geminiGenerate(prompt, jsonMode);
    return this.openAiGenerate(prompt, jsonMode);
  }

  async *streamChat(system: string, user: string): AsyncGenerator<string> {
    if (this.provider === 'gemini') {
      yield* this.geminiStream(system, user);
      return;
    }
    yield* this.openAiStream(system, user);
  }

  private async request(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await this.fetchImpl(url, { ...init, signal: controller.signal });
    } catch (error) {
      const message = (error as Error).name === 'AbortError'
        ? `Timeout dopo ${Math.round(this.timeoutMs / 1000)}s`
        : (error as Error).message;
      throw new Error(`${this.provider}: ${message}`);
    } finally {
      clearTimeout(timer);
    }
  }

  private async geminiGenerate(prompt: string, jsonMode: boolean): Promise<string> {
    const url = `${GEMINI_BASE}/models/${encodeURIComponent(this.model)}:generateContent?key=${encodeURIComponent(this.apiKey)}`;
    const body: Record<string, unknown> = {
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.2,
        ...(jsonMode ? { responseMimeType: 'application/json' } : {}),
      },
    };
    const response = await this.request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`gemini HTTP ${response.status}: ${extractErrorMessage(text)}`);
    }
    const parsed = JSON.parse(text) as {
      candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
    };
    const parts = parsed.candidates?.[0]?.content?.parts ?? [];
    return parts.map((part) => part.text ?? '').join('');
  }

  private async *geminiStream(system: string, user: string): AsyncGenerator<string> {
    const url = `${GEMINI_BASE}/models/${encodeURIComponent(this.model)}:streamGenerateContent?alt=sse&key=${encodeURIComponent(this.apiKey)}`;
    const body = {
      systemInstruction: { parts: [{ text: system }] },
      contents: [{ role: 'user', parts: [{ text: user }] }],
      generationConfig: { temperature: 0.3 },
    };
    const response = await this.request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`gemini HTTP ${response.status}: ${extractErrorMessage(text)}`);
    }
    yield* parseSseStream(response, (data) => {
      const parsed = data as {
        candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
      };
      const parts = parsed.candidates?.[0]?.content?.parts ?? [];
      return parts.map((part) => part.text ?? '').join('');
    });
  }

  private openAiBase(): string {
    const base = OPENAI_BASES[this.provider];
    if (!base) throw new Error(`Provider OpenAI-compatibile non supportato: ${this.provider}`);
    return base;
  }

  private openAiHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    if (this.provider === 'openrouter') {
      headers['HTTP-Referer'] = 'https://github.com/local/budget-app-manager';
      headers['X-Title'] = 'Budget App Manager';
    }
    return headers;
  }

  private async openAiGenerate(prompt: string, jsonMode: boolean): Promise<string> {
    const url = joinUrl(this.openAiBase(), 'chat/completions');
    const body: Record<string, unknown> = {
      model: this.model,
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.2,
      stream: false,
    };
    if (jsonMode && this.supportsJsonMode()) body.response_format = { type: 'json_object' };
    let response = await this.request(url, {
      method: 'POST',
      headers: this.openAiHeaders(),
      body: JSON.stringify(body),
    });
    if (response.status === 400 && body.response_format) {
      delete body.response_format;
      response = await this.request(url, {
        method: 'POST',
        headers: this.openAiHeaders(),
        body: JSON.stringify(body),
      });
    }
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${this.provider} HTTP ${response.status}: ${extractErrorMessage(text)}`);
    }
    const parsed = JSON.parse(text) as {
      choices?: Array<{ message?: { content?: string | Array<{ text?: string }> } }>;
    };
    const content = parsed.choices?.[0]?.message?.content;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) return content.map((part) => part.text ?? '').join('');
    return '';
  }

  private supportsJsonMode(): boolean {
    return this.provider === 'groq';
  }

  private async *openAiStream(system: string, user: string): AsyncGenerator<string> {
    const url = joinUrl(this.openAiBase(), 'chat/completions');
    const response = await this.request(url, {
      method: 'POST',
      headers: this.openAiHeaders(),
      body: JSON.stringify({
        model: this.model,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.3,
        stream: true,
      }),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${this.provider} HTTP ${response.status}: ${extractErrorMessage(text)}`);
    }
    yield* parseSseStream(response, (data) => {
      const parsed = data as {
        choices?: Array<{ delta?: { content?: string } }>;
      };
      return parsed.choices?.[0]?.delta?.content ?? '';
    });
  }
}

function requiresApiKey(provider: ProviderType): boolean {
  return provider === 'gemini' || provider === 'groq' || provider === 'openrouter' || provider === 'puter';
}

export function envKeyFor(provider: ProviderType): string {
  switch (provider) {
    case 'gemini':
      return 'GOOGLE_API_KEY';
    case 'groq':
      return 'GROQ_API_KEY';
    case 'ollama':
      return 'OLLAMA_API_KEY';
    case 'openrouter':
      return 'OPENROUTER_API_KEY';
    case 'puter':
      return 'PUTER_API_KEY';
    case 'opencode':
      return 'OPENCODE_GO_API_KEY';
    case 'llamacpp':
      return 'LLAMACPP_API_KEY';
    default:
      return '';
  }
}

async function* parseSseStream(
  response: Response,
  extract: (data: unknown) => string,
): AsyncGenerator<string> {
  const body = response.body;
  if (!body) return;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const payload = trimmed.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        try {
          const text = extract(JSON.parse(payload) as unknown);
          if (text) yield text;
        } catch {
          // ignore malformed SSE frames
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function mergeModels(primary: string[], secondary: string[]): string[] {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const model of [...primary, ...secondary]) {
    const name = model.trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    merged.push(name);
  }
  return merged;
}

async function fetchJsonWithTimeout(
  url: string,
  headers: Record<string, string>,
  fetchImpl: typeof fetch,
  timeoutMs = 8000,
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, { headers, signal: controller.signal });
    if (!response.ok) return null;
    return (await response.json()) as unknown;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function listProviderModels(
  provider: ProviderType,
  apiKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<string[]> {
  const fallback = PROVIDER_MODELS[provider];
  try {
    if (provider === 'llamacpp') {
      const data = (await fetchJsonWithTimeout(
        'http://localhost:8080/v1/models',
        {},
        fetchImpl,
      )) as { data?: Array<{ id?: string }> } | null;
      const ids = (data?.data ?? []).map((model) => model.id ?? '').filter(Boolean);
      return ids.length > 0 ? ids : fallback;
    }
    if (provider === 'ollama') {
      const data = (await fetchJsonWithTimeout(
        'http://localhost:11434/api/tags',
        {},
        fetchImpl,
      )) as { models?: Array<{ name?: string }> } | null;
      const names = (data?.models ?? []).map((model) => model.name ?? '').filter(Boolean);
      return names.length > 0 ? names : fallback;
    }
    if (provider === 'opencode') {
      const data = (await fetchJsonWithTimeout(
        joinUrl(OPENAI_BASES.opencode ?? '', 'models'),
        apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
        fetchImpl,
      )) as { data?: Array<{ id?: string }> } | null;
      const ids = (data?.data ?? [])
        .map((model) => (model.id ?? '').replace(/^opencode-go\//, ''))
        .filter(Boolean);
      return mergeModels(ids, fallback);
    }
    if (provider === 'openrouter') {
      const data = (await fetchJsonWithTimeout(
        'https://openrouter.ai/api/v1/models',
        apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
        fetchImpl,
      )) as { data?: Array<{ id?: string }> } | null;
      const ids = (data?.data ?? []).map((model) => model.id ?? '').filter(Boolean);
      return ids.length > 0 ? ids.slice(0, 400) : fallback;
    }
    if (provider === 'groq' && apiKey) {
      const data = (await fetchJsonWithTimeout(
        'https://api.groq.com/openai/v1/models',
        { Authorization: `Bearer ${apiKey}` },
        fetchImpl,
      )) as { data?: Array<{ id?: string }> } | null;
      const ids = (data?.data ?? []).map((model) => model.id ?? '').filter(Boolean);
      return ids.length > 0 ? ids : fallback;
    }
    if (provider === 'gemini' && apiKey) {
      const data = (await fetchJsonWithTimeout(
        `${GEMINI_BASE}/models?key=${encodeURIComponent(apiKey)}`,
        {},
        fetchImpl,
      )) as { models?: Array<{ name?: string; supportedGenerationMethods?: string[] }> } | null;
      const ids = (data?.models ?? [])
        .filter((model) => (model.supportedGenerationMethods ?? []).includes('generateContent'))
        .map((model) => (model.name ?? '').replace(/^models\//, ''))
        .filter(Boolean);
      return ids.length > 0 ? ids : fallback;
    }
  } catch {
    return fallback;
  }
  return fallback;
}
