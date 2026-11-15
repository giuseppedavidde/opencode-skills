import * as fs from 'node:fs';
import * as path from 'node:path';

export type TranscriptKind = 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'error' | 'session_meta';

export interface TranscriptRecord {
  id: string;
  ts: string;
  kind: TranscriptKind;
  sessionId: string;
  text?: string;
  name?: string;
  callId?: string;
  args?: unknown;
  ok?: boolean;
  meta?: Record<string, unknown>;
}

export interface SessionSummary {
  sessionId: string;
  title: string;
  messageCount: number;
  toolCallCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface TranscriptFs {
  ensureDir(dir: string): void;
  append(file: string, text: string): void;
  read(file: string): string;
  exists(file: string): boolean;
  listFiles(dir: string): string[];
  remove(file: string): void;
}

const SESSION_FILE_PATTERN = /^[A-Za-z0-9_-]+\.jsonl$/;
const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]+$/;
const TITLE_LIMIT = 80;

export function sanitizeSessionId(raw: string): string {
  const trimmed = raw.trim();
  if (SESSION_ID_PATTERN.test(trimmed)) {
    return trimmed;
  }
  return trimmed.replace(/[^A-Za-z0-9_-]/g, '');
}

export function newSessionId(now: Date = new Date(), random: () => number = Math.random): string {
  const pad = (value: number, width = 2): string => String(value).padStart(width, '0');
  const stamp = [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
  ].join('') + '-' + [pad(now.getHours()), pad(now.getMinutes()), pad(now.getSeconds())].join('');
  const suffix = Math.floor(random() * 0x10000)
    .toString(16)
    .padStart(4, '0');
  return `${stamp}-${suffix}`;
}

export function sessionFilePath(dir: string, sessionId: string): string {
  return path.join(dir, `${sanitizeSessionId(sessionId)}.jsonl`);
}

export function createRecord(
  kind: TranscriptKind,
  sessionId: string,
  payload: Omit<Partial<TranscriptRecord>, 'kind' | 'sessionId'> = {},
  now: Date = new Date(),
  random: () => number = Math.random
): TranscriptRecord {
  const suffix = Math.floor(random() * 0x1000000)
    .toString(36)
    .padStart(5, '0');
  return {
    id: `${now.getTime().toString(36)}-${suffix}`,
    ts: now.toISOString(),
    kind,
    sessionId: sanitizeSessionId(sessionId),
    ...payload,
  };
}

export function serializeRecord(record: TranscriptRecord): string {
  return `${JSON.stringify(record)}\n`;
}

export function parseTranscript(content: string): TranscriptRecord[] {
  const records: TranscriptRecord[] = [];
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      continue;
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      continue;
    }
    const candidate = parsed as Partial<TranscriptRecord>;
    if (typeof candidate.kind !== 'string' || typeof candidate.sessionId !== 'string') {
      continue;
    }
    records.push({
      id: typeof candidate.id === 'string' ? candidate.id : `${records.length}`,
      ts: typeof candidate.ts === 'string' ? candidate.ts : '',
      kind: candidate.kind as TranscriptKind,
      sessionId: candidate.sessionId,
      ...(typeof candidate.text === 'string' ? { text: candidate.text } : {}),
      ...(typeof candidate.name === 'string' ? { name: candidate.name } : {}),
      ...(typeof candidate.callId === 'string' ? { callId: candidate.callId } : {}),
      ...(candidate.args === undefined ? {} : { args: candidate.args }),
      ...(typeof candidate.ok === 'boolean' ? { ok: candidate.ok } : {}),
      ...(candidate.meta && typeof candidate.meta === 'object' ? { meta: candidate.meta as Record<string, unknown> } : {}),
    });
  }
  return records;
}

export function appendRecord(transcriptFs: TranscriptFs, file: string, record: TranscriptRecord): void {
  transcriptFs.ensureDir(path.dirname(file));
  transcriptFs.append(file, serializeRecord(record));
}

export function readSession(transcriptFs: TranscriptFs, file: string): TranscriptRecord[] {
  if (!transcriptFs.exists(file)) {
    return [];
  }
  try {
    return parseTranscript(transcriptFs.read(file));
  } catch {
    return [];
  }
}

