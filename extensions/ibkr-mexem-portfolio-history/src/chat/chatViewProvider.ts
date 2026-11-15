import * as vscode from 'vscode';
import { buildChatContext, formatGeneratedAt, TRADE_AGENT_PERSONA } from './context.ts';
import type { ChatContextResult } from './context.ts';
import { ChatError, streamChatCompletion, trimHistory } from './client.ts';
import type { ChatMessage } from './client.ts';
import { resolveChatSettings } from './chatSettings.ts';
import type { ChatSettings } from './chatSettings.ts';
import { CHAT_API_KEY_SECRET, resolveApiKey } from './credentials.ts';
import { renderChatHtml } from './chatHtml.ts';
import { buildHandoffQuery, handoffHeader, handoffStamp } from './handoff.ts';
import { describeLanguageModelError, selectModel, toLmMessages, toModelOptions } from './lm.ts';
import type { LanguageModelMessage } from './lm.ts';
import { chainKey, renderMarketDataBlock, valueOptions } from './marketData.ts';
import { MarketDataService } from './marketDataService.ts';
import type { MarketDataResult } from './marketDataService.ts';
import { openOptionPositions } from './optionSymbol.ts';
import type { PortfolioContextStore } from './portfolioContext.ts';
import type { DatasetPayload } from '../panel/protocol.ts';
import {
  chatNotice,
  DEFAULT_CHAT_BACKEND,
  MODEL_OPTIONS,
  NO_LANGUAGE_MODEL_MESSAGE
} from './protocol.ts';
import type { ChatBackend, ChatHostMessage, ChatWebviewMessage, ContextBadge, ModelOption } from './protocol.ts';

export const CHAT_VIEW_TYPE = 'ibkrHistory.chat';
/** Global-state key of the one-time send consent. */
export const CHAT_CONSENT_KEY = 'ibkrHistory.chat.consent';
/** Persistent privacy notice shown in the view for the default backend. */
export const CHAT_NOTICE = chatNotice(DEFAULT_CHAT_BACKEND);

/** Why VS Code grants the extension access to the selected language model. */
const LM_JUSTIFICATION =
  'Answer questions about the IBKR portfolio dataset that this extension already holds in its Trade Chat view.';

export type { ChatSettings } from './chatSettings.ts';

export interface ChatDependencies {
  readonly extensionUri: vscode.Uri;
  readonly output: vscode.OutputChannel;
  readonly portfolio: PortfolioContextStore;
  readonly secrets: vscode.SecretStorage;
  readonly globalState: vscode.Memento;
  /** Where the `Open in @trade` handoff files are written. */
  readonly globalStorageUri: vscode.Uri;
}

/** Reads the chat settings. The defaults mirror `contributes.configuration`. */
export function readChatSettings(): ChatSettings {
  return resolveChatSettings(vscode.workspace.getConfiguration('ibkrHistory'));
}

/**
 * Sidebar chat view. The conversation lives in the extension host; the webview
 * only renders it. The portfolio dataset is always part of the first user
 * message, so a new fetch changes the answer without a new conversation.
 *
 * Two backends:
 * - `lm`: `vscode.lm`, so the chat uses the language model provider that is
 *   already signed in to VS Code. No API key.
 * - `http`: the OpenAI-compatible client against `ibkrHistory.chat.baseUrl`.
 */
