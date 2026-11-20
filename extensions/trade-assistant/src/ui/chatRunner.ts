import * as os from 'node:os';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { McpClient, isUnsafeToolName, toChatTools, type ChatToolSpec, type ToolCallOutcome } from '../core/mcpClient';
import type { SkillInfo } from '../core/capabilities';
import { FILE_TOOL_NAMES, FileToolService } from '../core/fileTools';
import {
  normalizeModelId,
  supportsChatCompletions,
  type OpenAiMessage,
  type OpenAiToolCall,
  type UsageInfo,
} from '../core/opencodeGo';
import { DEFAULT_TIMEOUT_MS, OpencodeGoClient, defaultAuthPath, readAuthKeyFromFile } from '../core/opencodeGoClient';
import { isServerStale } from '../core/sync';
import type { TranscriptFs, TranscriptRecord } from '../core/transcript';
import { appendRecord, createRecord, readSession, sessionFilePath, summaryOf } from '../core/transcript';

export const SKILL_LOOKUP_TOOL = 'skill_lookup';

const SKILL_LOOKUP_SPEC: ChatToolSpec = {
  name: SKILL_LOOKUP_TOOL,
  description: 'Search the local trading skill catalogue. Returns skill names, one-line descriptions and SKILL.md paths.',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Substring or topic, for example "options", "risk" or "volume".' },
    },
    required: ['query'],
  },
};

import { compressToolOutput } from '../core/toolOutput';

const FINAL_ANSWER_NUDGE =
  'You have reached the tool iteration limit for this turn. Do not call more tools. Answer the user now, in concise markdown, using only the tool results already above. If a value is missing, state that it is missing.';
const HISTORY_TOKEN_BUDGET = 0.65;
const DEFAULT_OPENCODE_MODEL = 'deepseek-v4.1-flash';

export const MISSING_KEY_MESSAGE =
  'OpenCode Go key not found in ~/.local/share/opencode/auth.json. Run "opencode auth login" or set tradeAssistant.chat.provider to copilot.';

export type ChatProvider = 'opencode-go' | 'copilot';

export interface ProviderStatus {
  configured: string;
  provider: ChatProvider;
  model: string;
  modelSource: 'setting' | 'agent' | 'default';
  authPath: string;
  keyPresent: boolean;
  roots: string[];
}

export interface McpServiceConfig {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

export class McpService implements vscode.Disposable {
  private client: McpClient | undefined;
  private inFlight: Promise<ChatToolSpec[]> | undefined;
  private toolSpecs: ChatToolSpec[] = [];
  private stale = false;
  private lastSourceMtime = 0;

  constructor(
    private readonly resolveConfig: () => McpServiceConfig | null,
    private readonly log: (line: string) => void,
    private readonly sourceMtimes: () => number[] = () => []
  ) {}

  get tools(): ChatToolSpec[] {
    return this.toolSpecs;
  }

  get running(): boolean {
    return this.client?.isRunning === true;
  }

  markStale(reason: string): void {
    if (!this.client) {
      return;
    }
    this.stale = true;
    this.log(`MCP client marked stale (${reason})`);
  }