export function listSessions(transcriptFs: TranscriptFs, dir: string): SessionSummary[] {
  let files: string[];
  try {
    files = transcriptFs.listFiles(dir);
  } catch {
    return [];
  }
  const summaries: SessionSummary[] = [];
  for (const name of files) {
    if (!SESSION_FILE_PATTERN.test(name)) {
      continue;
    }
    const file = path.join(dir, name);
    const records = readSession(transcriptFs, file);
    if (records.length === 0) {
      continue;
    }
    summaries.push(summaryOf(records, name.replace(/\.jsonl$/, '')));
  }
  return summaries.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

export function deleteSession(transcriptFs: TranscriptFs, file: string): void {
  if (!transcriptFs.exists(file)) {
    return;
  }
  transcriptFs.remove(file);
}

export function summaryOf(records: TranscriptRecord[], fallbackSessionId = ''): SessionSummary {
  let sessionId = fallbackSessionId;
  let title = 'Untitled chat';
  let messageCount = 0;
  let toolCallCount = 0;
  let createdAt = '';
  let updatedAt = '';
  for (const record of records) {
    if (!sessionId && record.sessionId) {
      sessionId = record.sessionId;
    }
    if (!createdAt && record.ts) {
      createdAt = record.ts;
    }
    if (record.ts) {
      updatedAt = record.ts;
    }
    if (record.kind === 'user' || record.kind === 'assistant') {
      messageCount += 1;
    }
    if (record.kind === 'tool_call') {
      toolCallCount += 1;
    }
    if (record.kind === 'user' && title === 'Untitled chat') {
      const line = (record.text ?? '').split('\n')[0].trim();
      if (line.length > 0) {
        title = line.length > TITLE_LIMIT ? `${line.slice(0, TITLE_LIMIT - 1)}…` : line;
      }
    }
  }
  return { sessionId, title, messageCount, toolCallCount, createdAt, updatedAt };
}

export function exportSession(records: TranscriptRecord[], title = ''): string {
  const summary = summaryOf(records);
  const lines: string[] = [];
  lines.push(`# ${title.trim() || summary.title}`);
  lines.push('');
  lines.push(`- Session: \`${summary.sessionId}\``);
  lines.push(`- Messages: ${summary.messageCount}`);
  lines.push(`- Tool calls: ${summary.toolCallCount}`);
  if (summary.createdAt) {
    lines.push(`- Started: ${summary.createdAt}`);
  }
  if (summary.updatedAt) {
    lines.push(`- Updated: ${summary.updatedAt}`);
  }
  lines.push('');
  for (const record of records) {
    if (record.kind === 'session_meta') {
      continue;
    }
    const body = record.text ?? '';
    if (record.kind === 'user') {
      lines.push('## User', '', body, '');
      continue;
    }
    if (record.kind === 'assistant') {
      lines.push('## Assistant', '', body, '');
      continue;
    }
    if (record.kind === 'error') {
      lines.push('## Error', '', '```text', body, '```', '');
      continue;
    }
    if (record.kind === 'tool_call') {
      lines.push(`### Tool call: \`${record.name ?? 'unknown'}\``, '', '```json', JSON.stringify(record.args ?? {}, null, 2), '```', '');
      continue;
    }
    lines.push(`### Tool result: \`${record.name ?? 'unknown'}\` (${record.ok === false ? 'error' : 'ok'})`, '', '```text', truncate(body, 4000), '```', '');
  }
  return lines.join('\n');
}

export function createNodeTranscriptFs(): TranscriptFs {
  return {
    ensureDir: (dir) => {
      fs.mkdirSync(dir, { recursive: true });
    },
    append: (file, text) => {
      fs.appendFileSync(file, text, 'utf8');
    },
    read: (file) => fs.readFileSync(file, 'utf8'),
    exists: (file) => fs.existsSync(file),
    listFiles: (dir) => (fs.existsSync(dir) ? fs.readdirSync(dir) : []),
    remove: (file) => {
      fs.rmSync(file, { force: true });
    },
  };
}

function truncate(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}\n… truncated` : text;
}
