import * as vscode from 'vscode';
import type { SessionSummary, TranscriptFs, TranscriptRecord } from '../core/transcript';
import {
  exportSession,
  listSessions,
  newSessionId,
  readSession,
  sanitizeSessionId,
  sessionFilePath,
  summaryOf,
} from '../core/transcript';
import type { ChatRunner, ChatTurnHandlers, TurnUsage } from './chatRunner';

const CURRENT_SESSION_KEY = 'tradeAssistant.chat.sessionId';

interface InboundMessage {
  type?: unknown;
  text?: unknown;
  sessionId?: unknown;
}

export class ChatPanel implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewId = 'tradeAssistant.chat';

  private view: vscode.WebviewView | undefined;
  private readonly disposables: vscode.Disposable[] = [];
  private sessionId: string;
  private usage: TurnUsage | undefined;
  private lastError = '';

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly runner: ChatRunner,
    private readonly transcriptFs: TranscriptFs,
    private readonly transcriptDir: string,
    private readonly log: (line: string) => void
  ) {
    this.sessionId = this.restoreSessionId();
  }

  get currentSessionId(): string {
    return this.sessionId;
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'resources')],
    };
    webviewView.webview.html = this.html(webviewView.webview);
    this.disposables.push(
      webviewView.webview.onDidReceiveMessage((message: InboundMessage) => {
        void this.handleMessage(message);
      }),
      webviewView.onDidDispose(() => {
        this.view = undefined;
      })
    );
    void this.pushState();
  }

  dispose(): void {
    this.disposables.forEach((disposable) => disposable.dispose());
    this.disposables.length = 0;
    this.view = undefined;
  }

  newSession(): void {
    this.runner.stop();
    this.sessionId = newSessionId();
    this.usage = undefined;
    this.lastError = '';
    void this.context.globalState.update(CURRENT_SESSION_KEY, this.sessionId);
    this.log(`chat session: ${this.sessionId}`);
    void this.pushState();
  }

  selectSession(sessionId: string): void {
    const sanitized = sanitizeSessionId(sessionId);
    if (sanitized.length === 0 || sanitized === this.sessionId) {
      return;
    }
    this.runner.stop();
    this.sessionId = sanitized;
    this.usage = undefined;
    this.lastError = '';
    void this.context.globalState.update(CURRENT_SESSION_KEY, this.sessionId);
    void this.pushState();
  }

  async exportCurrent(): Promise<void> {
    const records = this.readCurrent();
    if (records.length === 0) {
      void vscode.window.showInformationMessage('Trade Assistant: the current chat is empty.');
      return;
    }
    const content = exportSession(records);
    const document = await vscode.workspace.openTextDocument({ content, language: 'markdown' });
    await vscode.window.showTextDocument(document, { preview: true });
  }

  async reveal(): Promise<void> {
    await vscode.commands.executeCommand(`${ChatPanel.viewId}.focus`);
  }

  private restoreSessionId(): string {
    const stored = this.context.globalState.get<string>(CURRENT_SESSION_KEY) ?? '';
    const sanitized = sanitizeSessionId(stored);
    if (sanitized.length > 0) {
      return sanitized;
    }
    const created = newSessionId();
    void this.context.globalState.update(CURRENT_SESSION_KEY, created);
    return created;
  }

  private readCurrent(): TranscriptRecord[] {
    return readSession(this.transcriptFs, sessionFilePath(this.transcriptDir, this.sessionId));
  }

  private async handleMessage(message: InboundMessage): Promise<void> {
    if (!message || typeof message !== 'object') {
      return;
    }
    if (message.type === 'send') {
      const text = typeof message.text === 'string' ? message.text : '';
      await this.send(text);
      return;
    }
    if (message.type === 'stop') {
      this.runner.stop();
      return;
    }
    if (message.type === 'newSession') {
      this.newSession();
      return;
    }
    if (message.type === 'selectSession' && typeof message.sessionId === 'string') {
      this.selectSession(message.sessionId);
      return;
    }
    if (message.type === 'export') {
      await this.exportCurrent();
      return;
    }
    if (message.type === 'ready') {
      await this.pushState();
    }
  }

  private async send(text: string): Promise<void> {
    if (text.trim().length === 0) {
      return;
    }
    if (this.runner.busy) {
      this.post({ type: 'busy', busy: true });
      return;
    }
    this.lastError = '';
    const handlers: ChatTurnHandlers = {
      onDelta: (chunk) => this.post({ type: 'delta', text: chunk }),
      onRecord: (record) => this.post({ type: 'append', record }),
      onBusy: (busy) => this.post({ type: 'busy', busy }),
      onError: (errorMessage) => {
        this.lastError = errorMessage;
        this.post({ type: 'error', message: errorMessage });
      },
      onUsage: (usage) => {
        this.usage = usage;
      },
    };
    await this.runner.run(this.sessionId, text, handlers);
    await this.pushState();
  }

  private async pushState(): Promise<void> {
    const file = sessionFilePath(this.transcriptDir, this.sessionId);
    const records = readSession(this.transcriptFs, file);
    const sessions: SessionSummary[] = listSessions(this.transcriptFs, this.transcriptDir);
    this.post({
      type: 'state',
      sessionId: this.sessionId,
      records,
      sessions,
      summary: summaryOf(records),
      busy: this.runner.busy,
      usage: this.usage,
      error: this.lastError,
    });
  }

  private post(message: unknown): void {
    void this.view?.webview.postMessage(message);
  }

  private html(webview: vscode.Webview): string {
    const nonce = createNonce();
    const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'resources', 'chat.js'));
    const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'resources', 'chat.css'));
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource} data:; style-src ${webview.cspSource}; font-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="${styleUri}" rel="stylesheet">
<title>Trade Assistant Chat</title>
</head>
<body>
<header class="bar">
  <select id="sessions" title="Conversation"></select>
  <button id="new" type="button" title="New chat">New</button>
  <button id="export" type="button" title="Export transcript as markdown">Export</button>
</header>
<main id="messages" aria-live="polite"></main>
<footer class="composer">
  <textarea id="input" rows="3" placeholder="Ask the Trade Assistant" spellcheck="false"></textarea>
  <div class="actions">
    <span id="usage" class="usage"></span>
    <button id="send" type="button" class="primary">Send</button>
    <button id="stop" type="button" disabled>Stop</button>
  </div>
</footer>
<script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

function createNonce(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  for (let index = 0; index < 32; index += 1) {
    nonce += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  }
  return nonce;
}
