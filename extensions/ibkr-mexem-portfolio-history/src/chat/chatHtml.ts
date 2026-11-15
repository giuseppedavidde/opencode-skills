import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';
import { CHAT_NOTICE_LM } from './protocol.ts';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Sidebar HTML for the Trade Chat. Same CSP pattern as the portfolio panel:
 * a nonce for the one local script, no remote origin, no inline handler.
 */
export function renderChatHtml(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  notice: string = CHAT_NOTICE_LM
): string {
  const nonce = randomBytes(16).toString('base64');
  const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', 'chat.js'));
  const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', 'chat.css'));
  const csp = [
    "default-src 'none'",
    `style-src ${webview.cspSource}`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
    "connect-src 'none'",
    "img-src 'none'",
    "form-action 'none'",
    "base-uri 'none'"
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${styleUri}" />
  <title>Trade Chat</title>
</head>
<body>
  <header class="chat-head">
    <div class="chat-title">
      <h1>Trade Chat</h1>
      <span id="context-badge" class="badge" role="status">No dataset</span>
    </div>
    <div class="chat-actions">
      <label class="model-field">
        <span class="sr-only">Model</span>
        <select id="model" aria-label="Model"></select>
      </label>
      <button id="btn-handoff" class="ghost" type="button">Open in @trade</button>
      <button id="btn-clear" class="ghost" type="button">Clear chat</button>
      <button id="btn-copy" class="ghost" type="button">Copy transcript</button>
    </div>
  </header>

  <p id="notice" class="notice" role="note">${escapeHtml(notice)}</p>

  <p id="key-hint" class="hint hidden" role="status"></p>

  <main id="messages" class="messages" aria-live="polite" aria-label="Conversation"></main>

  <section id="empty" class="empty">
    <p>Fetch a report first. The chat needs the trades dataset.</p>
    <button id="btn-fetch" class="primary" type="button">Fetch report</button>
  </section>

  <footer class="composer">
    <label class="sr-only" for="input">Message</label>
    <textarea id="input" rows="3" placeholder="Ask about your realized P&amp;L, symbols, drawdown…"></textarea>
    <div class="composer-actions">
      <button id="btn-send" class="primary" type="button">Send</button>
      <button id="btn-stop" class="ghost" type="button" disabled>Stop</button>
      <span id="status" class="hint" role="status">Enter sends, Shift+Enter adds a new line.</span>
    </div>
  </footer>

  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
}
