import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import type { BudgetAppService } from '../appService';
import type { WebviewMessage } from '../types';

export type Page = 'dashboard' | 'data' | 'month' | 'chat';

export const BUDGET_VIEW_ID = 'budgetApp.dashboardView';

export class BudgetView implements vscode.WebviewViewProvider, vscode.Disposable {
  private view: vscode.WebviewView | null = null;
  private ready = false;
  private pendingNavigation: Page | null = null;
  private readyResolve: (() => void) | null = null;
  private readyPromise = new Promise<void>((resolve) => {
    this.readyResolve = resolve;
  });
  private readonly disposables: vscode.Disposable[] = [];

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly service: BudgetAppService,
  ) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.resetForNewView(view);
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this.context.extensionUri, 'dist'),
        vscode.Uri.joinPath(this.context.extensionUri, 'media'),
      ],
    };
    view.webview.html = getHtml(view.webview, this.context.extensionUri);

    this.service.attach((message) => {
      void Promise.resolve(view.webview.postMessage(message)).catch(() => undefined);
    });

    view.webview.onDidReceiveMessage(
      async (message: WebviewMessage) => {
        if (message.type === 'ready') this.ready = true;
        await this.service.handleMessage(message);
        if (message.type === 'ready') {
          this.readyResolve?.();
          this.readyResolve = null;
          if (this.pendingNavigation) {
            const page = this.pendingNavigation;
            this.pendingNavigation = null;
            void Promise.resolve(view.webview.postMessage({ type: 'navigate', page })).catch(
              () => undefined,
            );
          }
        }
      },
      null,
      this.disposables,
    );

    view.onDidDispose(
      () => {
        if (this.view !== view) return;
        this.service.detach();
        this.view = null;
        this.ready = false;
        this.clearDisposables();
      },
      null,
      this.disposables,
    );
  }

  get current(): vscode.WebviewView | null {
    return this.view;
  }

  whenReady(): Promise<void> {
    return this.ready ? Promise.resolve() : this.readyPromise;
  }

  async reveal(page?: Page): Promise<void> {
    if (!this.view) {
      await vscode.commands.executeCommand(`${BUDGET_VIEW_ID}.focus`);
      await Promise.race([
        this.whenReady(),
        new Promise<void>((resolve) => setTimeout(resolve, 5000)),
      ]);
    }
    if (page) this.navigate(page);
  }

  navigate(page: Page): void {
    if (this.view && this.ready) {
      void Promise.resolve(
        this.view.webview.postMessage({ type: 'navigate', page }),
      ).catch(() => undefined);
    } else {
      this.pendingNavigation = page;
    }
  }

  dispose(): void {
    this.service.detach();
    this.view = null;
    this.clearDisposables();
  }

  private resetForNewView(view: vscode.WebviewView): void {
    if (this.view && this.view !== view) this.clearDisposables();
    this.view = view;
    this.ready = false;
    this.pendingNavigation = null;
    this.readyPromise = new Promise<void>((resolve) => {
      this.readyResolve = resolve;
    });
  }

  private clearDisposables(): void {
    for (const disposable of this.disposables) disposable.dispose();
    this.disposables.length = 0;
  }
}

export function getHtml(webview: vscode.Webview, extensionUri: vscode.Uri): string {
  const nonce = randomBytes(16).toString('hex');
  const scriptUri = webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, 'dist', 'webview.js'),
  );
  const plotlyUri = webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, 'dist', 'media', 'plotly.min.js'),
  );
  const styleUri = webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, 'dist', 'media', 'styles.css'),
  );
  const iconUri = webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, 'dist', 'media', 'icon.png'),
  );
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data: blob:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}' ${webview.cspSource}`,
    `font-src ${webview.cspSource} data:`,
    `connect-src 'none'`,
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" href="${iconUri}" />
  <link rel="stylesheet" href="${styleUri}" />
  <title>Budget App</title>
</head>
<body>
  <div id="root"><div class="boot">Caricamento Budget App…</div></div>
  <script nonce="${nonce}" src="${plotlyUri}"></script>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
}
