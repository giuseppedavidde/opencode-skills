import type { ChatMessage } from '../types';
import { el, markdownToHtml, clear } from './dom';
import type { UiContext } from './context';

const KEY_REQUIRED = new Set(['gemini', 'groq', 'openrouter', 'puter']);

export function renderChat(root: HTMLElement, ctx: UiContext): void {
  clear(root);
  const { state } = ctx;

  root.append(
    el('div', { className: 'page-head' }, [
      el('div', {}, [
        el('h1', { text: '💬 Financial Assistant' }),
        el('p', { className: 'muted', text: 'Chiedi al tuo assistente personale informazioni sul tuo budget.' }),
      ]),
    ]),
  );

  const configured =
    !KEY_REQUIRED.has(state.ai.provider) || state.ai.keySet;
  if (!configured) {
    root.append(
      el('div', { className: 'alert warn' }, [
        el('strong', { text: '⚠️ AI non configurata. ' }),
        el('span', { text: 'Inserisci una API key nella sidebar (AI Configuration) per parlare con l’assistente.' }),
      ]),
    );
  }

  const chatCard = el('section', { className: 'card chat-card' });
  const messagesBox = el('div', { className: 'chat-messages', attrs: { id: 'chat-messages' } });
  const allMessages: ChatMessage[] = [...state.chat];
  if (state.chatStreaming) {
    allMessages.push({ role: 'assistant', content: state.chatStreaming.text });
  }
  if (allMessages.length === 0) {
    messagesBox.append(
      el('div', { className: 'chat-empty' }, [
        el('div', { className: 'drop-icon', text: '🤖' }),
        el('p', { text: 'Nessun messaggio. Prova: "Analizza i miei ultimi 6 mesi e suggerisci dove tagliare le spese."' }),
      ]),
    );
  }
  allMessages.forEach((message, index) => {
    const isStreaming =
      state.chatStreaming && index === allMessages.length - 1 && message.role === 'assistant';
    const bubble = el('div', { className: `chat-message ${message.role}` }, [
      el('div', { className: 'chat-role', text: message.role === 'user' ? 'Tu' : 'Assistant' }),
      el('div', {
        className: 'markdown chat-body',
        html: markdownToHtml(message.content || (isStreaming ? '…' : '')),
        attrs: isStreaming ? { id: 'chat-stream' } : {},
      }),
    ]);
    messagesBox.append(bubble);
  });

  const input = el('textarea', {
    className: 'control chat-input',
    attrs: { rows: '3', placeholder: 'Chiedi qualcosa sui tuoi numeri…', id: 'chat-input' },
  }) as HTMLTextAreaElement;
  const send = el('button', {
    className: 'btn primary',
    text: 'Invia',
    attrs: { type: 'button', ...(state.chatStreaming ? { disabled: 'true' } : {}) },
  });
  const sendMessage = (): void => {
    const text = input.value.trim();
    if (!text) {
      ctx.toast('warn', 'Scrivi una domanda.');
      return;
    }
    if (state.chatStreaming) {
      ctx.toast('warn', 'Attendi la risposta precedente.');
      return;
    }
    const requestId = `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    state.chat.push({ role: 'user', content: text });
    state.chatStreaming = { requestId, text: '' };
    ctx.post({ type: 'chatSend', requestId, text });
    ctx.renderMain();
    const nextInput = document.getElementById('chat-input') as HTMLTextAreaElement | null;
    nextInput?.focus();
  };
  send.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  const clearButton = el('button', { className: 'btn ghost', text: '🧹 Nuova chat', attrs: { type: 'button' } });
  clearButton.addEventListener('click', () => {
    state.chat = [];
    state.chatStreaming = null;
    ctx.post({ type: 'chatClear' });
    ctx.renderMain();
  });

  chatCard.append(
    messagesBox,
    el('div', { className: 'chat-compose' }, [input, send, clearButton]),
  );
  root.append(chatCard);

  requestAnimationFrame(() => {
    const box = document.getElementById('chat-messages');
    if (box) box.scrollTop = box.scrollHeight;
    const nextInput = document.getElementById('chat-input') as HTMLTextAreaElement | null;
    nextInput?.focus();
  });
}

export function updateChatStreaming(text: string): void {
  const node = document.getElementById('chat-stream');
  if (node) {
    node.innerHTML = markdownToHtml(text || '…');
    const box = document.getElementById('chat-messages');
    if (box) box.scrollTop = box.scrollHeight;
  }
}
