/**
 * Trade Chat webview. It only renders state sent by the host: the conversation,
 * the model list, the portfolio badge and the streaming deltas.
 *
 * Model output goes through `renderMarkdown`, which escapes first. Never assign
 * unescaped text to `innerHTML`.
 */
import { renderMarkdown } from '../markdown.ts';
import type { ChatHostMessage, ChatWebviewMessage, ContextBadge, ModelOption } from '../protocol.ts';

declare function acquireVsCodeApi(): {
  postMessage(message: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
};

const vscode = acquireVsCodeApi();

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) {
    throw new Error(`Missing element #${id}`);
  }
  return node as T;
}

const messages = el<HTMLElement>('messages');
const input = el<HTMLTextAreaElement>('input');
const status = el<HTMLElement>('status');
const badge = el<HTMLElement>('context-badge');
const empty = el<HTMLElement>('empty');
const modelSelect = el<HTMLSelectElement>('model');
const keyHint = el<HTMLElement>('key-hint');
const notice = el<HTMLElement>('notice');
const sendButton = el<HTMLButtonElement>('btn-send');
const stopButton = el<HTMLButtonElement>('btn-stop');

let busy = false;
let streaming: HTMLElement | null = null;
let streamingText: HTMLElement | null = null;
let lastUserText = '';
let renderedModels = '';

function post(message: ChatWebviewMessage): void {
  vscode.postMessage(message);
}

function setStatus(text: string): void {
  status.textContent = text;
}

function setBusy(value: boolean): void {
  busy = value;
  sendButton.disabled = value;
  stopButton.disabled = !value;
  input.disabled = value;
}

