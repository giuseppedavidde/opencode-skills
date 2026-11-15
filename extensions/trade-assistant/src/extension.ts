import * as os from 'node:os';
import * as path from 'node:path';
import * as vscode from 'vscode';
import {
  CapabilityState,
  TradeAgentCapabilities,
  TradingServerConfig,
  capabilitySignature,
  createNodeFsAdapter,
  diffSkillDirectories,
  extractFrontmatter,
  parseTradeAgent,
  resolveTradingServer,
  scanSkillCatalogue,
} from './core/capabilities';
import { resolveRepoRoot, type RepoRootResolution } from './core/roots';
import { collectSourceMtimes, createDebouncer, createNodeMtimeAdapter } from './core/sync';
import { createNodeTranscriptFs } from './core/transcript';
import { ChatPanel } from './ui/chatPanel';
import { ChatRunner, McpService } from './ui/chatRunner';
import { TradeTreeProvider } from './ui/tree';

const fsAdapter = createNodeFsAdapter();
const mtimeAdapter = createNodeMtimeAdapter();
const AGENT_FILE = path.join('agents', 'trade.md');
const MCP_SOURCE_DIR = path.join('mcp', 'src');

let activeMcp: McpService | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Trade Assistant');
  const tree = new TradeTreeProvider();
  const view = vscode.window.createTreeView('tradeAssistant.tree', { treeDataProvider: tree });
  let state: CapabilityState | undefined;
  let signature = '';
  let toolCommands: vscode.Disposable[] = [];
  const log = (line: string): void => output.appendLine(`[${new Date().toISOString()}] ${line}`);

  let rootResolution: RepoRootResolution | undefined;

  const resolveRoot = (): RepoRootResolution => {
    const configured = vscode.workspace.getConfiguration('tradeAssistant').get<string>('repoRoot')?.trim();
    const resolution = resolveRepoRoot({
      configured,
      workspaceFolders: (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath),
      homeDir: os.homedir(),
      extensionRoot: path.resolve(__dirname, '..'),
      exists: (target) => fsAdapter.exists(target),
    });
    rootResolution = resolution;
    return resolution;
  };

  const repoRoot = (): string => (rootResolution ?? resolveRoot()).root;

  const mcpConfigPath = (): string => {
    const configured = vscode.workspace.getConfiguration('tradeAssistant').get<string>('mcpConfigPath')?.trim();
    return configured ? path.resolve(configured) : path.join(os.homedir(), '.copilot', 'mcp-config.json');
  };

  const serverName = (): string =>
    vscode.workspace.getConfiguration('tradeAssistant').get<string>('tradingServerName')?.trim() || 'trading';

  const readServer = (errors: string[]): TradingServerConfig | null => {
    const target = mcpConfigPath();
    try {
      const resolved = resolveTradingServer(fsAdapter.readFile(target), serverName());
      if (!resolved) {
        errors.push(`Trading server "${serverName()}" not found in ${target}`);
      }
      return resolved;
    } catch {
      errors.push(`Cannot read MCP config: ${target}`);
      return null;
    }
  };

  const load = (): CapabilityState => {
    const errors: string[] = [];
    const resolution = resolveRoot();
    const root = resolution.root;
    let agent: TradeAgentCapabilities | null = null;
    const agentPath = path.join(root, AGENT_FILE);
    try {
      agent = parseTradeAgent(fsAdapter.readFile(agentPath), 'trade');
    } catch {
      errors.push(
        `Cannot read agent definition: ${agentPath} (repo root ${resolution.source}; set tradeAssistant.repoRoot)`
      );
    }
    const server = readServer(errors);
    let skills = [] as CapabilityState['skills'];
    try {
      skills = scanSkillCatalogue(path.join(root, 'skills'), fsAdapter);
    } catch {
      errors.push(`Cannot scan skills directory: ${path.join(root, 'skills')}`);
    }
    return { agent, server, skills, errors };
  };

  const registerToolCommands = (tools: string[]): void => {
    toolCommands.forEach((disposable) => disposable.dispose());
    toolCommands = [];
    for (const tool of tools) {
      if (tool.includes('*')) {
        continue;
      }
      toolCommands.push(vscode.commands.registerCommand(commandIdForTool(tool), () => runTradingTool(tool)));
    }
  };

  const sourceMtimes = (): number[] => collectSourceMtimes(path.join(repoRoot(), MCP_SOURCE_DIR), mtimeAdapter);

  const mcp = new McpService(
    () => {
      const server = state?.server ?? readServer([]);
      return server ? { name: server.name, command: server.command, args: server.args, env: server.env } : null;
    },
    log,
    sourceMtimes
  );
  activeMcp = mcp;

  const agentBody = (): string => {
    try {
      return extractFrontmatter(fsAdapter.readFile(path.join(repoRoot(), AGENT_FILE))).body;
    } catch {
      return '';
    }
  };

  const agentModel = (): string => {
    try {
      const data = extractFrontmatter(fsAdapter.readFile(path.join(repoRoot(), AGENT_FILE))).data;
      const model = data.model;
      return typeof model === 'string' ? model : '';
    } catch {
      return '';
    }
  };

  const transcriptFs = createNodeTranscriptFs();
  const transcriptDir = path.join(context.globalStorageUri.fsPath, 'chat');

  const chatRunner = new ChatRunner({
    transcriptFs,
    transcriptDir,
    repoRoot,
    skills: () => state?.skills ?? [],
    agentBody,
    agentModel,
    mcp,
    log,
  });

  const chatPanel = new ChatPanel(context, chatRunner, transcriptFs, transcriptDir, log);

  const refresh = (reason: string): void => {
    try {
      const next = load();
      const nextSignature = capabilitySignature(next);
      if (nextSignature === signature) {
        return;
      }
      signature = nextSignature;
      state = next;
      tree.setState(next);
      registerToolCommands(next.agent?.mcpTools ?? []);
      mcp.markStale(`capability change (${reason})`);
      log(
        `refreshed (${reason}): ${next.agent?.mcpTools.length ?? 0} tools, ${next.skills.length} skills, ${next.errors.length} errors`
      );
    } catch (error) {
      log(`refresh failed: ${messageOf(error)}`);
    }
  };

  let rootPrompted = false;

  const offerRepoRoot = async (): Promise<void> => {
    if (rootPrompted) {
      return;
    }
    rootPrompted = true;
    const choice = await vscode.window.showWarningMessage(
      'Trade Assistant: cannot find the opencode-skills repository. Select the folder that contains agents/trade.md.',
      'Locate repository'
    );
    if (choice !== 'Locate repository') {
      return;
    }
    const picked = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      openLabel: 'Use as repository root',
    });
    if (!picked || picked.length === 0) {
      return;
    }
    await vscode.workspace
      .getConfiguration('tradeAssistant')
      .update('repoRoot', picked[0].fsPath, vscode.ConfigurationTarget.Global);
    signature = '';
    rootResolution = undefined;
    refresh('repo root selected');
  };

  const openFile = async (target: string, preview: boolean): Promise<void> => {
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(target));
    await vscode.window.showTextDocument(document, { preview });
  };

  const openTradeAgent = async (): Promise<void> => {
    const target = path.join(repoRoot(), AGENT_FILE);
    try {
      await openFile(target, true);
    } catch (error) {
      void vscode.window.showErrorMessage(`Trade Assistant: cannot open ${target}. ${messageOf(error)}`);
    }
  };

  const openSkillFile = async (target?: string): Promise<void> => {
    if (!target) {
      return;
    }
    try {
      await openFile(target, true);
    } catch (error) {
      void vscode.window.showErrorMessage(`Trade Assistant: cannot open ${target}. ${messageOf(error)}`);
    }
  };

  const listSkills = async (): Promise<void> => {
    if (!state || state.skills.length === 0) {
      refresh('listSkills');
    }
    const skills = state?.skills ?? [];
    if (skills.length === 0) {
      void vscode.window.showWarningMessage('Trade Assistant: no skills found.');
      return;
    }
    const picked = await vscode.window.showQuickPick(
      skills.map((skill) => ({ label: skill.name, description: skill.description, detail: skill.path, skill })),
      { placeHolder: `Select a skill (${skills.length})`, matchOnDescription: true, matchOnDetail: true }
    );
    if (picked) {
      await openSkillFile(picked.skill.path);
    }
  };

  const runTradingTool = async (tool?: string): Promise<void> => {
    const ticker = await vscode.window.showInputBox({
      prompt: 'Ticker for context',
      placeHolder: 'AAPL',
      ignoreFocusOut: true,
    });
    if (ticker === undefined) {
      return;
    }
    const server = state?.server ?? readServer([]);
    if (!server) {
      void vscode.window.showErrorMessage('Trade Assistant: trading server not found in mcp-config.json.');
      return;
    }
    const terminal = vscode.window.createTerminal({ name: 'Trade Assistant', cwd: repoRoot() });
    context.subscriptions.push(terminal);
    terminal.show();
    const normalizedTicker = ticker.trim().toUpperCase() || 'n/a';
    const label = `Trade Assistant - ticker=${normalizedTicker}${tool ? ` tool=${tool}` : ''}`;
    terminal.sendText(`echo ${quote(label)}`);
    terminal.sendText([quote(server.command), ...server.args.map(quote), '--help'].join(' '));
  };

  const showMismatch = (): void => {
    const repoSkills = path.join(repoRoot(), 'skills');
    const installedSkills = path.join(os.homedir(), '.copilot', 'skills');
    const drift = diffSkillDirectories(repoSkills, installedSkills, fsAdapter);
    output.show(true);
    output.appendLine(`Skill drift - ${new Date().toISOString()}`);
    output.appendLine(`repo:      ${repoSkills}`);
    output.appendLine(`installed: ${installedSkills}`);
    output.appendLine(`missing in installed: ${drift.missingInInstalled.length}`);
    drift.missingInInstalled.forEach((name) => output.appendLine(`  - ${name}`));
    output.appendLine(`extra in installed: ${drift.extraInInstalled.length}`);
    drift.extraInInstalled.forEach((name) => output.appendLine(`  + ${name}`));
    if (drift.missingInInstalled.length === 0 && drift.extraInInstalled.length === 0) {
      output.appendLine('No drift detected.');
    }
  };

  const showProviderStatus = (): void => {
    const status = chatRunner.providerStatus();
    output.show(true);
    output.appendLine(`Provider status - ${new Date().toISOString()}`);
    output.appendLine(`configured provider: ${status.configured}`);
    output.appendLine(`active provider:     ${status.provider}`);
    output.appendLine(`model:               ${status.model} (source: ${status.modelSource})`);
    output.appendLine(`auth file:           ${status.authPath}`);
    output.appendLine(`key present:         ${status.keyPresent ? 'yes' : 'no'}`);
    output.appendLine(`allowed file roots (${status.roots.length}):`);
    status.roots.forEach((root) => output.appendLine(`  ${root}`));
    output.appendLine('blocked file patterns: .ssh/id_*, auth.json, .netrc, *.pem, credentials*, .aws/credentials');
  };

  const addAllowedFolder = async (): Promise<void> => {
    const picked = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: true,
      openLabel: 'Allow file access',
    });
    if (!picked || picked.length === 0) {
      return;
    }
    const configuration = vscode.workspace.getConfiguration('tradeAssistant');
    const current = (configuration.get<string[]>('fileAccess.roots') ?? []).filter(
      (entry): entry is string => typeof entry === 'string' && entry.trim().length > 0
    );
    const merged = [...new Set([...current.map((entry) => path.resolve(entry.trim())), ...picked.map((uri) => uri.fsPath)])];
    await configuration.update('fileAccess.roots', merged, vscode.ConfigurationTarget.Global);
    log(`allowed file roots updated: ${merged.join(', ')}`);
    void vscode.window.showInformationMessage(`Trade Assistant: ${picked.length} folder(s) added to the allowed file roots.`);
  };

  const registerWatchers = (): vscode.Disposable[] => {
    const configuredDelay = vscode.workspace.getConfiguration('tradeAssistant').get<number>('debounceMs') ?? 600;
    const debounceMs = Math.max(500, configuredDelay);
    const refreshDebouncer = createDebouncer(() => refresh('watcher'), debounceMs);
    const pythonDebouncer = createDebouncer(() => {
      mcp.markStale('python source change under mcp/src');
      log('mcp/src changed: the trading MCP server restarts on the next chat turn');
    }, debounceMs);
    const root = repoRoot();
    const configPath = mcpConfigPath();
    const patterns: Array<{ pattern: vscode.GlobPattern; trigger: () => void }> = [
      { pattern: new vscode.RelativePattern(vscode.Uri.file(path.join(root, 'agents')), '*.md'), trigger: () => refreshDebouncer.trigger() },
      { pattern: new vscode.RelativePattern(vscode.Uri.file(path.join(root, 'skills')), '**/SKILL.md'), trigger: () => refreshDebouncer.trigger() },
      {
        pattern: new vscode.RelativePattern(vscode.Uri.file(path.dirname(configPath)), path.basename(configPath)),
        trigger: () => refreshDebouncer.trigger(),
      },
      { pattern: new vscode.RelativePattern(path.join(root, MCP_SOURCE_DIR), '**/*.py'), trigger: () => pythonDebouncer.trigger() },
    ];
    const disposables: vscode.Disposable[] = [
      new vscode.Disposable(() => {
        refreshDebouncer.cancel();
        pythonDebouncer.cancel();
      }),
    ];
    for (const entry of patterns) {
      const watcher = vscode.workspace.createFileSystemWatcher(entry.pattern);
      disposables.push(
        watcher,
        watcher.onDidCreate(() => entry.trigger()),
        watcher.onDidChange(() => entry.trigger()),
        watcher.onDidDelete(() => entry.trigger())
      );
    }
    return disposables;
  };

  context.subscriptions.push(
    output,
    tree,
    view,
    mcp,
    chatRunner,
    chatPanel,
    vscode.window.registerWebviewViewProvider(ChatPanel.viewId, chatPanel, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.commands.registerCommand('tradeAssistant.openTradeAgent', openTradeAgent),
    vscode.commands.registerCommand('tradeAssistant.listSkills', listSkills),
    vscode.commands.registerCommand('tradeAssistant.runTradingTool', runTradingTool),
    vscode.commands.registerCommand('tradeAssistant.showMismatch', showMismatch),
    vscode.commands.registerCommand('tradeAssistant.openSkillFile', openSkillFile),
    vscode.commands.registerCommand('tradeAssistant.newChatSession', async () => {
      chatPanel.newSession();
      await chatPanel.reveal();
    }),
    vscode.commands.registerCommand('tradeAssistant.exportTranscript', () => chatPanel.exportCurrent()),
    vscode.commands.registerCommand('tradeAssistant.showProviderStatus', showProviderStatus),
    vscode.commands.registerCommand('tradeAssistant.addAllowedFolder', addAllowedFolder),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (!event.affectsConfiguration('tradeAssistant')) {
        return;
      }
      if (
        event.affectsConfiguration('tradeAssistant.mcpConfigPath') ||
        event.affectsConfiguration('tradeAssistant.tradingServerName')
      ) {
        mcp.markStale('mcp configuration change');
      }
      signature = '';
      refresh('configuration');
    }),
    new vscode.Disposable(() => toolCommands.forEach((disposable) => disposable.dispose())),
    ...registerWatchers()
  );

  refresh('activate');
  if (state?.agent == null) {
    void offerRepoRoot();
  }
}

export function deactivate(): void {
  const mcp = activeMcp;
  activeMcp = undefined;
  if (mcp) {
    void mcp.dispose();
  }
}

function commandIdForTool(tool: string): string {
  return `tradeAssistant.tool.${tool.replace(/[^A-Za-z0-9_]/g, '_')}`;
}

function quote(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
