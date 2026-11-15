import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';

export const MCP_PROTOCOL_VERSION = '2025-06-18';
export const MCP_CLIENT_NAME = 'trade-assistant';
export const MCP_CLIENT_VERSION = '0.2.0';
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

export const UNSAFE_TOOL_PATTERN = /place|order|trade_execute|buy|sell|close_position|transfer/i;

export interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface ChatToolSpec {
  name: string;
  description: string;
  inputSchema: object;
}

export interface RpcErrorShape {
  code: number;
  message: string;
  data?: unknown;
}

export interface RpcMessage {
  jsonrpc?: string;
  id?: number | string | null;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: RpcErrorShape;
}

export interface ToolCallOutcome {
  isError: boolean;
  text: string;
}

export interface McpClientOptions {
  command: string;
  args?: string[];
  env?: Record<string, string>;
  cwd?: string;
  requestTimeoutMs?: number;
  maxLogLines?: number;
  onLog?: (line: string) => void;
  onExit?: (code: number | null) => void;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export function isUnsafeToolName(name: string): boolean {
  return UNSAFE_TOOL_PATTERN.test(name);
}

export function parseRpcLines(buffer: string): { messages: RpcMessage[]; rest: string } {
  const messages: RpcMessage[] = [];
  let cursor = 0;
  for (;;) {
    const newline = buffer.indexOf('\n', cursor);
    if (newline === -1) {
      break;
    }
    const line = buffer.slice(cursor, newline).trim();
    cursor = newline + 1;
    if (line.length === 0) {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      continue;
    }
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      messages.push(parsed as RpcMessage);
    }
  }
  return { messages, rest: buffer.slice(cursor) };
}

export function normalizeInputSchema(schema: unknown): Record<string, unknown> {
  const source = schema && typeof schema === 'object' && !Array.isArray(schema) ? { ...(schema as Record<string, unknown>) } : {};
  delete source.$schema;
  if (source.type !== 'object') {
    source.type = 'object';
  }
  if (!source.properties || typeof source.properties !== 'object' || Array.isArray(source.properties)) {
    source.properties = {};
  }
  return source;
}

export function parseToolList(result: unknown): McpTool[] {
  const source = result && typeof result === 'object' ? (result as { tools?: unknown }).tools : undefined;
  if (!Array.isArray(source)) {
    return [];
  }
  const tools: McpTool[] = [];
  const seen = new Set<string>();
  for (const entry of source) {
    if (!entry || typeof entry !== 'object') {
      continue;
    }
    const candidate = entry as { name?: unknown; description?: unknown; inputSchema?: unknown };
    if (typeof candidate.name !== 'string' || candidate.name.trim().length === 0 || seen.has(candidate.name)) {
      continue;
    }
    seen.add(candidate.name);
    tools.push({
      name: candidate.name,
      description: typeof candidate.description === 'string' ? candidate.description : '',
      inputSchema: normalizeInputSchema(candidate.inputSchema),
    });
  }
  return tools;
}

export function toChatTools(tools: McpTool[]): ChatToolSpec[] {
  return tools.map((tool) => ({
    name: tool.name,
    description: tool.description.trim() || tool.name,
    inputSchema: normalizeInputSchema(tool.inputSchema),
  }));
}

export function outcomeText(result: unknown): string {
  const content = result && typeof result === 'object' ? (result as { content?: unknown }).content : undefined;
  if (!Array.isArray(content)) {
    return typeof result === 'string' ? result : JSON.stringify(result ?? null);
  }
  const pieces: string[] = [];
  for (const part of content) {
    if (typeof part === 'string') {
      pieces.push(part);
      continue;
    }
    if (!part || typeof part !== 'object') {
      continue;
    }
    const block = part as { type?: unknown; text?: unknown };
    if (block.type === 'text' && typeof block.text === 'string') {
      pieces.push(block.text);
      continue;
    }
    pieces.push(JSON.stringify(part));
  }
  return pieces.join('\n');
}

export class McpClient {
  private child: ChildProcessWithoutNullStreams | undefined;
  private buffer = '';
  private nextId = 1;
  private readonly pending = new Map<number, PendingRequest>();
  private readonly logLines: string[] = [];
  private readonly options: McpClientOptions;
  private readonly timeoutMs: number;
  private readonly maxLogLines: number;
  private toolCache: McpTool[] = [];
  private startedAtMs = 0;
  private disposed = false;
  private stderrCarry = '';

  constructor(options: McpClientOptions) {
    this.options = options;
    this.timeoutMs = options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    this.maxLogLines = options.maxLogLines ?? 200;
  }

  get isRunning(): boolean {
    return this.child !== undefined && this.child.exitCode === null;
  }

