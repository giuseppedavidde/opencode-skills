import * as vscode from 'vscode';
import { createOutputLogger, HistoryController } from './historyController.ts';
import type { PanelDependencies } from './historyController.ts';
import { renderHtml } from './html.ts';
import type { WebviewMessage } from './protocol.ts';

/**
 * Activity Bar surface. It renders the same HTML and speaks the same protocol as
 * the editor tab, because both delegate to {@link HistoryController}.
 */
export class HistoryViewProvider implements vscode.WebviewViewProvider {
  static readonly viewType = HistoryController.viewType;

  private view: vscode.WebviewView | undefined;
  private controller: HistoryController | undefined;
  private viewDisposable: vscode.Disposable | undefined;

  constructor(private readonly deps: PanelDependencies) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.deps.extensionUri]
    };
    webviewView.webview.html = renderHtml(webviewView.webview, this.deps.extensionUri);

    this.viewDisposable?.dispose();
    this.controller?.dispose();

    const controller = new HistoryController(this.deps, {
      post: (message) => webviewView.webview.postMessage(message),
      log: createOutputLogger(this.deps.output)
    });
    this.controller = controller;

    this.viewDisposable = vscode.Disposable.from(
      webviewView.webview.onDidReceiveMessage((message: WebviewMessage) => {
        void controller.handleMessage(message);
      }),
      webviewView.onDidDispose(() => {
        if (this.controller === controller) {
          this.controller.dispose();
          this.controller = undefined;
          this.view = undefined;
        }
      })
    );
  }

  get isResolved(): boolean {
    return this.controller !== undefined;
  }

  get hasData(): boolean {
    return this.controller?.hasData ?? false;
  }

  requestFetch(): boolean {
    if (!this.controller) {
      return false;
    }
    void this.view?.show(true);
    this.controller.requestFetch();
    return true;
  }

  async exportCsv(): Promise<boolean> {
    if (!this.controller) {
      return false;
    }
    await this.controller.exportCsv();
    return true;
  }

  async copyDiagnostics(): Promise<boolean> {
    if (!this.controller) {
      return false;
    }
    await this.controller.copyDiagnostics();
    return true;
  }

  async refreshState(): Promise<void> {
    await this.controller?.refreshState();
  }

  dispose(): void {
    this.viewDisposable?.dispose();
    this.viewDisposable = undefined;
    this.controller?.dispose();
    this.controller = undefined;
    this.view = undefined;
  }
}
