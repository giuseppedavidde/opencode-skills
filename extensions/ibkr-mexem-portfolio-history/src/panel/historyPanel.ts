import * as vscode from 'vscode';
import { createOutputLogger, HistoryController } from './historyController.ts';
import type { PanelDependencies } from './historyController.ts';
import { renderHtml } from './html.ts';
import type { WebviewMessage } from './protocol.ts';

export type { PanelDependencies };

/**
 * Editor-tab surface. It only owns the tab lifecycle and forwards everything else
 * to the shared {@link HistoryController}.
 */
export class HistoryPanel {
  static current: HistoryPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private readonly controller: HistoryController;
  private readonly disposables: vscode.Disposable[] = [];
  private disposed = false;

  private constructor(panel: vscode.WebviewPanel, deps: PanelDependencies) {
    this.panel = panel;
    this.panel.webview.options = { enableScripts: true, localResourceRoots: [deps.extensionUri] };
    this.panel.webview.html = renderHtml(this.panel.webview, deps.extensionUri);

    this.controller = new HistoryController(deps, {
      post: (message) => this.panel.webview.postMessage(message),
      log: createOutputLogger(deps.output)
    });

    this.disposables.push(
      this.panel.webview.onDidReceiveMessage((message: WebviewMessage) => {
        void this.controller.handleMessage(message);
      }),
      this.panel.onDidDispose(() => this.dispose())
    );

    HistoryPanel.current = this;
  }

  static createOrShow(deps: PanelDependencies, options: { fetchOnOpen?: boolean } = {}): HistoryPanel {
    if (HistoryPanel.current) {
      HistoryPanel.current.reveal(options);
      return HistoryPanel.current;
    }
    const panel = vscode.window.createWebviewPanel(
      HistoryController.viewType,
      'IBKR Portfolio History',
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [deps.extensionUri]
      }
    );
    const instance = new HistoryPanel(panel, deps);
    if (options.fetchOnOpen) {
      instance.requestFetch();
    }
    return instance;
  }

  reveal(options: { fetchOnOpen?: boolean } = {}): void {
    this.panel.reveal(vscode.ViewColumn.One);
    if (options.fetchOnOpen) {
      this.requestFetch();
    }
  }

  get hasData(): boolean {
    return this.controller.hasData;
  }

  async refreshState(): Promise<void> {
    await this.controller.refreshState();
  }

  requestFetch(): void {
    this.controller.requestFetch();
  }

  async exportCsv(): Promise<void> {
    await this.controller.exportCsv();
  }

  async copyDiagnostics(): Promise<void> {
    await this.controller.copyDiagnostics();
  }

  dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    if (HistoryPanel.current === this) {
      HistoryPanel.current = undefined;
    }
    this.controller.dispose();
    for (const disposable of this.disposables) {
      disposable.dispose();
    }
    this.disposables.length = 0;
    this.panel.dispose();
  }
}