  get tools(): McpTool[] {
    return this.toolCache;
  }

  get processStartedAt(): number {
    return this.startedAtMs;
  }

  get stderrLog(): string[] {
    return [...this.logLines];
  }

  async start(): Promise<void> {
    if (this.disposed) {
      throw new Error('MCP client is disposed.');
    }
    if (this.isRunning) {
      return;
    }
    this.spawnChild();
    await this.request(
      'initialize',
      {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: MCP_CLIENT_NAME, version: MCP_CLIENT_VERSION },
      },
      this.timeoutMs
    );
    this.notify('notifications/initialized', {});
    this.startedAtMs = Date.now();
    await this.refreshTools();
  }

  async refreshTools(timeoutMs = this.timeoutMs): Promise<McpTool[]> {
    const result = await this.request('tools/list', {}, timeoutMs);
    this.toolCache = parseToolList(result);
    return this.toolCache;
  }

  async callTool(name: string, args: Record<string, unknown>, timeoutMs = this.timeoutMs): Promise<ToolCallOutcome> {
    if (!this.isRunning) {
      throw new Error('MCP server is not running.');
    }
    const result = await this.request('tools/call', { name, arguments: args }, timeoutMs);
    const isError = Boolean(result && typeof result === 'object' && (result as { isError?: unknown }).isError === true);
    return { isError, text: outcomeText(result) };
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    this.rejectPending(new Error('MCP client disposed.'));
    this.killChild();
  }

  private spawnChild(): void {
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (typeof value === 'string') {
        env[key] = value;
      }
    }
    Object.assign(env, this.options.env ?? {});
    const child = spawn(this.options.command, this.options.args ?? [], {
      cwd: this.options.cwd,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      detached: process.platform !== 'win32',
    });
    this.child = child;

    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk;
      const { messages, rest } = parseRpcLines(this.buffer);
      this.buffer = rest;
      for (const message of messages) {
        this.dispatch(message);
      }
    });

    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk: string) => {
      this.stderrCarry += chunk;
      const lines = this.stderrCarry.split('\n');
      this.stderrCarry = lines.pop() ?? '';
      for (const line of lines) {
        this.pushLog(line);
      }
    });

    child.on('error', (error) => {
      this.pushLog(`spawn error: ${error.message}`);
      this.rejectPending(error instanceof Error ? error : new Error(String(error)));
    });

    child.on('exit', (code) => {
      if (this.stderrCarry.trim().length > 0) {
        this.pushLog(this.stderrCarry.trim());
        this.stderrCarry = '';
      }
      this.child = undefined;
      this.rejectPending(new Error(`MCP server exited with code ${code ?? 'null'}.`));
      this.options.onExit?.(code);
    });

    child.stdin.on('error', (error) => {
      this.pushLog(`stdin error: ${error.message}`);
    });
  }

  private dispatch(message: RpcMessage): void {
    if (message.id === undefined || message.id === null) {
      return;
    }
    const id = typeof message.id === 'number' ? message.id : Number(message.id);
    const pending = this.pending.get(id);
    if (!pending) {
      return;
    }
    this.pending.delete(id);
    clearTimeout(pending.timer);
    if (message.error) {
      pending.reject(new Error(`MCP error ${message.error.code}: ${message.error.message}`));
      return;
    }
    pending.resolve(message.result);
  }

  private notify(method: string, params: unknown): void {
    const child = this.child;
    if (!child) {
      return;
    }
    try {
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`);
    } catch (error) {
      this.pushLog(`notification failed: ${messageOf(error)}`);
    }
  }

  private request(method: string, params: unknown, timeoutMs: number): Promise<unknown> {
    const child = this.child;
    if (!child || child.stdin.destroyed) {
      return Promise.reject(new Error('MCP server is not running.'));
    }
    const id = this.nextId;
    this.nextId += 1;
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`MCP request timed out after ${timeoutMs} ms: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private rejectPending(error: Error): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      this.pending.delete(id);
    }
  }

  private killChild(): void {
    const child = this.child;
    this.child = undefined;
    if (!child || child.exitCode !== null || child.signalCode !== null) {
      return;
    }
    if (process.platform !== 'win32' && typeof child.pid === 'number') {
      try {
        process.kill(-child.pid, 'SIGKILL');
        return;
      } catch {
        // no process group left
      }
    }
    try {
      child.kill('SIGKILL');
    } catch {
      // already exited
    }
  }

  private pushLog(line: string): void {
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      return;
    }
    this.logLines.push(trimmed);
    if (this.logLines.length > this.maxLogLines) {
      this.logLines.splice(0, this.logLines.length - this.maxLogLines);
    }
    this.options.onLog?.(trimmed);
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