  async ensure(): Promise<ChatToolSpec[]> {
    if (this.inFlight) {
      return this.inFlight;
    }
    if (this.client?.isRunning && !this.stale) {
      const changed = this.freshSourceMtimes();
      if (changed.length > 0 && isServerStale(this.client.processStartedAt, changed)) {
        this.stale = true;
        this.log('python sources changed since the MCP start: restarting the server');
      } else {
        return this.toolSpecs;
      }
    }
    this.inFlight = this.connect();
    try {
      return await this.inFlight;
    } finally {
      this.inFlight = undefined;
    }
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<ToolCallOutcome> {
    if (!this.client?.isRunning) {
      await this.ensure();
    }
    const client = this.client;
    if (!client?.isRunning) {
      throw new Error('Trading MCP server is not running.');
    }
    return client.callTool(name, args);
  }

  async dispose(): Promise<void> {
    const client = this.client;
    this.client = undefined;
    this.toolSpecs = [];
    this.stale = false;
    if (client) {
      await client.dispose().catch(() => undefined);
    }
  }

  private async connect(): Promise<ChatToolSpec[]> {
    const previous = this.client;
    this.client = undefined;
    if (previous) {
      await previous.dispose().catch(() => undefined);
    }
    const config = this.resolveConfig();
    if (!config) {
      throw new Error('Trading MCP server is not configured in mcp-config.json.');
    }
    const client = new McpClient({
      command: config.command,
      args: config.args,
      env: config.env,
      onLog: (line) => this.log(`[${config.name}] ${line}`),
      onExit: (code) => {
        this.stale = true;
        this.log(`[${config.name}] process exited (${code === null ? 'null' : code}); restart on next turn`);
      },
    });
    this.client = client;
    this.stale = false;
    await client.start();
    this.rememberSourceMtimes();
    this.toolSpecs = toChatTools(client.tools);
    this.log(`MCP tools loaded: ${this.toolSpecs.length}`);
    return this.toolSpecs;
  }

  private freshSourceMtimes(): number[] {
    try {
      return this.sourceMtimes().filter((mtime) => mtime > this.lastSourceMtime);
    } catch {
      return [];
    }
  }

  private rememberSourceMtimes(): void {
    try {
      for (const mtime of this.sourceMtimes()) {
        if (Number.isFinite(mtime) && mtime > this.lastSourceMtime) {
          this.lastSourceMtime = mtime;
        }
      }
    } catch {
      // the source directory is optional
    }
  }
}

export interface TurnUsage {
  model: string;
  messages: number;
  toolCalls: number;
  approximateTokens: number;
}

export interface TurnResult {
  modelLabel: string;
  toolCalls: number;
  usage: UsageInfo | null;
}

export interface ChatTurnHandlers {
  onDelta(chunk: string): void;
  onRecord(record: TranscriptRecord): void;
  onBusy(busy: boolean): void;
  onError(message: string): void;
  onUsage(usage: TurnUsage): void;
}

export interface ChatRunnerDeps {
  transcriptFs: TranscriptFs;
  transcriptDir: string;
  repoRoot: () => string;
  skills: () => SkillInfo[];
  agentBody: () => string;
  agentModel?: () => string;
  authPath?: () => string;
  mcp: McpService;
  log: (line: string) => void;
}

export class ChatRunner implements vscode.Disposable {
  private readonly deps: ChatRunnerDeps;
  private readonly fileTools = new FileToolService(() => ({
    roots: this.fileRoots(),
    homeDir: os.homedir(),
  }));
  private cancellation: vscode.CancellationTokenSource | undefined;
  private goClient: OpencodeGoClient | undefined;
  private protocolCache: { at: number; map: Map<string, string[]> } | undefined;
  private active = false;

  constructor(deps: ChatRunnerDeps) {
    this.deps = deps;
  }

  get busy(): boolean {
    return this.active;
  }

  stop(): void {
    this.cancellation?.cancel();
    this.goClient?.abort();
  }

  dispose(): void {
    this.stop();
    this.goClient?.dispose();
    this.goClient = undefined;
    this.cancellation?.dispose();
    this.cancellation = undefined;
  }

  providerStatus(): ProviderStatus {
    const configured = (this.configuration().get<string>('chat.provider') ?? 'auto').trim() || 'auto';
    const authPath = this.authPath();
    const keyPresent = readAuthKeyFromFile(authPath) !== null;
    const provider: ChatProvider =
      configured === 'copilot'
        ? 'copilot'
        : configured === 'opencode-go'
          ? 'opencode-go'
          : keyPresent
            ? 'opencode-go'
            : 'copilot';
    const configuredModel = (this.configuration().get<string>('chat.model') ?? '').trim();
    const agentModel = normalizeModelId(this.agentModel());
    const model = configuredModel.length > 0 ? normalizeModelId(configuredModel) : agentModel;
    return {
      configured,
      provider,
      model: model.length > 0 ? model : DEFAULT_OPENCODE_MODEL,
      modelSource: configuredModel.length > 0 ? 'setting' : agentModel.length > 0 ? 'agent' : 'default',
      authPath,
      keyPresent,
      roots: this.fileRoots(),
    };
  }