function scrollToBottom(): void {
  messages.scrollTop = messages.scrollHeight;
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${Math.round(tokens / 1000)}k`;
  }
  return String(tokens);
}

function userBubble(text: string): void {
  const bubble = document.createElement('article');
  bubble.className = 'bubble user';
  bubble.dataset.role = 'user';
  bubble.dataset.raw = text;
  const content = document.createElement('div');
  content.className = 'content';
  content.textContent = text;
  bubble.append(content);
  messages.append(bubble);
  scrollToBottom();
}

function assistantBubble(): void {
  const bubble = document.createElement('article');
  bubble.className = 'bubble assistant streaming';
  bubble.dataset.role = 'assistant';
  const content = document.createElement('div');
  content.className = 'content';
  const stream = document.createElement('span');
  stream.className = 'stream-text';
  stream.textContent = '…';
  content.append(stream);
  bubble.append(content);
  messages.append(bubble);
  streaming = bubble;
  streamingText = stream;
  scrollToBottom();
}

function lastAssistant(): HTMLElement | null {
  const all = messages.querySelectorAll<HTMLElement>('.bubble.assistant');
  return all.length > 0 ? (all[all.length - 1] ?? null) : null;
}

function appendDelta(text: string): void {
  if (!streaming || !streamingText) {
    assistantBubble();
  }
  if (streamingText && streamingText.textContent === '…') {
    streamingText.textContent = '';
  }
  streamingText?.append(document.createTextNode(text));
  scrollToBottom();
}

function finishAssistant(text: string): void {
  const bubble = streaming ?? lastAssistant();
  if (!bubble) {
    return;
  }
  bubble.classList.remove('streaming');
  bubble.dataset.raw = text;
  const content = bubble.querySelector('.content');
  if (content) {
    // renderMarkdown escapes the input before it builds any tag.
    content.innerHTML = renderMarkdown(text);
  }
  streaming = null;
  streamingText = null;
  scrollToBottom();
}

function showError(message: string): void {
  const bubble = streaming ?? lastAssistant();
  streaming = null;
  streamingText = null;
  if (bubble) {
    bubble.classList.remove('streaming');
    bubble.classList.add('failed');
  }
  const target = bubble ?? document.createElement('article');
  if (!bubble) {
    target.className = 'bubble assistant failed';
    target.dataset.role = 'assistant';
    messages.append(target);
  }
  const box = document.createElement('div');
  box.className = 'error-box';
  const text = document.createElement('p');
  text.textContent = message;
  box.append(text);
  if (lastUserText.length > 0) {
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'ghost';
    retry.textContent = 'Retry';
    retry.addEventListener('click', () => retryLast());
    box.append(retry);
  }
  target.append(box);
  scrollToBottom();
}

function retryLast(): void {
  if (busy || lastUserText.length === 0) {
    return;
  }
  lastAssistant()?.remove();
  assistantBubble();
  setBusy(true);
  setStatus('Retrying…');
  post({ type: 'send', text: lastUserText });
}

function applyState(message: Extract<ChatHostMessage, { type: 'state' }>): void {
  const known = message.models.some((option) => option.id === message.model);
  const signature = [
    message.backend,
    known ? '' : message.model,
    ...message.models.map((option) => `${option.id}\u0000${option.label}`)
  ].join('\u0001');
  if (signature !== renderedModels) {
    renderedModels = signature;
    modelSelect.replaceChildren();
    for (const option of message.models as readonly ModelOption[]) {
      const node = document.createElement('option');
      node.value = option.id;
      node.textContent = option.label;
      modelSelect.append(node);
    }
    if (message.models.length === 0) {
      const node = document.createElement('option');
      node.value = '';
      node.textContent = 'No model available';
      node.disabled = true;
      modelSelect.append(node);
    }
    if (!known && message.model.length > 0) {
      const node = document.createElement('option');
      node.value = message.model;
      node.textContent = `${message.model} (from settings)`;
      modelSelect.append(node);
    }
  }
  if (message.model.length > 0) {
    modelSelect.value = message.model;
  }
  notice.textContent = message.notice;
  if (message.backend === 'lm') {
    if (message.models.length === 0) {
      keyHint.textContent =
        'No VS Code language model is available. Install and sign in to a language model provider, ' +
        'or set ibkrHistory.chat.backend to http.';
      keyHint.classList.remove('hidden');
    } else {
      keyHint.classList.add('hidden');
    }
    return;
  }
  if (!message.hasApiKey) {
    keyHint.textContent = 'No chat API key. Run "IBKR History: Set Chat API Key".';
    keyHint.classList.remove('hidden');
  } else if (message.keySource === 'opencodeAuth') {
    keyHint.textContent = 'Using the opencode auth.json key.';
    keyHint.classList.remove('hidden');
  } else {
    keyHint.classList.add('hidden');
  }
}

function applyContext(available: boolean, context: ContextBadge | null): void {
  if (!available || !context) {
    badge.textContent = 'No dataset';
    empty.classList.remove('hidden');
    return;
  }
  badge.textContent =
    `Context: ${context.trades} trades · ${context.baseCurrency} base · ` +
    `generated ${context.generatedAt} · ~${formatTokens(context.approxTokens)} tokens`;
  empty.classList.add('hidden');
}

function send(): void {
  const text = input.value.trim();
  if (text.length === 0 || busy) {
    return;
  }
  lastUserText = text;
  input.value = '';
  userBubble(text);
  assistantBubble();
  setBusy(true);
  setStatus('Waiting for the model…');
  post({ type: 'send', text });
}

function copyTranscript(): void {
  const lines: string[] = [];
  for (const bubble of messages.querySelectorAll<HTMLElement>('.bubble')) {
    const role = bubble.dataset.role === 'user' ? 'You' : 'Assistant';
    const raw = bubble.dataset.raw ?? bubble.textContent ?? '';
    lines.push(`${role}: ${raw}`);
  }
  if (lines.length === 0) {
    setStatus('Nothing to copy yet.');
    return;
  }
  post({ type: 'copyTranscript', text: lines.join('\n\n') });
}

window.addEventListener('message', (event: MessageEvent<ChatHostMessage>) => {
  const message = event.data;
  switch (message.type) {
    case 'state':
      applyState(message);
      break;
    case 'context':
      applyContext(message.available, message.badge);
      break;
    case 'delta':
      appendDelta(message.text);
      break;
    case 'done':
      finishAssistant(message.text);
      setStatus('Done.');
      break;
    case 'error':
      showError(message.message);
      setStatus('Error. Use Retry or change the model.');
      break;
    case 'busy':
      setBusy(message.busy);
      if (!message.busy && streaming) {
        // A stop leaves a partial answer: keep the visible text, end the caret.
        const partial = streaming;
        partial.classList.remove('streaming');
        partial.dataset.raw = partial.textContent ?? '';
        streaming = null;
        streamingText = null;
      }
      break;
    case 'cleared':
      messages.replaceChildren();
      streaming = null;
      streamingText = null;
      lastUserText = '';
      setStatus('Chat cleared.');
      break;
    case 'info':
      setStatus(message.message);
      break;
    default:
      break;
  }
});

sendButton.addEventListener('click', send);
stopButton.addEventListener('click', () => {
  setStatus('Stopping…');
  post({ type: 'stop' });
});
el<HTMLButtonElement>('btn-clear').addEventListener('click', () => post({ type: 'clear' }));
el<HTMLButtonElement>('btn-copy').addEventListener('click', copyTranscript);
el<HTMLButtonElement>('btn-fetch').addEventListener('click', () => post({ type: 'fetchReport' }));
el<HTMLButtonElement>('btn-handoff').addEventListener('click', () => {
  setStatus('Writing the handoff file…');
  post({ type: 'handoff' });
});

modelSelect.addEventListener('change', () => {
  post({ type: 'setModel', model: modelSelect.value });
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    send();
  }
});

setBusy(false);
post({ type: 'ready' });
