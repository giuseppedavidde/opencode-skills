import * as vscode from 'vscode';
import { BudgetAppService } from './appService';
import { BUDGET_VIEW_ID, BudgetView } from './webview/panel';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Budget App');
  const service = new BudgetAppService(context, context.extensionPath, output);
  const view = new BudgetView(context, service);
  context.subscriptions.push(output, service, view);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(BUDGET_VIEW_ID, view, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('budget.openDashboard', async () => {
      await view.reveal('dashboard');
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('budget.importBankStatement', async () => {
      await view.reveal('month');
      await view.whenReady();
      await service.openImportFlow('hybrid');
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('budget.openChat', async () => {
      await view.reveal('chat');
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('budgetApp.dbPath')) {
        void service
          .reloadDatabase()
          .catch((error: unknown) =>
            vscode.window.showErrorMessage(`Budget: ${(error as Error).message}`),
          );
      }
    }),
  );

  output.appendLine('[activate] Budget App Manager pronto.');
}

export function deactivate(): void {
  // Disposables registered in context.subscriptions close the database and view.
}
