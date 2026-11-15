export const DEFAULT_BASE_URL = 'https://opencode.ai/zen/go/v1';
export const DEFAULT_USER_AGENT = 'trade-assistant/0.3.0';
export const AUTH_PROVIDER = 'opencode-go';
export const CHAT_COMPLETIONS_PATH = '/chat/completions';
export const MODELS_PATH = '/models';

export interface ToolSpec {
  name: string;
  description: string;
  inputSchema: unknown;
}

export interface OpenAiToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

export interface OpenAiMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_calls?: OpenAiToolCall[];
  tool_call_id?: string;
  name?: string;
}

export interface UsageInfo {
  promptTokens: number;
  completionTokens: number;
  cost: number | null;
}

export interface ChatRequestBody {
  model: string;
  messages: OpenAiMessage[];
  tools: unknown[];
  stream: boolean;
  temperature?: number;
}

export interface ChatRequestInput {
  baseUrl?: string;
  apiKey: string;
  model: string;
  sessionId: string;
  messages: OpenAiMessage[];
  tools?: ToolSpec[];
  stream: boolean;
  temperature?: number;
  userAgent?: string;
}

export interface ChatRequest {
  url: string;
  headers: Record<string, string>;
  body: ChatRequestBody;
}

export interface ToolCallDelta {
  index: number;
  id?: string;
  name?: string;
  argumentsText?: string;
}

export interface ParsedToolCall {
  index: number;
  id: string;
  name: string;
  argumentsText: string;
  argumentsObject: Record<string, unknown> | null;
  parseError: boolean;
}

export interface SseEvent {
  done?: boolean;
  event?: string;
  deltaText?: string;
  toolCallDelta?: ToolCallDelta;
  toolCallDeltas?: ToolCallDelta[];
  finishReason?: string | null;
  usage?: UsageInfo | null;
}

export interface ParsedCompletion {
  text: string;
  toolCalls: ParsedToolCall[];
  finishReason: string;
  usage: UsageInfo | null;
  parseError?: string;
}

export interface ToolCallState {
  calls: ParsedToolCall[];
}

const PROVIDER_PREFIXES = ['opencode-go/', 'opencode_go/', 'opencodego/', 'opencode/'];

export function parseAuthKey(authJsonText: string): string | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(authJsonText);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null;
  }
  const entry = (parsed as Record<string, unknown>)[AUTH_PROVIDER];
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return null;
  }
  const key = (entry as Record<string, unknown>).key;
  if (typeof key !== 'string') {
    return null;
  }
  const trimmed = key.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function normalizeModelId(raw: string): string {
  let value = (raw ?? '').trim();
  let stripped = true;
  while (stripped) {
    stripped = false;
    for (const prefix of PROVIDER_PREFIXES) {
      if (value.toLowerCase().startsWith(prefix)) {
        value = value.slice(prefix.length).trim();
        stripped = true;
        break;
      }
    }
  }
  return value;
}

export function normalizeParameters(schema: unknown): Record<string, unknown> {
  const source =
    schema && typeof schema === 'object' && !Array.isArray(schema)
      ? { ...(schema as Record<string, unknown>) }
      : {};
  delete source.$schema;
  if (source.type !== 'object') {
    source.type = 'object';
  }
  if (!source.properties || typeof source.properties !== 'object' || Array.isArray(source.properties)) {
    source.properties = {};
  }
  return source;
}

export function toOpenAiTools(specs: ToolSpec[]): unknown[] {
  const tools: unknown[] = [];
  const seen = new Set<string>();
  for (const spec of specs) {
    const name = spec.name.trim();
    if (name.length === 0 || seen.has(name)) {
      continue;
    }
    seen.add(name);
    tools.push({
      type: 'function',
      function: {
        name,
        description: spec.description.trim() || name,
        parameters: normalizeParameters(spec.inputSchema),
      },
    });
  }
  return tools;
}