  async run(sessionId: string, prompt: string, handlers: ChatTurnHandlers): Promise<void> {
    if (this.active) {
      handlers.onBusy(true);
      return;
    }
    const text = prompt.trim();
    if (text.length === 0) {
      return;
    }
    this.active = true;
    const cancellation = new vscode.CancellationTokenSource();
    this.cancellation = cancellation;
    handlers.onBusy(true);
    const file = sessionFilePath(this.deps.transcriptDir, sessionId);
    try {
      const userRecord = this.persist(file, createRecord('user', sessionId, { text }));
      handlers.onRecord(userRecord);

      const route = await this.resolveRoute();
      const tools = await this.loadTools(handlers);
      const turn =
        route.provider === 'opencode-go'
          ? await this.runOpencodeGoTurn(file, sessionId, tools, cancellation, handlers)
          : await this.runCopilotTurn(file, sessionId, tools, cancellation, handlers, route.lmModelId);

      if (cancellation.token.isCancellationRequested) {
        handlers.onRecord(this.persist(file, createRecord('error', sessionId, { text: 'Stopped by user.' })));
      }

      this.emitUsage(sessionId, turn.modelLabel, turn.toolCalls, handlers, turn.usage);
    } catch (error) {
      const message = cancellation.token.isCancellationRequested ? 'Stopped by user.' : describeModelError(error);
      if (cancellation.token.isCancellationRequested) {
        handlers.onRecord(this.persist(file, createRecord('error', sessionId, { text: message })));
      } else {
        this.fail(file, sessionId, handlers, message);
      }
    } finally {
      this.active = false;
      this.cancellation = undefined;
      cancellation.dispose();
      handlers.onBusy(false);
    }
  }

  /**
   * Choose the backend for one turn.
   *
   * The direct OpenCode Go client speaks chat-completions only. A model that
   * needs another protocol (for example `generate-content` for Gemini) goes
   * through the VS Code language model API, where the OpenCode Go provider
   * extension (vendor `tradeAssistant.chat.lmVendor`) speaks every protocol.
   */
  private async resolveRoute(): Promise<{ provider: ChatProvider; lmModelId?: string }> {
    const configured = (this.configuration().get<string>('chat.provider') ?? 'auto').trim();
    if (configured === 'copilot') {
      return { provider: 'copilot' };
    }
    const apiKey = readAuthKeyFromFile(this.authPath());
    if (configured !== 'opencode-go' && apiKey === null) {
      return { provider: 'copilot' };
    }
    const model = this.resolveModelId();
    if (apiKey === null || model.length === 0) {
      return { provider: 'opencode-go' };
    }
    const protocols = await this.modelProtocols(apiKey);
    if (supportsChatCompletions(protocols, model)) {
      return { provider: 'opencode-go' };
    }
    this.deps.log(
      `model ${model} has no chat-completions endpoint (${(protocols.get(model) ?? []).join(', ')}); using the VS Code language model API`
    );
    return { provider: 'copilot', lmModelId: model };
  }

  private async modelProtocols(apiKey: string): Promise<Map<string, string[]>> {
    if (this.protocolCache && Date.now() - this.protocolCache.at < 3_600_000) {
      return this.protocolCache.map;
    }
    const probe = new OpencodeGoClient({ apiKey, model: DEFAULT_OPENCODE_MODEL, sessionId: 'protocol-probe', timeoutMs: 15_000 });
    try {
      const map = await probe.listModelProtocols();
      this.protocolCache = { at: Date.now(), map };
      return map;
    } catch (error) {
      this.deps.log(`opencode-go protocol probe failed: ${messageOf(error)}`);
      return new Map();
    } finally {
      probe.dispose();
    }
  }

  private authPath(): string {
    try {
      const custom = this.deps.authPath?.();
      if (custom && custom.trim().length > 0) {
        return path.resolve(custom.trim());
      }
    } catch {
      // fall back to the default location
    }
    return defaultAuthPath(os.homedir());
  }

  private agentModel(): string {
    try {
      return normalizeModelId(this.deps.agentModel?.() ?? '');
    } catch {
      return '';
    }
  }

  private fileRoots(): string[] {
    const configured = this.configuration().get<string[]>('fileAccess.roots') ?? [];
    const explicit = configured
      .filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
      .map((entry) => path.resolve(entry.trim()));
    if (explicit.length > 0) {
      return dedupe(explicit);
    }
    const workspaceFolders = (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath);
    return dedupe([...workspaceFolders, this.deps.repoRoot(), os.homedir()].filter((entry) => entry.length > 0));
  }

  private resolveModelId(): string {
    const configured = (this.configuration().get<string>('chat.model') ?? '').trim();
    return normalizeModelId(configured.length > 0 ? configured : this.agentModel());
  }

