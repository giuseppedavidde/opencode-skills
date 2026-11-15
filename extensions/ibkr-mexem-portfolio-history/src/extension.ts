import * as vscode from 'vscode';
import { CHAT_CONSENT_KEY, ChatViewProvider } from './chat/chatViewProvider.ts';
import { CHAT_API_KEY_SECRET } from './chat/credentials.ts';
import { PortfolioContextStore } from './chat/portfolioContext.ts';
import { CredentialStore } from './config/secrets.ts';
import { HistoryPanel } from './panel/historyPanel.ts';
import type { PanelDependencies } from './panel/historyPanel.ts';
import { HistoryViewProvider } from './panel/historyViewProvider.ts';

let outputChannel: vscode.OutputChannel | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const store = new CredentialStore(context.secrets, context.globalState);
  outputChannel = vscode.window.createOutputChannel('IBKR Mexem Portfolio History');
  const output = outputChannel;
  context.subscriptions.push(output);

  // One shared portfolio context: the panel publishes, the chat reads.
  const chatContext = new PortfolioContextStore();
  const deps: PanelDependencies = { extensionUri: context.extensionUri, store, output, chat: chatContext };
  const viewProvider = new HistoryViewProvider(deps);
  const chatProvider = new ChatViewProvider({
    extensionUri: context.extensionUri,
    output,
    portfolio: chatContext,
    secrets: context.secrets,
    globalState: context.globalState,
    globalStorageUri: context.globalStorageUri
  });

  output.appendLine(`[${new Date().toISOString()}] IBKR Mexem Portfolio History activated.`);

  context.subscriptions.push(
    viewProvider,
    chatProvider,
    vscode.window.registerWebviewViewProvider(HistoryViewProvider.viewType, viewProvider, {
      webviewOptions: { retainContextWhenHidden: true }
    }),
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chatProvider, {
      webviewOptions: { retainContextWhenHidden: true }
    }),
    vscode.commands.registerCommand('ibkrHistory.open', () => {
      HistoryPanel.createOrShow(deps);
    }),
    vscode.commands.registerCommand('ibkrHistory.openChat', async () => {
      await vscode.commands.executeCommand('ibkrHistory.chat.focus');
    }),
    vscode.commands.registerCommand('ibkrHistory.analyzeWithTradeAgent', () => chatProvider.handoff()),
    vscode.commands.registerCommand('ibkrHistory.fetch', () => {
      const panel = HistoryPanel.current;
      if (panel) {
        panel.requestFetch();
        return;
      }
      if (viewProvider.requestFetch()) {
        return;
      }
      HistoryPanel.createOrShow(deps, { fetchOnOpen: true });
    }),
    vscode.commands.registerCommand('ibkrHistory.exportCsv', async () => {
      const panel = HistoryPanel.current;
      if (panel) {
        await panel.exportCsv();
        return;
      }
      if (await viewProvider.exportCsv()) {
        return;
      }
      await vscode.window.showWarningMessage('Open the IBKR Portfolio History panel and fetch a report first.');
    }),
    vscode.commands.registerCommand('ibkrHistory.copyDiagnostics', async () => {
      const panel = HistoryPanel.current;
      if (panel) {
        await panel.copyDiagnostics();
        return;
      }
      if (await viewProvider.copyDiagnostics()) {
        return;
      }
      await vscode.window.showWarningMessage('No diagnostics to copy. Fetch a report first.');
    }),
    vscode.commands.registerCommand('ibkrHistory.clearCredentials', async () => {
      const confirm = await vscode.window.showWarningMessage(
        'Delete the stored Flex token and Query ID from VS Code SecretStorage?',
        { modal: true },
        'Delete'
      );
      if (confirm !== 'Delete') {
        return;
      }
      await store.clearToken();
      await store.clearQueryId();
      output.appendLine(`[${new Date().toISOString()}] Stored Flex credentials cleared.`);
      await vscode.window.showInformationMessage('Stored Flex token and Query ID deleted.');
      await HistoryPanel.current?.refreshState();
      await viewProvider.refreshState();
    }),
    vscode.commands.registerCommand('ibkrHistory.setChatApiKey', async () => {
      const key = await vscode.window.showInputBox({
        title: 'IBKR History: Set Chat API Key',
        prompt: 'Paste the opencode-go API key. It is stored in VS Code SecretStorage and never sent to the webview.',
        password: true,
        ignoreFocusOut: true,
        placeHolder: 'API key'
      });
      if (key === undefined || key.trim().length === 0) {
        return;
      }
      await context.secrets.store(CHAT_API_KEY_SECRET, key.trim());
      output.appendLine(`[${new Date().toISOString()}] Chat API key stored in SecretStorage.`);
      await vscode.window.showInformationMessage('Chat API key stored.');
      await chatProvider.refreshState();
    }),
    vscode.commands.registerCommand('ibkrHistory.clearChatApiKey', async () => {
      const confirm = await vscode.window.showWarningMessage(
        'Delete the stored chat API key from VS Code SecretStorage?',
        { modal: true },
        'Delete'
      );
      if (confirm !== 'Delete') {
        return;
      }
      await context.secrets.delete(CHAT_API_KEY_SECRET);
      output.appendLine(`[${new Date().toISOString()}] Chat API key deleted.`);
      await vscode.window.showInformationMessage('Chat API key deleted.');
      await chatProvider.refreshState();
    }),
    vscode.commands.registerCommand('ibkrHistory.resetChatConsent', async () => {
      await context.globalState.update(CHAT_CONSENT_KEY, false);
      output.appendLine(`[${new Date().toISOString()}] Chat send consent reset.`);
      await vscode.window.showInformationMessage('Chat data consent reset. The next send asks again.');
    })
  );
}

export function deactivate(): void {
  outputChannel?.dispose();
  outputChannel = undefined;
}