export function buildChatRequest(input: ChatRequestInput): ChatRequest {
  const baseUrl = (input.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const headers: Record<string, string> = {
    Authorization: `Bearer ${input.apiKey}`,
    'content-type': 'application/json',
    'user-agent': input.userAgent ?? DEFAULT_USER_AGENT,
    'x-opencode-session': input.sessionId,
  };
  const body: ChatRequestBody = {
    model: normalizeModelId(input.model),
    messages: input.messages,
    tools: toOpenAiTools(input.tools ?? []),
    stream: input.stream,
  };
  if (typeof input.temperature === 'number' && Number.isFinite(input.temperature)) {
    body.temperature = input.temperature;
  }
  return { url: `${baseUrl}${CHAT_COMPLETIONS_PATH}`, headers, body };
}

export function splitSseLines(buffer: string, chunk: string): { lines: string[]; rest: string } {
  const combined = buffer + chunk;
  const lines: string[] = [];
  let cursor = 0;
  for (;;) {
    const newline = combined.indexOf('\n', cursor);
    if (newline === -1) {
      break;
    }
    lines.push(combined.slice(cursor, newline));
    cursor = newline + 1;
  }
  return { lines, rest: combined.slice(cursor) };
}

export function parseSseLine(line: string): SseEvent | null {
  const trimmed = line.replace(/\r$/, '').trim();
  if (trimmed.length === 0 || trimmed.startsWith(':')) {
    return null;
  }
  const colon = trimmed.indexOf(':');
  if (colon === -1) {
    return null;
  }
  const field = trimmed.slice(0, colon).trim().toLowerCase();
  const value = trimmed.slice(colon + 1).trim();
  if (field === 'event') {
    return value.length > 0 ? { event: value } : null;
  }
  if (field !== 'data') {
    return null;
  }
  if (value === '[DONE]') {
    return { done: true };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') {
    return null;
  }
  const root = parsed as Record<string, unknown>;
  const choices = Array.isArray(root.choices) ? root.choices : [];
  const choice = choices.length > 0 && choices[0] && typeof choices[0] === 'object'
    ? (choices[0] as Record<string, unknown>)
    : {};
  const delta =
    choice.delta && typeof choice.delta === 'object'
      ? (choice.delta as Record<string, unknown>)
      : choice.message && typeof choice.message === 'object'
        ? (choice.message as Record<string, unknown>)
        : {};
  const content = typeof delta.content === 'string' && delta.content.length > 0 ? delta.content : undefined;
  const rawCalls = Array.isArray(delta.tool_calls) ? delta.tool_calls : [];
  const toolCallDeltas: ToolCallDelta[] = [];
  for (const entry of rawCalls) {
    const deltaEntry = readToolCall(entry);
    if (deltaEntry) {
      toolCallDeltas.push(deltaEntry);
    }
  }
  const finishReason = typeof choice.finish_reason === 'string' ? choice.finish_reason : null;
  const usage = readOpencodeUsage(root);
  if (
    content === undefined &&
    toolCallDeltas.length === 0 &&
    finishReason === null &&
    usage === null
  ) {
    return null;
  }
  const event: SseEvent = {};
  if (content !== undefined) {
    event.deltaText = content;
  }
  if (toolCallDeltas.length > 0) {
    event.toolCallDeltas = toolCallDeltas;
    event.toolCallDelta = toolCallDeltas[0];
  }
  event.finishReason = finishReason;
  if (usage !== null) {
    event.usage = usage;
  }
  return event;
}

export function createToolCallState(): ToolCallState {
  return { calls: [] };
}

export function mergeToolCallDeltas(state: ToolCallState, deltas: ToolCallDelta[]): ToolCallState {
  for (const delta of deltas) {
    const index = Number.isFinite(delta.index) ? Math.max(0, Math.floor(delta.index)) : state.calls.length;
    let slot = state.calls.find((call) => call.index === index);
    if (!slot) {
      slot = { index, id: '', name: '', argumentsText: '', argumentsObject: null, parseError: false };
      state.calls.push(slot);
    }
    if (typeof delta.id === 'string' && delta.id.length > 0 && slot.id.length === 0) {
      slot.id = delta.id;
    }
    if (typeof delta.name === 'string' && delta.name.length > 0) {
      if (slot.name.length === 0) {
        slot.name = delta.name;
      } else if (!slot.name.startsWith(delta.name) && !delta.name.startsWith(slot.name)) {
        slot.name += delta.name;
      }
    }
    if (typeof delta.argumentsText === 'string' && delta.argumentsText.length > 0) {
      slot.argumentsText += delta.argumentsText;
    }
    const parsed = parseArguments(slot.argumentsText);
    slot.argumentsObject = parsed.value;
    slot.parseError = parsed.error;
  }
  state.calls.sort((left, right) => left.index - right.index);
  return state;
}

export function finalizeToolCalls(state: ToolCallState): ParsedToolCall[] {
  const finalized: ParsedToolCall[] = [];
  for (const call of state.calls) {
    if (call.name.length === 0) {
      continue;
    }
    const id = call.id.length > 0 ? call.id : `call_${call.index}`;
    const parsed = parseArguments(call.argumentsText);
    finalized.push({
      index: call.index,
      id,
      name: call.name,
      argumentsText: call.argumentsText,
      argumentsObject: parsed.value,
      parseError: parsed.error,
    });
  }
  return finalized;
}

export function parseCompletionJson(text: string): ParsedCompletion {
  const empty: ParsedCompletion = { text: '', toolCalls: [], finishReason: '', usage: null };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    return { ...empty, parseError: `Invalid JSON response: ${messageOf(error)}` };
  }
  if (!parsed || typeof parsed !== 'object') {
    return { ...empty, parseError: 'Invalid JSON response: not an object.' };
  }
  const root = parsed as Record<string, unknown>;
  const choices = Array.isArray(root.choices) ? root.choices : [];
  const choice =
    choices.length > 0 && choices[0] && typeof choices[0] === 'object'
      ? (choices[0] as Record<string, unknown>)
      : {};
  const message =
    choice.message && typeof choice.message === 'object' ? (choice.message as Record<string, unknown>) : {};
  const content = typeof message.content === 'string' ? message.content : '';
  const rawCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
  const state = createToolCallState();
  const deltas: ToolCallDelta[] = [];
  for (let position = 0; position < rawCalls.length; position += 1) {
    const call = readToolCall(rawCalls[position], position);
    if (call) {
      deltas.push(call);
    }
  }
  mergeToolCallDeltas(state, deltas);
  const finishReason = typeof choice.finish_reason === 'string' ? choice.finish_reason : '';
  return {
    text: content,
    toolCalls: finalizeToolCalls(state),
    finishReason,
    usage: readOpencodeUsage(root),
  };
}