  private async firstAvailableModel(apiKey: string, sessionId: string): Promise<string> {
    const probe = new OpencodeGoClient({ apiKey, model: DEFAULT_OPENCODE_MODEL, sessionId, timeoutMs: 15_000 });
    try {
      const models = await probe.listModels();
      return models[0] ?? DEFAULT_OPENCODE_MODEL;
    } catch (error) {
      this.deps.log(`opencode-go model probe failed: ${messageOf(error)}`);
      return DEFAULT_OPENCODE_MODEL;
    } finally {
      probe.dispose();
    }
  }

  private async runOpencodeGoTurn(
    file: string,
    sessionId: string,
    tools: ChatToolSpec[],
    cancellation: vscode.CancellationTokenSource,
    handlers: ChatTurnHandlers
  ): Promise<TurnResult> {
    const apiKey = readAuthKeyFromFile(this.authPath());
    if (!apiKey) {
      this.fail(file, sessionId, handlers, MISSING_KEY_MESSAGE);
      return { modelLabel: 'opencode-go', toolCalls: 0, usage: null };
    }
    let model = this.resolveModelId();
    if (model.length === 0) {
      model = await this.firstAvailableModel(apiKey, sessionId);
    }
    const client = new OpencodeGoClient({
      apiKey,
      model,
      sessionId,
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
    this.goClient = client;
    const abort = new AbortController();
    const cancellationListener = cancellation.token.onCancellationRequested(() => abort.abort());
    const records = readSession(this.deps.transcriptFs, file);
    const messages: OpenAiMessage[] = toOpenAiMessages(records, this.systemPrompt(tools));
    const maxIterations = this.maxToolIterations();
    let toolCalls = 0;
    let usage: UsageInfo | null = null;
    let answered = false;
    try {
      for (let iteration = 0; iteration < maxIterations; iteration += 1) {
        if (cancellation.token.isCancellationRequested) {
          break;
        }
        const result = await client.streamChat({
          messages,
          tools,
          temperature: this.temperature(),
          signal: abort.signal,
          onDelta: (chunk) => handlers.onDelta(chunk),
        });
        if (result.usage) {
          usage = result.usage;
        }
        const text = result.text;
        if (text.trim().length > 0) {
          handlers.onRecord(this.persist(file, createRecord('assistant', sessionId, { text })));
        }
        if (cancellation.token.isCancellationRequested) {
          break;
        }
        if (result.toolCalls.length === 0) {
          answered = true;
          break;
        }
        messages.push({
          role: 'assistant',
          content: text.length > 0 ? text : null,
          tool_calls: result.toolCalls.map(
            (call): OpenAiToolCall => ({
              id: call.id,
              type: 'function',
              function: {
                name: call.name,
                arguments: call.argumentsText.length > 0 ? call.argumentsText : '{}',
              },
            })
          ),
        });
        for (const call of result.toolCalls) {
          const args = call.argumentsObject ?? {};
          handlers.onRecord(
            this.persist(file, createRecord('tool_call', sessionId, { name: call.name, callId: call.id, args }))
          );
          const outcome = await this.executeToolCall(call.name, args, call.parseError);
          toolCalls += 1;
          handlers.onRecord(
            this.persist(
              file,
              createRecord('tool_result', sessionId, {
                name: call.name,
                callId: call.id,
                ok: !outcome.isError,
                text: outcome.text,
              })
            )
          );
          messages.push({ role: 'tool', tool_call_id: call.id, content: compressToolOutput(outcome.text) });
        }
      }

      if (!answered && !cancellation.token.isCancellationRequested) {
        const final = await client.streamChat({
          messages: [...messages, { role: 'user', content: FINAL_ANSWER_NUDGE }],
          tools: [],
          temperature: this.temperature(),
          signal: abort.signal,
          onDelta: (chunk) => handlers.onDelta(chunk),
        });
        if (final.usage) {
          usage = final.usage;
        }
        if (final.text.trim().length > 0) {
          handlers.onRecord(this.persist(file, createRecord('assistant', sessionId, { text: final.text })));
        } else {
          const message = `The model reached ${maxIterations} tool iterations without a final answer. Send the message again to continue.`;
          handlers.onRecord(this.persist(file, createRecord('error', sessionId, { text: message })));
          handlers.onError(message);
        }
      }
    } finally {
      cancellationListener.dispose();
      client.dispose();
      if (this.goClient === client) {
        this.goClient = undefined;
      }
    }
    return { modelLabel: model, toolCalls, usage };
  }

  private async runCopilotTurn(
    file: string,
    sessionId: string,
    tools: ChatToolSpec[],
    cancellation: vscode.CancellationTokenSource,
    handlers: ChatTurnHandlers,
    preferredModelId?: string
  ): Promise<TurnResult> {
    const model = await this.selectModel(preferredModelId);
    if (!model) {
      this.fail(
        file,
        sessionId,
        handlers,
        'Copilot models unavailable. Install GitHub Copilot, sign in, then reload the window.'
      );
      return { modelLabel: 'copilot', toolCalls: 0, usage: null };
    }
    const chatTools: vscode.LanguageModelChatTool[] = tools.map((tool) => ({
      name: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema,
    }));
    const records = readSession(this.deps.transcriptFs, file);
    const messages = this.buildMessages(records, model, this.systemPrompt(tools));
    const maxIterations = this.maxToolIterations();
    let toolCalls = 0;
    let answered = false;

    for (let iteration = 0; iteration < maxIterations; iteration += 1) {
      if (cancellation.token.isCancellationRequested) {
        break;
      }
      const response = await model.sendRequest(
        messages,
        {
          justification: 'Trade Assistant answers your question with the trading MCP tools.',
          tools: chatTools,
          modelOptions: { temperature: this.temperature() },
        },
        cancellation.token
      );

      let streamed = '';
      const calls: vscode.LanguageModelToolCallPart[] = [];
      for await (const part of response.stream) {
        if (cancellation.token.isCancellationRequested) {
          break;
        }
        if (part instanceof vscode.LanguageModelTextPart) {
          streamed += part.value;
          handlers.onDelta(part.value);
        } else if (part instanceof vscode.LanguageModelToolCallPart) {
          calls.push(part);
        }
      }

      if (streamed.trim().length > 0) {
        handlers.onRecord(this.persist(file, createRecord('assistant', sessionId, { text: streamed })));
      }

      if (cancellation.token.isCancellationRequested) {
        break;
      }
      if (calls.length === 0) {
        answered = true;
        break;
      }

      messages.push(vscode.LanguageModelChatMessage.Assistant(calls));
      const results: vscode.LanguageModelToolResultPart[] = [];
      for (const call of calls) {
        handlers.onRecord(
          this.persist(
            file,
            createRecord('tool_call', sessionId, { name: call.name, callId: call.callId, args: call.input })
          )
        );
        const outcome = await this.executeToolCall(call.name, call.input, false);
        toolCalls += 1;
        handlers.onRecord(
          this.persist(
            file,
            createRecord('tool_result', sessionId, {
              name: call.name,
              callId: call.callId,
              ok: !outcome.isError,
              text: outcome.text,
            })
          )
        );
        results.push(
          new vscode.LanguageModelToolResultPart(call.callId, [
            new vscode.LanguageModelTextPart(compressToolOutput(outcome.text)),
          ])
        );
      }
      messages.push(vscode.LanguageModelChatMessage.User(results));
    }

    if (!answered && !cancellation.token.isCancellationRequested) {
      const final = await model.sendRequest(
        [...messages, vscode.LanguageModelChatMessage.User(FINAL_ANSWER_NUDGE)],
        {
          justification: 'Trade Assistant asks for the final answer without more tools.',
          tools: [],
          modelOptions: { temperature: this.temperature() },
        },
        cancellation.token
      );
      let finalText = '';
      for await (const part of final.stream) {
        if (cancellation.token.isCancellationRequested) {
          break;
        }
        if (part instanceof vscode.LanguageModelTextPart) {
          finalText += part.value;
          handlers.onDelta(part.value);
        }
      }
      if (finalText.trim().length > 0) {
        handlers.onRecord(this.persist(file, createRecord('assistant', sessionId, { text: finalText })));
      } else {
        const message = `The model reached ${maxIterations} tool iterations without a final answer. Send the message again to continue.`;
        handlers.onRecord(this.persist(file, createRecord('error', sessionId, { text: message })));
        handlers.onError(message);
      }
    }
    return { modelLabel: model.name || model.id, toolCalls, usage: null };
  }

  private fail(file: string, sessionId: string, handlers: ChatTurnHandlers, message: string): void {
    this.deps.log(`chat error: ${message}`);
    handlers.onRecord(this.persist(file, createRecord('error', sessionId, { text: message })));
    handlers.onError(message);
  }

  private persist(file: string, record: TranscriptRecord): TranscriptRecord {
    appendRecord(this.deps.transcriptFs, file, record);
    return record;
  }

  private async loadTools(handlers: ChatTurnHandlers): Promise<ChatToolSpec[]> {
    let remote: ChatToolSpec[] = [];
    try {
      const stale = this.deps.mcp.tools.length === 0;
      const tools = await this.deps.mcp.ensure();
      remote = tools;
      if (stale) {
        this.deps.log(`MCP tool surface ready: ${tools.length} tools`);
      }
    } catch (error) {
      const message = `Trading MCP server unavailable: ${messageOf(error)}`;
      this.deps.log(message);
      handlers.onError(message);
    }
    const names = new Set(remote.map((tool) => tool.name));
    const specs: ChatToolSpec[] = [...remote];
    if (!names.has(SKILL_LOOKUP_TOOL)) {
      specs.push(SKILL_LOOKUP_SPEC);
      names.add(SKILL_LOOKUP_TOOL);
    }
    for (const spec of this.fileTools.specs) {
      if (names.has(spec.name)) {
        continue;
      }
      names.add(spec.name);
      specs.push({ name: spec.name, description: spec.description, inputSchema: spec.inputSchema as object });
    }
    return specs;
  }

  private async executeToolCall(name: string, rawArgs: unknown, parseError: boolean): Promise<ToolCallOutcome> {
    if (isUnsafeToolName(name)) {
      return {
        isError: true,
        text: `Tool "${name}" is blocked: the Trade Assistant never places orders, transfers funds or closes positions.`,
      };
    }
    if (parseError) {
      return { isError: true, text: `Tool "${name}" received arguments that are not valid JSON. Send valid JSON.` };
    }
    const args = rawArgs && typeof rawArgs === 'object' && !Array.isArray(rawArgs) ? (rawArgs as Record<string, unknown>) : {};
    if (name === SKILL_LOOKUP_TOOL) {
      return { isError: false, text: this.lookupSkill(args) };
    }
    const remoteNames = new Set(this.deps.mcp.tools.map((tool) => tool.name));
    if (!remoteNames.has(name) && FILE_TOOL_NAMES.has(name)) {
      return this.fileTools.call(name, args);
    }
    try {
      return await this.deps.mcp.callTool(name, args);
    } catch (error) {
      return { isError: true, text: `Tool "${name}" failed: ${messageOf(error)}` };
    }
  }

  private lookupSkill(input: unknown): string {
    const query =
      input && typeof input === 'object'
        ? String((input as { query?: unknown }).query ?? (input as { name?: unknown }).name ?? '')
        : '';
    const needle = query.trim().toLowerCase();
    const skills = this.deps.skills();
    const matches = skills.filter((skill) => {
      if (needle.length === 0) {
        return true;
      }
      return `${skill.name} ${skill.description}`.toLowerCase().includes(needle);
    });
    if (matches.length === 0) {
      return `No skill matches "${query}". Available: ${skills.map((skill) => skill.name).slice(0, 40).join(', ')}`;
    }
    return matches
      .slice(0, 8)
      .map((skill) => `- ${skill.name}: ${skill.description}\n  path: ${skill.path}`)
      .join('\n');
  }

  private systemPrompt(tools: ChatToolSpec[]): string {
    const body = this.deps.agentBody().trim();
    const skills = this.deps.skills();
    const toolLines = tools.map((tool) => `- ${tool.name}: ${tool.description}`).join('\n');
    const skillLines = skills.map((skill) => `- ${skill.name}: ${skill.description}`).join('\n');
    const lines: string[] = [];
    if (body.length > 0) {
      lines.push(body, '');
    }
    lines.push(
      '## Runtime context',
      'You are embedded in the VS Code extension "Trade Assistant".',
      'Most tools in the list below come from the trading MCP server of this repository.',
      'skill_lookup searches the local skill catalogue.',
      'read_file, list_dir, find_files and search_text read the local disk. They only accept paths inside the configured file roots.',
      'Call a tool before you state a price, an indicator or a fundamental value.',
      'When the user gives paths, call read_file once on each path. Do not search a directory first.',
      'Answer as soon as you have the data. Do not repeat a tool call that already succeeded.',
      'A long tool result is compressed: read the head and the tail, then answer.',
      `Allowed file roots: ${this.fileRoots().join(', ')}`,
      'You never place orders and you never transfer funds.',
      'Finish the turn with a direct answer before you reach the tool iteration limit.',
      'Answer in concise markdown. Use two decimals for prices and name the tool that produced each number.',
      '',
      '## Available tools',
      toolLines,
      '',
      '## Skill catalogue'
    );
    if (skillLines.length > 0) {
      lines.push(skillLines);
    } else {
      lines.push('- (no skills found)');
    }
    if (skills.length === 0) {
      this.deps.log('chat: skill catalogue is empty, the system prompt has no skills');
    }
    return lines.join('\n');
  }

  private buildMessages(
    records: TranscriptRecord[],
    model: vscode.LanguageModelChat,
    systemPrompt: string
  ): vscode.LanguageModelChatMessage[] {
    const messages = toChatMessages(records, systemPrompt);
    const budget = Math.max(4000, Math.floor(model.maxInputTokens * HISTORY_TOKEN_BUDGET));
    while (messages.length > 2 && estimateTokens(messages) > budget) {
      const boundary = messages.findIndex((message, index) => index > 1 && isTurnStart(message));
      if (boundary === -1) {
        break;
      }
      messages.splice(1, boundary - 1);
    }
    return messages;
  }

  private async selectModel(preferredModelId?: string): Promise<vscode.LanguageModelChat | undefined> {
    if (preferredModelId && preferredModelId.length > 0) {
      const vendor = (this.configuration().get<string>('chat.lmVendor') ?? 'opencodego').trim() || 'opencodego';
      const preferred = await vscode.lm.selectChatModels({ vendor, id: preferredModelId });
      if (preferred.length > 0) {
        return preferred[0];
      }
      this.deps.log(
        `no ${vendor}/${preferredModelId} model in VS Code; install OnesoftQwQ.opencode-go-copilot-provider to use it. Falling back to Copilot models.`
      );
    }
    const family = this.configuration().get<string>('chat.modelFamily')?.trim() ?? '';
    const copilot = await vscode.lm.selectChatModels({ vendor: 'copilot' });
    let models = copilot.length > 0 ? copilot : await vscode.lm.selectChatModels({});
    if (family.length > 0) {
      const filtered = models.filter((model) => model.family === family || model.id === family || model.name === family);
      if (filtered.length > 0) {
        models = filtered;
      }
    }
    return models[0];
  }

  private configuration(): vscode.WorkspaceConfiguration {
    return vscode.workspace.getConfiguration('tradeAssistant');
  }

  private maxToolIterations(): number {
    const raw = this.configuration().get<number>('chat.maxToolIterations') ?? 14;
    return Math.min(40, Math.max(1, Math.floor(raw)));
  }

  private temperature(): number {
    const raw = this.configuration().get<number>('chat.temperature') ?? 0.2;
    return Math.min(2, Math.max(0, raw));
  }

  private emitUsage(
    sessionId: string,
    modelLabel: string,
    toolCalls: number,
    handlers: ChatTurnHandlers,
    usage?: UsageInfo | null
  ): void {
    const file = sessionFilePath(this.deps.transcriptDir, sessionId);
    const records = readSession(this.deps.transcriptFs, file);
    const chars = records.reduce((total, record) => total + (record.text?.length ?? 0), 0);
    const summary = summaryOf(records);
    const reported = (usage?.promptTokens ?? 0) + (usage?.completionTokens ?? 0);
    handlers.onUsage({
      model: modelLabel,
      messages: summary.messageCount,
      toolCalls,
      approximateTokens: reported > 0 ? reported : Math.round(chars / 4),
    });
  }
}

export function toOpenAiMessages(records: TranscriptRecord[], systemPrompt: string): OpenAiMessage[] {
  const messages: OpenAiMessage[] = [];
  if (systemPrompt.trim().length > 0) {
    messages.push({ role: 'system', content: systemPrompt });
  }
  let assistantText: string[] = [];
  let calls: OpenAiToolCall[] = [];

  const flushAssistant = (): void => {
    const text = assistantText.join('').trim();
    if (text.length === 0 && calls.length === 0) {
      assistantText = [];
      return;
    }
    const message: OpenAiMessage = { role: 'assistant', content: text.length > 0 ? text : null };
    if (calls.length > 0) {
      message.tool_calls = calls;
    }
    messages.push(message);
    assistantText = [];
    calls = [];
  };

  for (const record of records) {
    if (record.kind === 'user') {
      flushAssistant();
      const text = (record.text ?? '').trim();
      if (text.length > 0) {
        messages.push({ role: 'user', content: text });
      }
      continue;
    }
    if (record.kind === 'assistant') {
      if ((record.text ?? '').trim().length > 0) {
        assistantText.push(record.text ?? '');
      }
      continue;
    }
    if (record.kind === 'tool_call') {
      if (record.callId && record.name) {
        calls.push({
          id: record.callId,
          type: 'function',
          function: {
            name: record.name,
            arguments: JSON.stringify(record.args && typeof record.args === 'object' ? record.args : {}),
          },
        });
      }
      continue;
    }
    if (record.kind === 'tool_result') {
      flushAssistant();
      if (record.callId) {
        messages.push({
          role: 'tool',
          tool_call_id: record.callId,
          ...(record.name ? { name: record.name } : {}),
          content: record.text ?? '',
        });
      }
    }
  }
  flushAssistant();
  return messages;
}

export function toChatMessages(
  records: TranscriptRecord[],
  systemPrompt: string
): vscode.LanguageModelChatMessage[] {
  const messages: vscode.LanguageModelChatMessage[] = [];
  if (systemPrompt.trim().length > 0) {
    messages.push(vscode.LanguageModelChatMessage.User(systemPrompt));
  }
  let assistantText: string[] = [];
  let calls: vscode.LanguageModelToolCallPart[] = [];
  let results: vscode.LanguageModelToolResultPart[] = [];

  const flushAssistant = (): void => {
    const text = assistantText.join('').trim();
    if (text.length === 0 && calls.length === 0) {
      assistantText = [];
      return;
    }
    const parts: Array<vscode.LanguageModelTextPart | vscode.LanguageModelToolCallPart> = [];
    if (text.length > 0) {
      parts.push(new vscode.LanguageModelTextPart(text));
    }
    parts.push(...calls);
    if (parts.length > 0) {
      messages.push(vscode.LanguageModelChatMessage.Assistant(parts));
    }
    assistantText = [];
    calls = [];
  };

  const flushResults = (): void => {
    if (results.length > 0) {
      messages.push(vscode.LanguageModelChatMessage.User(results));
    }
    results = [];
  };

  for (const record of records) {
    if (record.kind === 'user') {
      flushResults();
      flushAssistant();
      const text = record.text ?? '';
      if (text.trim().length > 0) {
        messages.push(vscode.LanguageModelChatMessage.User(text));
      }
      continue;
    }
    if (record.kind === 'assistant') {
      if ((record.text ?? '').trim().length > 0) {
        assistantText.push(record.text ?? '');
      }
      continue;
    }
    if (record.kind === 'tool_call') {
      if (record.callId && record.name) {
        const input = record.args && typeof record.args === 'object' ? (record.args as object) : {};
        calls.push(new vscode.LanguageModelToolCallPart(record.callId, record.name, input));
      }
      continue;
    }
    if (record.kind === 'tool_result') {
      if (record.callId) {
        results.push(
          new vscode.LanguageModelToolResultPart(record.callId, [
            new vscode.LanguageModelTextPart(record.text ?? ''),
          ])
        );
      }
    }
  }
  flushResults();
  flushAssistant();
  return messages;
}

function isTurnStart(message: vscode.LanguageModelChatMessage): boolean {
  return (
    message.role === vscode.LanguageModelChatMessageRole.User &&
    message.content.some((part) => part instanceof vscode.LanguageModelTextPart)
  );
}

function estimateTokens(messages: vscode.LanguageModelChatMessage[]): number {
  let chars = 0;
  for (const message of messages) {
    for (const part of message.content) {
      if (part instanceof vscode.LanguageModelTextPart) {
        chars += part.value.length;
      } else {
        chars += 120;
      }
    }
  }
  return Math.ceil(chars / 4);
}

export function describeModelError(error: unknown): string {
  if (error instanceof vscode.LanguageModelError) {
    if (error.code === 'NoPermissions') {
      return 'Copilot did not grant access to the selected model. Open Copilot Chat, select a model, then retry.';
    }
    if (error.code === 'Blocked') {
      return 'Access to the selected model is blocked by policy. Choose another model in tradeAssistant.chat.modelFamily.';
    }
    if (error.code === 'NotFound') {
      return 'The selected model is not available. Clear tradeAssistant.chat.modelFamily to use automatic selection.';
    }
    if (error.code === 'QuotaExceeded') {
      return 'The Copilot quota for this model is exhausted. Retry later or pick another model.';
    }
    return `Language model error: ${error.message}`;
  }
  return messageOf(error);
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const resolved = path.resolve(value);
    if (seen.has(resolved)) {
      continue;
    }
    seen.add(resolved);
    result.push(resolved);
  }
  return result;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