export class ChatViewProvider implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewType = CHAT_VIEW_TYPE;

  private view: vscode.WebviewView | undefined;
  private history: ChatMessage[] = [];
  private abort: AbortController | undefined;
  private lmCancellation: vscode.CancellationTokenSource | undefined;
  private unsubscribe: (() => void) | undefined;
  private webviewDisposable: vscode.Disposable | undefined;
  private pendingError: string | undefined;
  private marketDataService: MarketDataService | undefined;
  private marketDataTemplate: string | undefined;

  constructor(private readonly deps: ChatDependencies) {}

  get isBusy(): boolean {
    return this.abort !== undefined;
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.deps.extensionUri]
    };
    webviewView.webview.html = renderChatHtml(
      webviewView.webview,
      this.deps.extensionUri,
      chatNotice(readChatSettings().backend)
    );

    this.unsubscribe?.();
    this.unsubscribe = this.deps.portfolio.onDidChange(() => {
      void this.postContext();
    });

    this.webviewDisposable?.dispose();
    this.webviewDisposable = webviewView.webview.onDidReceiveMessage((message: ChatWebviewMessage) => {
      void this.handleMessage(message);
    });

    webviewView.onDidDispose(() => {
      this.webviewDisposable?.dispose();
      this.webviewDisposable = undefined;
      this.unsubscribe?.();
      this.unsubscribe = undefined;
      this.stop();
      this.view = undefined;
    });
  }

  /** Re-send the header state, for example after the API key or a setting changed. */
  async refreshState(): Promise<void> {
    if (!this.view) {
      return;
    }
    await this.postState();
    await this.postContext();
    if (this.pendingError) {
      await this.post({ type: 'error', message: this.pendingError });
    }
  }

  private async post(message: ChatHostMessage): Promise<void> {
    await this.view?.webview.postMessage(message);
  }

  private log(message: string): void {
    this.deps.output.appendLine(`[${new Date().toISOString()}] chat: ${message}`);
  }

  private async postState(): Promise<void> {
    const settings = readChatSettings();
    const notice = chatNotice(settings.backend);
    if (settings.backend === 'lm') {
      const models = await this.loadLmModelOptions();
      await this.post({
        type: 'state',
        backend: settings.backend,
        notice,
        models,
        model: settings.model,
        hasApiKey: true,
        keySource: null
      });
      if (models.length === 0) {
        await this.post({ type: 'info', message: NO_LANGUAGE_MODEL_MESSAGE });
      }
      return;
    }
    const resolved = await resolveApiKey({ readSecret: async () => this.deps.secrets.get(CHAT_API_KEY_SECRET) });
    await this.post({
      type: 'state',
      backend: settings.backend,
      notice,
      models: MODEL_OPTIONS,
      model: settings.model,
      hasApiKey: Boolean(resolved),
      keySource: resolved?.source ?? null
    });
  }

  /** The `vscode.lm` model list. A selection failure becomes an empty list. */
  private async loadLmModelOptions(): Promise<ModelOption[]> {
    try {
      const models = await vscode.lm.selectChatModels({});
      return toModelOptions(models);
    } catch (error) {
      this.log(`Language model selection failed: ${error instanceof Error ? error.name : 'unknown'}`);
      return [];
    }
  }

  private contextPayload(): { result: ChatContextResult | undefined; badge: ContextBadge | null } {
    const dataset = this.deps.portfolio.get();
    if (!dataset) {
      return { result: undefined, badge: null };
    }
    const result = buildChatContext(dataset, { maxContextTrades: readChatSettings().maxContextTrades });
    return {
      result,
      badge: {
        trades: dataset.meta.rowsInRange,
        baseCurrency: dataset.baseCurrency,
        generatedAt: formatGeneratedAt(dataset.meta.generatedAt),
        approxTokens: result.approxTokens,
        presetLabel: dataset.meta.range.label
      }
    };
  }

  private async postContext(): Promise<void> {
    const { result, badge } = this.contextPayload();
    await this.post({ type: 'context', available: result !== undefined, badge });
  }

  /** One service per provider, so a second question inside ten minutes reuses the chains. */
  private marketDataServiceFor(settings: ChatSettings): MarketDataService {
    if (!this.marketDataService || this.marketDataTemplate !== settings.marketDataCommand) {
      this.marketDataService = new MarketDataService({ commandTemplate: settings.marketDataCommand });
      this.marketDataTemplate = settings.marketDataCommand;
    }
    return this.marketDataService;
  }

  /**
   * The live option block of the open option positions, or the one-line
   * limitation. Never throws and never blocks the send: a failure becomes a
   * stated limitation.
   */
  private async marketDataLines(dataset: DatasetPayload, settings: ChatSettings): Promise<string[]> {
    if (!settings.marketData) {
      return [];
    }
    const positions = openOptionPositions(dataset.trades);
    if (positions.length === 0) {
      return [];
    }
    const requests = [
      ...new Map(
        positions.map((position) => [
          chainKey(position.contract.root, position.contract.expiry),
          { ticker: position.contract.root, expiry: position.contract.expiry }
        ])
      ).values()
    ];
    const service = this.marketDataServiceFor(settings);
    const startedAt = Date.now();
    let cancelled = false;
    // The CLI needs 10 s to 20 s. The window progress keeps the view responsive
    // and lets the user abandon the wait without cancelling the send.
    const result = await vscode.window.withProgress<MarketDataResult | undefined>(
      {
        location: vscode.ProgressLocation.Window,
        title: 'IBKR History: fetching live option prices…',
        cancellable: true
      },
      async (_progress, token) =>
        new Promise<MarketDataResult | undefined>((resolve) => {
          let settled = false;
          const finish = (value: MarketDataResult | undefined): void => {
            if (!settled) {
              settled = true;
              resolve(value);
            }
          };
          token.onCancellationRequested(() => {
            cancelled = true;
            finish(undefined);
          });
          void service.fetchChains(requests).then(
            (value) => finish(value),
            () => finish(undefined)
          );
        })
    );
    const elapsed = Date.now() - startedAt;
    if (!result) {
      this.log(`market-data: 0 chain(s), 1 error(s), ${elapsed} ms`);
      const reason = cancelled ? 'the fetch was cancelled' : 'the fetch failed';
      return ['', `Live option data is not available: ${reason}. The option values below are not current.`];
    }
    this.log(`market-data: ${result.chains.size} chain(s), ${result.errors.length} error(s), ${elapsed} ms`);
    if (result.chains.size === 0) {
      const reason = result.errors[0]?.message ?? 'no option chain is available';
      return ['', `Live option data is not available: ${reason}. The option values below are not current.`];
    }
    return renderMarketDataBlock(valueOptions(positions, result.chains), result.chains, result.fetchedAt, {
      missing: result.errors,
      omitted: result.omitted
    });
  }

  /** The context text of one send: the portfolio dataset, then the live option block. */
  private async prepareSend(
    settings: ChatSettings
  ): Promise<{ readonly result: ChatContextResult; readonly text: string } | undefined> {
    const dataset = this.deps.portfolio.get();
    const { result } = this.contextPayload();
    if (!dataset || !result) {
      return undefined;
    }
    const extra = await this.marketDataLines(dataset, settings);
    return { result, text: extra.length > 0 ? `${result.text}\n${extra.join('\n')}` : result.text };
  }

  /**
   * Write the same context to `<globalStorageUri>/handoff/portfolio-<stamp>.md`
   * and open the chat with the `@trade` agent on that file.
   */
  async handoff(): Promise<void> {
    const settings = readChatSettings();
    const prepared = await this.prepareSend(settings);
    if (!prepared) {
      await vscode.window.showWarningMessage('No portfolio dataset yet. Fetch a report first.');
      return;
    }
    const dataset = this.deps.portfolio.get();
    if (!dataset) {
      await vscode.window.showWarningMessage('No portfolio dataset yet. Fetch a report first.');
      return;
    }
    const directory = vscode.Uri.joinPath(this.deps.globalStorageUri, 'handoff');
    const file = vscode.Uri.joinPath(directory, `portfolio-${handoffStamp(new Date())}.md`);
    const body = [...handoffHeader(dataset, new Date().toISOString()), '', prepared.text, ''].join('\n');
    try {
      await vscode.workspace.fs.createDirectory(directory);
      await vscode.workspace.fs.writeFile(file, Buffer.from(body, 'utf8'));
    } catch (error) {
      this.log(`handoff failed: ${error instanceof Error ? error.name : 'unknown'}`);
      await vscode.window.showErrorMessage(
        `Cannot write the handoff file: ${error instanceof Error ? error.message : String(error)}`
      );
      return;
    }
    this.log(`handoff: wrote ${file.fsPath} (${body.length} chars).`);
    await vscode.commands.executeCommand('workbench.action.chat.open', { query: buildHandoffQuery(file.fsPath) });
  }

  async handleMessage(message: ChatWebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case 'ready':
          await this.postState();
          await this.postContext();
          if (this.pendingError) {
            await this.post({ type: 'error', message: this.pendingError });
          }
          break;
        case 'send':
          await this.send(message.text);
          break;
        case 'stop':
          this.stop();
          break;
        case 'clear':
          this.history = [];
          this.pendingError = undefined;
          await this.post({ type: 'cleared' });
          break;
        case 'copyTranscript':
          await vscode.env.clipboard.writeText(message.text);
          await this.post({ type: 'info', message: 'Transcript copied to the clipboard.' });
          break;
        case 'fetchReport':
          await vscode.commands.executeCommand('ibkrHistory.fetch');
          break;
        case 'handoff':
          await this.handoff();
          break;
        case 'setModel':
          await vscode.workspace
            .getConfiguration('ibkrHistory')
            .update('chat.model', message.model, true)
            .then(
              () => this.postState(),
              () => undefined
            );
          break;
        default:
          break;
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      this.log(`Unhandled message error: ${error instanceof Error ? error.name : 'unknown'}`);
      await this.post({ type: 'error', message: `Unexpected chat failure: ${detail}` });
      await this.post({ type: 'busy', busy: false });
    }
  }

  private async ensureConsent(backend: ChatBackend, destination: string): Promise<boolean> {
    if (this.deps.globalState.get<boolean>(CHAT_CONSENT_KEY, false)) {
      return true;
    }
    const credentialNote =
      backend === 'lm'
        ? 'No Flex token is sent and no API key is used. The destination is the VS Code language model provider you selected.'
        : 'No Flex token and no API key are sent.';
    const detail =
      'This sends the following data to ' +
      destination +
      ':\n' +
      '• Symbols, quantities, prices and trade dates\n' +
      '• Realized P&L and the P&L provenance\n' +
      '• Commissions per trade currency\n' +
      '• Account ids and the date range\n\n' +
      credentialNote +
      ' The data leaves this machine only for the chat request.';
    const title =
      backend === 'lm'
        ? 'Send portfolio data to the language model provider?'
        : 'Send portfolio data to the chat provider?';
    const choice = await vscode.window.showWarningMessage(
      title,
      { modal: true, detail },
      'Send and remember',
      'Cancel'
    );
    if (choice !== 'Send and remember') {
      await this.post({ type: 'info', message: 'Cancelled. Nothing was sent.' });
      return false;
    }
    await this.deps.globalState.update(CHAT_CONSENT_KEY, true);
    return true;
  }

  private stop(): void {
    this.abort?.abort();
    this.lmCancellation?.cancel();
  }

  private async send(rawText: string): Promise<void> {
    const text = rawText.trim();
    if (text.length === 0) {
      return;
    }
    if (this.abort) {
      await this.post({ type: 'info', message: 'A reply is already streaming. Use Stop first.' });
      return;
    }
    if (!this.deps.portfolio.get()) {
      const message = 'No portfolio dataset yet. Fetch a report first.';
      this.pendingError = message;
      await this.post({ type: 'error', message });
      return;
    }

    const settings = readChatSettings();
    const destination =
      settings.backend === 'lm' ? 'the VS Code language model provider you selected' : httpHost(settings.baseUrl);
    if (!(await this.ensureConsent(settings.backend, destination))) {
      return;
    }

    if (settings.backend === 'lm') {
      await this.sendWithLm(text, settings);
      return;
    }
    await this.sendWithHttp(text, settings);
  }

  /** Primary backend: `vscode.lm`. The dataset rides in the first user message. */
  private async sendWithLm(text: string, settings: ChatSettings): Promise<void> {
    const prepared = await this.prepareSend(settings);
    if (!prepared) {
      await this.post({ type: 'error', message: 'No portfolio dataset yet. Fetch a report first.' });
      return;
    }
    const { result } = prepared;

    let models: readonly vscode.LanguageModelChat[] = [];
    try {
      models = await vscode.lm.selectChatModels({});
    } catch (error) {
      this.log(`Language model selection failed: ${error instanceof Error ? error.name : 'unknown'}`);
    }
    const model = selectModel(models, settings.model);
    if (!model) {
      this.pendingError = NO_LANGUAGE_MODEL_MESSAGE;
      await this.post({ type: 'error', message: NO_LANGUAGE_MODEL_MESSAGE });
      return;
    }
    this.pendingError = undefined;

    const userMessage: ChatMessage = { role: 'user', content: text };
    const turns = trimHistory([...this.history, userMessage], settings.maxHistoryMessages);
    const last = turns[turns.length - 1];
    const historyTurns: readonly ChatMessage[] = last && last.role === 'user' ? turns.slice(0, -1) : turns;
    const messages = toLmMessages(TRADE_AGENT_PERSONA, prepared.text, historyTurns, text).map((message) =>
      toLanguageModelMessage(message)
    );

    const controller = new AbortController();
    const cancellation = new vscode.CancellationTokenSource();
    const onAbort = (): void => cancellation.cancel();
    controller.signal.addEventListener('abort', onAbort, { once: true });
    this.abort = controller;
    this.lmCancellation = cancellation;

    await this.post({ type: 'busy', busy: true });
    this.log(
      `Request start: backend=lm, model=${model.id}, rows=${result.tradeRowsIncluded}, approxTokens=${result.approxTokens}`
    );

    let answer = '';
    try {
      const response = await model.sendRequest(messages, { justification: LM_JUSTIFICATION }, cancellation.token);
      for await (const fragment of response.text) {
        if (controller.signal.aborted) {
          break;
        }
        if (fragment.length === 0) {
          continue;
        }
        answer += fragment;
        await this.post({ type: 'delta', text: fragment });
      }
      if (controller.signal.aborted) {
        this.log('Request stopped by the user.');
        await this.post({ type: 'info', message: 'Stopped. The partial answer was discarded.' });
        return;
      }
      this.history = trimHistory(
        [...this.history, userMessage, { role: 'assistant', content: answer }],
        settings.maxHistoryMessages
      );
      this.log(`Request done: ${answer.length} chars in the answer.`);
      await this.post({ type: 'done', text: answer });
    } catch (error) {
      if (controller.signal.aborted) {
        this.log('Request stopped by the user.');
        await this.post({ type: 'info', message: 'Stopped. The partial answer was discarded.' });
      } else {
        const message = describeLanguageModelError(error);
        this.log(`Request failed: ${error instanceof Error ? error.name : 'unknown'}`);
        this.pendingError = message;
        await this.post({ type: 'error', message });
      }
    } finally {
      controller.signal.removeEventListener('abort', onAbort);
      cancellation.dispose();
      this.lmCancellation = undefined;
      this.abort = undefined;
      await this.post({ type: 'busy', busy: false });
    }
  }

  /** Secondary backend: the OpenAI-compatible HTTP client with an API key. */
  private async sendWithHttp(text: string, settings: ChatSettings): Promise<void> {
    const resolved = await resolveApiKey({ readSecret: async () => this.deps.secrets.get(CHAT_API_KEY_SECRET) });
    if (!resolved) {
      const message =
        'No chat API key. Run "IBKR History: Set Chat API Key", or set OPENCODE_API_KEY, or sign in with opencode.';
      this.pendingError = message;
      await this.post({ type: 'error', message });
      void vscode.window
        .showWarningMessage(message, 'Set Chat API Key')
        .then((choice) =>
          choice === 'Set Chat API Key' ? vscode.commands.executeCommand('ibkrHistory.setChatApiKey') : undefined
        );
      return;
    }
    this.pendingError = undefined;

    const prepared = await this.prepareSend(settings);
    if (!prepared) {
      await this.post({ type: 'error', message: 'No portfolio dataset yet. Fetch a report first.' });
      return;
    }
    const { result } = prepared;

    const userMessage: ChatMessage = { role: 'user', content: text };
    const systemMessage: ChatMessage = {
      role: 'system',
      content: `${TRADE_AGENT_PERSONA}\n\n---\n\n${prepared.text}`
    };
    const messages = trimHistory([systemMessage, ...this.history, userMessage], settings.maxHistoryMessages);

    const controller = new AbortController();
    this.abort = controller;
    await this.post({ type: 'busy', busy: true });
    this.log(
      `Request start: backend=http, model=${settings.model}, rows=${result.tradeRowsIncluded}, approxTokens=${result.approxTokens}`
    );

    try {
      const answer = await streamChatCompletion({
        baseUrl: settings.baseUrl,
        apiKey: resolved.key,
        model: settings.model,
        messages,
        temperature: settings.temperature,
        maxTokens: settings.maxTokens,
        signal: controller.signal,
        onDelta: (delta) => {
          void this.post({ type: 'delta', text: delta });
        }
      });
      this.history = trimHistory(
        [...this.history, userMessage, { role: 'assistant', content: answer.text }],
        settings.maxHistoryMessages
      );
      this.log(`Request done: ${answer.text.length} chars in the answer.`);
      await this.post({ type: 'done', text: answer.text });
    } catch (error) {
      if (error instanceof ChatError) {
        if (/cancelled/i.test(error.message)) {
          this.log('Request stopped by the user.');
          await this.post({ type: 'info', message: 'Stopped. The partial answer was discarded.' });
        } else {
          this.log(`Request failed: ${error.status ?? 'no status'} ${error.message}`);
          this.pendingError = error.message;
          await this.post({ type: 'error', message: error.message });
        }
      } else {
        const message = error instanceof Error ? error.message : String(error);
        this.log(`Request failed with unexpected error: ${error instanceof Error ? error.name : 'unknown'}`);
        this.pendingError = message;
        await this.post({ type: 'error', message });
      }
    } finally {
      this.abort = undefined;
      await this.post({ type: 'busy', busy: false });
    }
  }

  dispose(): void {
    this.webviewDisposable?.dispose();
    this.webviewDisposable = undefined;
    this.unsubscribe?.();
    this.unsubscribe = undefined;
    this.stop();
    this.abort = undefined;
    this.lmCancellation = undefined;
    this.view = undefined;
    this.history = [];
    this.marketDataService?.clear();
    this.marketDataService = undefined;
    this.marketDataTemplate = undefined;
  }
}

/** The host name for the consent text. A malformed URL is shown verbatim. */
function httpHost(baseUrl: string): string {
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl;
  }
}

/** `LanguageModelChatMessage` has only the two statics, hence the mapping. */
function toLanguageModelMessage(message: LanguageModelMessage): vscode.LanguageModelChatMessage {
  return message.role === 'assistant'
    ? vscode.LanguageModelChatMessage.Assistant(message.content)
    : vscode.LanguageModelChatMessage.User(message.content);
}
