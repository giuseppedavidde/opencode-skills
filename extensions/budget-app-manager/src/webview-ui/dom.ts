export type Child = Node | string | null | undefined | false;

export interface ElOptions {
  className?: string;
  text?: string;
  html?: string;
  title?: string;
  attrs?: Record<string, string>;
  dataset?: Record<string, string>;
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  options: ElOptions = {},
  children: Child[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.html !== undefined) node.innerHTML = options.html;
  if (options.title) node.title = options.title;
  if (options.attrs) {
    for (const [key, value] of Object.entries(options.attrs)) node.setAttribute(key, value);
  }
  if (options.dataset) {
    for (const [key, value] of Object.entries(options.dataset)) node.dataset[key] = value;
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(child));
  }
  return node;
}

export function clear(node: HTMLElement): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function fmtEur(value: number, decimals = 2): string {
  const safe = Number.isFinite(value) ? value : 0;
  return `€ ${safe.toLocaleString('it-IT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export function fmtEur0(value: number): string {
  return fmtEur(value, 0);
}

export function fmtPct(value: number, decimals = 1): string {
  const safe = Number.isFinite(value) ? value : 0;
  return `${safe.toFixed(decimals)}%`;
}

export function fmtNum(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString('it-IT') : '0';
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function inline(text: string): string {
  let value = text;
  value = value.replace(/`([^`]+)`/g, '<code>$1</code>');
  value = value.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  value = value.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  value = value.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  value = value.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
  value = value.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
  );
  return value;
}

export function markdownToHtml(markdown: string): string {
  const source = escapeHtml(String(markdown ?? ''));
  const lines = source.split(/\r?\n/);
  const out: string[] = [];
  let inCode = false;
  let codeBuffer: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let paragraph: string[] = [];

  const flushParagraph = (): void => {
    if (paragraph.length > 0) {
      out.push(`<p>${inline(paragraph.join(' '))}</p>`);
      paragraph = [];
    }
  };
  const closeList = (): void => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? '';
    const trimmed = line.trim();
    if (trimmed.startsWith('```')) {
      flushParagraph();
      closeList();
      if (inCode) {
        out.push(`<pre><code>${codeBuffer.join('\n')}</code></pre>`);
        codeBuffer = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }
    if (!trimmed) {
      flushParagraph();
      closeList();
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(6, (heading[1] ?? '#').length + 2);
      out.push(`<h${level}>${inline(heading[2] ?? '')}</h${level}>`);
      continue;
    }
    if (trimmed.startsWith('|') && i + 1 < lines.length) {
      const next = (lines[i + 1] ?? '').trim();
      if (/^\|?[\s:|-]+\|?$/.test(next) && next.includes('-')) {
        flushParagraph();
        closeList();
        const headerCells = splitRow(trimmed);
        i += 2;
        const body: string[][] = [];
        while (i < lines.length) {
          const rowLine = (lines[i] ?? '').trim();
          if (!rowLine.startsWith('|')) break;
          body.push(splitRow(rowLine));
          i += 1;
        }
        i -= 1;
        const head = headerCells.map((cell) => `<th>${inline(cell)}</th>`).join('');
        const rows = body
          .map((cells) => `<tr>${cells.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`)
          .join('');
        out.push(`<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`);
        continue;
      }
    }
    if (/^[-*+]\s+/.test(trimmed)) {
      flushParagraph();
      if (listType !== 'ul') {
        closeList();
        out.push('<ul>');
        listType = 'ul';
      }
      out.push(`<li>${inline(trimmed.replace(/^[-*+]\s+/, ''))}</li>`);
      continue;
    }
    if (/^\d+[.)]\s+/.test(trimmed)) {
      flushParagraph();
      if (listType !== 'ol') {
        closeList();
        out.push('<ol>');
        listType = 'ol';
      }
      out.push(`<li>${inline(trimmed.replace(/^\d+[.)]\s+/, ''))}</li>`);
      continue;
    }
    closeList();
    paragraph.push(trimmed);
  }
  flushParagraph();
  closeList();
  if (inCode) out.push(`<pre><code>${codeBuffer.join('\n')}</code></pre>`);
  return out.join('\n');
}

function splitRow(line: string): string[] {
  const trimmed = line.replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => cell.trim());
}

export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export function confirmThen(
  button: HTMLButtonElement,
  action: () => void,
  confirmLabel = '⚠️ Clicca di nuovo per confermare',
): void {
  if (button.dataset.armed === '1') {
    delete button.dataset.armed;
    button.textContent = button.dataset.label ?? button.textContent;
    button.classList.remove('warn');
    action();
    return;
  }
  button.dataset.label = button.textContent ?? '';
  button.dataset.armed = '1';
  button.textContent = confirmLabel;
  button.classList.add('warn');
  setTimeout(() => {
    if (button.dataset.armed !== '1') return;
    delete button.dataset.armed;
    button.textContent = button.dataset.label ?? '';
    button.classList.remove('warn');
  }, 6000);
}