export function readOpencodeUsage(json: unknown): UsageInfo | null {
  if (!json || typeof json !== 'object' || Array.isArray(json)) {
    return null;
  }
  const record = json as Record<string, unknown>;
  const nested = record.usage;
  const source =
    nested && typeof nested === 'object' && !Array.isArray(nested)
      ? (nested as Record<string, unknown>)
      : record;
  const prompt = readNumber(source.prompt_tokens);
  const completion = readNumber(source.completion_tokens);
  const cost = readNumber(source.cost);
  if (prompt === null && completion === null && cost === null) {
    return null;
  }
  return { promptTokens: prompt ?? 0, completionTokens: completion ?? 0, cost };
}

function readToolCall(entry: unknown, fallbackIndex?: number): ToolCallDelta | null {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
    return null;
  }
  const record = entry as Record<string, unknown>;
  const index = readNumber(record.index) ?? (fallbackIndex === undefined ? null : fallbackIndex);
  if (index === null) {
    return null;
  }
  const fn =
    record.function && typeof record.function === 'object' && !Array.isArray(record.function)
      ? (record.function as Record<string, unknown>)
      : {};
  const delta: ToolCallDelta = { index: Math.floor(index) };
  if (typeof record.id === 'string' && record.id.length > 0) {
    delta.id = record.id;
  }
  if (typeof fn.name === 'string' && fn.name.length > 0) {
    delta.name = fn.name;
  }
  if (typeof fn.arguments === 'string' && fn.arguments.length > 0) {
    delta.argumentsText = fn.arguments;
  }
  return delta;
}

function parseArguments(text: string): { value: Record<string, unknown> | null; error: boolean } {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return { value: {}, error: false };
  }
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return { value: parsed as Record<string, unknown>, error: false };
    }
    return { value: null, error: true };
  } catch {
    return { value: null, error: true };
  }
}

function readNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
