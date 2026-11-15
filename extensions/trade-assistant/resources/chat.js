(function () {
  'use strict';

  const vscode = acquireVsCodeApi();
  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('input');
  const sendEl = document.getElementById('send');
  const stopEl = document.getElementById('stop');
  const sessionsEl = document.getElementById('sessions');
  const newEl = document.getElementById('new');
  const exportEl = document.getElementById('export');
  const usageEl = document.getElementById('usage');

  let streamingEl = null;
  let streamingRaw = '';
  let lastAssistant = null;
  const traceByCallId = new Map();
  const traceCountByAssistant = new Map();

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function inline(text) {
    let out = text;
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<span class="link" title="$2">$1</span>');
    return out;
  }

  function renderProse(source) {
    const lines = escapeHtml(source).split('\n');
    const out = [];
    let listOpen = '';
    let quoteOpen = false;
    const closeList = () => {
      if (listOpen) {
        out.push('</' + listOpen + '>');
        listOpen = '';
      }
    };
    const closeQuote = () => {
      if (quoteOpen) {
        out.push('</blockquote>');
        quoteOpen = false;
      }
    };
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed === '') {
        closeList();
        closeQuote();
        continue;
      }
      const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
      if (heading) {
        closeList();
        closeQuote();
        const level = heading[1].length;
        out.push('<h' + level + '>' + inline(heading[2]) + '</h' + level + '>');
        continue;
      }
      if (/^([-*+])\s+/.test(trimmed)) {
        closeQuote();
        if (listOpen !== 'ul') {
          closeList();
          out.push('<ul>');
          listOpen = 'ul';
        }
        out.push('<li>' + inline(trimmed.replace(/^([-*+])\s+/, '')) + '</li>');
        continue;
      }
      if (/^\d+[.)]\s+/.test(trimmed)) {
        closeQuote();
        if (listOpen !== 'ol') {
          closeList();
          out.push('<ol>');
          listOpen = 'ol';
        }
        out.push('<li>' + inline(trimmed.replace(/^\d+[.)]\s+/, '')) + '</li>');
        continue;
      }
      if (trimmed.indexOf('&gt;') === 0) {
        closeList();
        if (!quoteOpen) {
          out.push('<blockquote>');
          quoteOpen = true;
        }
        out.push('<p>' + inline(trimmed.replace(/^&gt;\s?/, '')) + '</p>');
        continue;
      }
      if (/^-{3,}$/.test(trimmed)) {
        closeList();
        closeQuote();
        out.push('<hr>');
        continue;
      }
      closeList();
      closeQuote();
      out.push('<p>' + inline(trimmed) + '</p>');
    }
    closeList();
    closeQuote();
    return out.join('');
  }

  function renderMarkdown(source) {
    const chunks = String(source === undefined || source === null ? '' : source).split('```');
    let html = '';
    for (let index = 0; index < chunks.length; index += 1) {
      if (index % 2 === 1) {
        const block = chunks[index];
        const newline = block.indexOf('\n');
        const language = newline >= 0 ? block.slice(0, newline).trim() : '';
        const code = newline >= 0 ? block.slice(newline + 1) : block;
        html +=
          '<pre class="code"><code data-lang="' +
          escapeHtml(language) +
          '">' +
          escapeHtml(code.replace(/\n$/, '')) +
          '</code></pre>';
        continue;
      }
      html += renderProse(chunks[index]);
    }
    return html;
  }

  function nearBottom() {
    return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 60;
  }

  function scrollToBottom(force) {
    if (force || nearBottom()) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  function makeBubble(kind) {
    const article = document.createElement('article');
    article.className = 'msg msg-' + kind;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    article.appendChild(bubble);
    messagesEl.appendChild(article);
    return { article: article, bubble: bubble };
  }

  function appendUser(text) {
    const node = makeBubble('user');
    node.bubble.innerHTML = renderMarkdown(text);
    lastAssistant = null;
    streamingEl = null;
    streamingRaw = '';
    scrollToBottom(true);
  }

  function appendError(text) {
    const node = makeBubble('error');
    node.bubble.textContent = text;
    scrollToBottom(true);
  }

  function ensureAssistantArticle() {
    if (lastAssistant) {
      return lastAssistant;
    }
    const node = makeBubble('assistant');
    lastAssistant = node.article;
    return lastAssistant;
  }

  function appendAssistant(text) {
    let article;
    let bubble;
    if (streamingEl) {
      article = streamingEl.article;
      bubble = streamingEl.bubble;
    } else {
      const node = makeBubble('assistant');
      article = node.article;
      bubble = node.bubble;
    }
    bubble.innerHTML = renderMarkdown(text);
    lastAssistant = article;
    streamingEl = null;
    streamingRaw = '';
    scrollToBottom(false);
    return article;
  }

  function onDelta(chunk) {
    if (!streamingEl) {
      const node = makeBubble('assistant');
      streamingEl = node;
      streamingRaw = '';
      lastAssistant = node.article;
    }
    streamingRaw += chunk;
    streamingEl.bubble.innerHTML = renderMarkdown(streamingRaw);
    scrollToBottom(true);
  }

  function traceContainer() {
    const article = ensureAssistantArticle();
    let trace = article.querySelector('details.trace');
    if (!trace) {
      trace = document.createElement('details');
      trace.className = 'trace';
      const summary = document.createElement('summary');
      summary.textContent = 'Tool calls';
      trace.appendChild(summary);
      const body = document.createElement('div');
      body.className = 'trace-body';
      trace.appendChild(body);
      article.appendChild(trace);
    }
    return trace;
  }

  function countTrace(node) {
    const count = (traceCountByAssistant.get(node) || 0) + 1;
    traceCountByAssistant.set(node, count);
    const summary = node.querySelector('details.trace > summary');
    if (summary) {
      summary.textContent = count === 1 ? '1 tool call' : count + ' tool calls';
    }
  }

  function appendToolCall(record) {
    const trace = traceContainer();
    countTrace(ensureAssistantArticle());
    const body = trace.querySelector('.trace-body');
    const entry = document.createElement('div');
    entry.className = 'trace-entry';
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = 'call: ' + (record.name || 'unknown');
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(record.args || {}, null, 2);
    entry.appendChild(label);
    entry.appendChild(pre);
    body.appendChild(entry);
    if (record.callId) {
      traceByCallId.set(record.callId, entry);
    }
    scrollToBottom(false);
  }

  function appendToolResult(record) {
    const entry = record.callId ? traceByCallId.get(record.callId) : undefined;
    const target = entry || traceContainer().querySelector('.trace-body');
    const row = document.createElement('div');
    row.className = 'trace-entry' + (record.ok === false ? ' bad' : '');
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = (record.ok === false ? 'error: ' : 'result: ') + (record.name || 'unknown');
    const pre = document.createElement('pre');
    pre.textContent = record.text || '';
    row.appendChild(label);
    row.appendChild(pre);
    target.appendChild(row);
    scrollToBottom(false);
  }

  function renderRecord(record) {
    if (!record || typeof record !== 'object') {
      return;
    }
    if (record.kind === 'user') {
      appendUser(record.text || '');
      return;
    }
    if (record.kind === 'assistant') {
      appendAssistant(record.text || '');
      return;
    }
    if (record.kind === 'tool_call') {
      appendToolCall(record);
      return;
    }
    if (record.kind === 'tool_result') {
      appendToolResult(record);
      return;
    }
    if (record.kind === 'error') {
      appendError(record.text || 'Unknown error');
    }
  }

  function reset() {
    messagesEl.innerHTML = '';
    traceByCallId.clear();
    traceCountByAssistant.clear();
    streamingEl = null;
    streamingRaw = '';
    lastAssistant = null;
  }

  function renderSessions(sessions, activeId) {
    sessionsEl.innerHTML = '';
    const seen = new Set();
    for (const session of sessions || []) {
      if (!session || !session.sessionId || seen.has(session.sessionId)) {
        continue;
      }
      seen.add(session.sessionId);
      const option = document.createElement('option');
      option.value = session.sessionId;
      const when = (session.updatedAt || '').replace('T', ' ').slice(0, 16);
      option.textContent = (session.title || 'Untitled') + (when ? ' · ' + when : '');
      if (session.sessionId === activeId) {
        option.selected = true;
      }
      sessionsEl.appendChild(option);
    }
    if (!seen.has(activeId)) {
      const option = document.createElement('option');
      option.value = activeId || '';
      option.textContent = 'New chat';
      option.selected = true;
      sessionsEl.appendChild(option);
    }
  }

  function renderUsage(usage, summary) {
    const parts = [];
    if (usage && usage.model) {
      parts.push(usage.model);
    }
    if (summary && typeof summary.messageCount === 'number') {
      parts.push(summary.messageCount + ' msg');
    }
    if (usage && typeof usage.toolCalls === 'number') {
      parts.push(usage.toolCalls + ' tools');
    }
    if (usage && typeof usage.approximateTokens === 'number') {
      parts.push('~' + usage.approximateTokens + ' tok');
    }
    usageEl.textContent = parts.join(' · ');
  }

  function setBusy(busy) {
    sendEl.disabled = busy;
    stopEl.disabled = !busy;
    inputEl.disabled = busy;
  }

  function applyState(message) {
    reset();
    const records = Array.isArray(message.records) ? message.records : [];
    if (records.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Start with a ticker, a position or a strategy question.';
      messagesEl.appendChild(empty);
    } else {
      for (const record of records) {
        renderRecord(record);
      }
    }
    renderSessions(message.sessions, message.sessionId);
    renderUsage(message.usage, message.summary);
    setBusy(Boolean(message.busy));
    if (message.error) {
      usageEl.textContent = message.error;
    }
    scrollToBottom(true);
  }

  function send() {
    const text = inputEl.value;
    if (!text || text.trim() === '') {
      return;
    }
    inputEl.value = '';
    vscode.postMessage({ type: 'send', text: text });
  }

  sendEl.addEventListener('click', send);
  stopEl.addEventListener('click', function () {
    vscode.postMessage({ type: 'stop' });
  });
  newEl.addEventListener('click', function () {
    vscode.postMessage({ type: 'newSession' });
  });
  exportEl.addEventListener('click', function () {
    vscode.postMessage({ type: 'export' });
  });
  sessionsEl.addEventListener('change', function () {
    vscode.postMessage({ type: 'selectSession', sessionId: sessionsEl.value });
  });
  inputEl.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  });

  window.addEventListener('message', function (event) {
    const message = event.data;
    if (!message || typeof message.type !== 'string') {
      return;
    }
    if (message.type === 'state') {
      applyState(message);
      return;
    }
    if (message.type === 'delta') {
      onDelta(message.text || '');
      return;
    }
    if (message.type === 'append') {
      renderRecord(message.record);
      if (message.record && message.record.kind === 'assistant') {
        streamingEl = null;
        streamingRaw = '';
      }
      return;
    }
    if (message.type === 'error') {
      appendError(message.message || 'Unknown error');
      return;
    }
    if (message.type === 'busy') {
      setBusy(Boolean(message.busy));
    }
  });

  vscode.postMessage({ type: 'ready' });
})();
