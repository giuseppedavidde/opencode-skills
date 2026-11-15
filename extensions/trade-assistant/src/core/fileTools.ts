import * as fs from 'node:fs';
import * as path from 'node:path';
import type { ToolSpec } from './opencodeGo';

export const FILE_ROOTS_SETTING = 'tradeAssistant.fileAccess.roots';
export const READ_FILE_LINE_CAP = 400;
export const READ_FILE_BYTE_CAP = 40 * 1024;
export const LIST_DIR_CAP = 400;
export const FIND_FILES_CAP = 200;
export const SEARCH_TEXT_CAP = 100;

const IGNORED_DIRECTORIES = new Set(['node_modules', '.git']);
const MAX_WALK_ENTRIES = 200_000;
const MAX_WALK_DEPTH = 12;
const MAX_SEARCH_BYTES = 1024 * 1024;
const BINARY_SNIFF_BYTES = 8192;

export interface FileToolContext {
  roots: string[];
  homeDir: string;
  cwd?: string;
}

export interface FileToolResult {
  isError: boolean;
  text: string;
}

export const FILE_TOOL_SPECS: ToolSpec[] = [
  {
    name: 'read_file',
    description:
      'Read a text file from the PC. Returns numbered lines. Use absolute paths or paths relative to the allowed roots.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'File path. Supports ~ and relative paths.' },
        startLine: { type: 'number', description: 'First line to return, 1-based.' },
        endLine: { type: 'number', description: 'Last line to return, inclusive.' },
      },
      required: ['path'],
    },
  },
  {
    name: 'list_dir',
    description: 'List a directory on the PC. Returns name, type and size for every entry.',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: 'Directory path. Supports ~.' } },
      required: ['path'],
    },
  },
  {
    name: 'find_files',
    description: 'Find files by a glob pattern (* and **) under a directory.',
    inputSchema: {
      type: 'object',
      properties: {
        pattern: { type: 'string', description: 'Glob pattern, for example "**/*.md" or "*.json".' },
        path: { type: 'string', description: 'Directory to search. Defaults to the first allowed root.' },
      },
      required: ['pattern'],
    },
  },
  {
    name: 'search_text',
    description: 'Search a regular expression in text files. Returns file:line matches.',
    inputSchema: {
      type: 'object',
      properties: {
        pattern: { type: 'string', description: 'JavaScript regular expression.' },
        path: { type: 'string', description: 'Directory to search. Defaults to the first allowed root.' },
        glob: { type: 'string', description: 'Optional file glob, for example "**/*.ts".' },
      },
      required: ['pattern'],
    },
  },
];

export const FILE_TOOL_NAMES = new Set(FILE_TOOL_SPECS.map((spec) => spec.name));

export function expandPath(input: string, bases: string[], homeDir: string): string {
  const raw = (input ?? '').trim();
  if (raw.length === 0) {
    return path.resolve(bases[0] ?? homeDir);
  }
  const separator = path.sep;
  let expanded = raw;
  if (raw === '~') {
    expanded = homeDir;
  } else if (raw.startsWith(`~${separator}`) || raw.startsWith('~/')) {
    expanded = path.join(homeDir, raw.slice(2));
  }
  if (path.isAbsolute(expanded)) {
    return path.resolve(expanded);
  }
  const candidates = bases.map((base) => path.resolve(base, expanded));
  for (const candidate of candidates) {
    if (exists(candidate)) {
      return candidate;
    }
  }
  return candidates[0] ?? path.resolve(expanded);
}

export function realPathSafe(target: string): string {
  const resolved = path.resolve(target);
  try {
    return fs.realpathSync.native(resolved);
  } catch {
    // the path does not exist: resolve the deepest existing ancestor instead
  }
  let current = resolved;
  const tail: string[] = [];
  for (;;) {
    const parent = path.dirname(current);
    if (parent === current) {
      return resolved;
    }
    tail.unshift(path.basename(current));
    current = parent;
    try {
      return path.join(fs.realpathSync.native(current), ...tail);
    } catch {
      continue;
    }
  }
}

export function isWithin(candidate: string, roots: string[]): boolean {
  const target = normalizeForCompare(candidate);
  for (const root of roots) {
    const base = normalizeForCompare(root);
    if (base.length === 0) {
      continue;
    }
    if (target === base) {
      return true;
    }
    const prefix = base.endsWith(path.sep) ? base : `${base}${path.sep}`;
    if (target.startsWith(prefix)) {
      return true;
    }
  }
  return false;
}

export function isBlockedPath(target: string): boolean {
  const normalized = realPathSafe(target);
  const base = path.basename(normalized);
  const segments = normalized.split(path.sep);
  if (base === 'auth.json' || base === '.netrc') {
    return true;
  }
  if (base.toLowerCase().endsWith('.pem')) {
    return true;
  }
  if (base.toLowerCase().startsWith('credentials')) {
    return true;
  }
  if (base.startsWith('id_') && segments.includes('.ssh')) {
    return true;
  }
  return false;
}

export function globToRegExp(pattern: string): RegExp {
  const normalized = pattern.replace(/\\/g, '/').trim();
  const anchored = normalized.includes('/') ? normalized : `**/${normalized}`;
  let source = '';
  for (let index = 0; index < anchored.length; index += 1) {
    const char = anchored.charAt(index);
    if (char === '*') {
      if (anchored.charAt(index + 1) === '*') {
        index += 1;
        if (anchored.charAt(index + 1) === '/') {
          index += 1;
          source += '(?:.*/)?';
        } else {
          source += '.*';
        }
      } else {
        source += '[^/]*';
      }
      continue;
    }
    if (char === '?') {
      source += '[^/]';
      continue;
    }
    source += char.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${source}$`, 'i');
}

export class FileToolService {
  constructor(private readonly context: () => FileToolContext) {}

  get specs(): ToolSpec[] {
    return FILE_TOOL_SPECS;
  }

  async call(name: string, args: Record<string, unknown>): Promise<FileToolResult> {
    if (name === 'read_file') {
      return this.readFile(args);
    }
    if (name === 'list_dir') {
      return this.listDir(args);
    }
    if (name === 'find_files') {
      return this.findFiles(args);
    }
    if (name === 'search_text') {
      return this.searchText(args);
    }
    return { isError: true, text: `Unknown file tool "${name}".` };
  }

  private readFile(args: Record<string, unknown>): FileToolResult {
    const resolved = this.resolve(args.path);
    if ('refusal' in resolved) {
      return { isError: true, text: resolved.refusal };
    }
    const target = resolved.path;
    let stats: fs.Stats;
    try {
      stats = fs.statSync(target);
    } catch (error) {
      return { isError: true, text: `Cannot read "${target}": ${messageOf(error)}` };
    }
    if (stats.isDirectory()) {
      return { isError: true, text: `"${target}" is a directory. Use list_dir instead.` };
    }
    if (!stats.isFile()) {
      return { isError: true, text: `"${target}" is not a regular file.` };
    }
    let buffer: Buffer;
    try {
      buffer = fs.readFileSync(target);
    } catch (error) {
      return { isError: true, text: `Cannot read "${target}": ${messageOf(error)}` };
    }
    if (looksBinary(buffer)) {
      return { isError: true, text: `"${target}" looks like a binary file. read_file returns text only.` };
    }
    const allLines = buffer.toString('utf8').split('\n');
    const startLine = clampLine(args.startLine, 1);
    const requestedEnd = args.endLine === undefined ? allLines.length : clampLine(args.endLine, allLines.length);
    const endLine = Math.max(startLine, Math.min(requestedEnd, allLines.length));
    const lines: string[] = [];
    let bytes = 0;
    let stoppedByBytes = false;
    for (let lineNumber = startLine; lineNumber <= endLine; lineNumber += 1) {
      if (lines.length >= READ_FILE_LINE_CAP) {
        break;
      }
      const line = allLines[lineNumber - 1] ?? '';
      bytes += line.length + 1;
      if (bytes > READ_FILE_BYTE_CAP) {
        stoppedByBytes = true;
        break;
      }
      lines.push(`${lineNumber}: ${line}`);
    }
    const total = allLines.length;
    const notes: string[] = [`${target} (${total} lines, ${stats.size} bytes)`];
    if (startLine > 1 || endLine < total) {
      notes[0] += ` - showing lines ${startLine}-${Math.max(startLine, endLine)}`;
    }
    if (lines.length >= READ_FILE_LINE_CAP && endLine - startLine + 1 > READ_FILE_LINE_CAP) {
      notes.push(`… stopped at the ${READ_FILE_LINE_CAP}-line cap. Use startLine to read further.`);
    }
    if (stoppedByBytes) {
      notes.push(`… stopped at the ${READ_FILE_BYTE_CAP}-byte cap. Use startLine to read further.`);
    }
    return { isError: false, text: `${notes.join('\n')}\n${lines.join('\n')}` };
  }

  private listDir(args: Record<string, unknown>): FileToolResult {
    const resolved = this.resolve(args.path);
    if ('refusal' in resolved) {
      return { isError: true, text: resolved.refusal };
    }
    const target = resolved.path;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(target, { withFileTypes: true });
    } catch (error) {
      return { isError: true, text: `Cannot list "${target}": ${messageOf(error)}` };
    }
    const rows: Array<{ name: string; line: string; isDirectory: boolean }> = [];
    for (const entry of entries) {
      const full = path.join(target, entry.name);
      const isDirectory = entry.isDirectory();
      let size = 0;
      try {
        size = entry.isFile() ? fs.statSync(full).size : 0;
      } catch {
        size = 0;
      }
      const type = isDirectory ? 'dir' : entry.isFile() ? 'file' : 'link';
      const suffix = isDirectory ? '' : ` (${size} bytes)`;
      rows.push({ name: entry.name, line: `${type}\t${entry.name}${suffix}`, isDirectory });
    }
    rows.sort((left, right) => {
      if (left.isDirectory !== right.isDirectory) {
        return left.isDirectory ? -1 : 1;
      }
      return left.name.localeCompare(right.name);
    });
    const shown = rows.slice(0, LIST_DIR_CAP);
    const lines = [target, ...shown.map((row) => row.line)];
    if (rows.length > shown.length) {
      lines.push(`… ${rows.length - shown.length} more entries not shown.`);
    }
    return { isError: false, text: lines.join('\n') };
  }

  private findFiles(args: Record<string, unknown>): FileToolResult {
    const pattern = readString(args.pattern);
    if (pattern.length === 0) {
      return { isError: true, text: 'find_files needs a "pattern" argument.' };
    }
    const context = this.context();
    const start = readString(args.path);
    const root = start.length > 0 ? this.resolve(start) : this.allowedRoot();
    if ('refusal' in root) {
      return { isError: true, text: root.refusal };
    }
    let expression: RegExp;
    try {
      expression = globToRegExp(pattern);
    } catch (error) {
      return { isError: true, text: `Invalid glob "${pattern}": ${messageOf(error)}` };
    }
    const matches: string[] = [];
    const walked = collectFiles(root.path);
    for (const file of walked.files) {
      const relative = path.relative(root.path, file).split(path.sep).join('/');
      if (expression.test(relative)) {
        matches.push(file);
        if (matches.length >= FIND_FILES_CAP) {
          break;
        }
      }
    }
    if (matches.length === 0) {
      return { isError: false, text: `No file matches "${pattern}" under ${root.path}.` };
    }
    const lines = matches.map((file) => file);
    if (matches.length >= FIND_FILES_CAP) {
      lines.push(`… stopped at the ${FIND_FILES_CAP}-match cap.`);
    } else if (walked.truncated) {
      lines.push(`… the directory walk reached its entry cap, so more files may match.`);
    }
    return { isError: false, text: lines.join('\n') };
  }

  private searchText(args: Record<string, unknown>): FileToolResult {
    const pattern = readString(args.pattern);
    if (pattern.length === 0) {
      return { isError: true, text: 'search_text needs a "pattern" argument.' };
    }
    let expression: RegExp;
    try {
      expression = new RegExp(pattern);
    } catch {
      expression = new RegExp(escapeRegExp(pattern));
    }
    const glob = readString(args.glob);
    let filter: RegExp | null = null;
    if (glob.length > 0) {
      try {
        filter = globToRegExp(glob);
      } catch (error) {
        return { isError: true, text: `Invalid glob "${glob}": ${messageOf(error)}` };
      }
    }
    const start = readString(args.path);
    const root = start.length > 0 ? this.resolve(start) : this.allowedRoot();
    if ('refusal' in root) {
      return { isError: true, text: root.refusal };
    }
    const matches: string[] = [];
    const walked = collectFiles(root.path);
    for (const file of walked.files) {
      if (isBlockedPath(file)) {
        continue;
      }
      const relative = path.relative(root.path, file).split(path.sep).join('/');
      if (filter && !filter.test(relative)) {
        continue;
      }
      let stats: fs.Stats;
      try {
        stats = fs.statSync(file);
      } catch {
        continue;
      }
      if (!stats.isFile() || stats.size > MAX_SEARCH_BYTES) {
        continue;
      }
      let content: string;
      try {
        content = fs.readFileSync(file, 'utf8');
      } catch {
        continue;
      }
      if (content.includes('\u0000')) {
        continue;
      }
      const rows = content.split('\n');
      for (let index = 0; index < rows.length; index += 1) {
        const row = rows[index];
        expression.lastIndex = 0;
        if (!expression.test(row)) {
          continue;
        }
        matches.push(`${file}:${index + 1}: ${row.trim().slice(0, 200)}`);
        if (matches.length >= SEARCH_TEXT_CAP) {
          break;
        }
      }
      if (matches.length >= SEARCH_TEXT_CAP) {
        break;
      }
    }
    if (matches.length === 0) {
      return { isError: false, text: `No match for /${pattern}/ under ${root.path}.` };
    }
    if (matches.length >= SEARCH_TEXT_CAP) {
      matches.push(`… stopped at the ${SEARCH_TEXT_CAP}-match cap.`);
    } else if (walked.truncated) {
      matches.push('… the directory walk reached its entry cap, so more matches may exist.');
    }
    return { isError: false, text: matches.join('\n') };
  }

  private allowedRoot(): { path: string } | { refusal: string } {
    const roots = this.context().roots;
    const first = roots[0];
    if (!first) {
      return {
        refusal: `No allowed root is configured. Add a folder to the setting "${FILE_ROOTS_SETTING}".`,
      };
    }
    return { path: realPathSafe(first) };
  }

  private resolve(input: unknown): { path: string } | { refusal: string } {
    const context = this.context();
    const raw = readString(input);
    if (raw.length === 0) {
      return { refusal: 'A "path" argument is required.' };
    }
    const bases = [...context.roots, context.cwd ?? process.cwd(), context.homeDir];
    const candidate = expandPath(raw, bases, context.homeDir);
    const resolved = realPathSafe(candidate);
    const roots = context.roots.map((root) => realPathSafe(root));
    if (roots.length === 0) {
      return {
        refusal: `No allowed root is configured. Add a folder to the setting "${FILE_ROOTS_SETTING}".`,
      };
    }
    if (!isWithin(resolved, roots)) {
      return {
        refusal: `Path "${resolved}" is outside the allowed roots (${roots.join(', ')}). Add it to the setting "${FILE_ROOTS_SETTING}" to allow access.`,
      };
    }
    if (isBlockedPath(resolved)) {
      return {
        refusal: `Reading "${resolved}" is blocked: it matches a protected pattern (.ssh/id_*, auth.json, .netrc, *.pem, credentials*, .aws/credentials). Trade Assistant never sends credentials to a model.`,
      };
    }
    return { path: resolved };
  }
}

interface WalkResult {
  files: string[];
  truncated: boolean;
}

export function collectFiles(start: string, entryCap = MAX_WALK_ENTRIES): WalkResult {
  const files: string[] = [];
  const queue: Array<{ directory: string; depth: number }> = [{ directory: start, depth: 0 }];
  const visitedDirs = new Set<string>();
  let entries = 0;
  let truncated = false;
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      break;
    }
    const realDir = realPathSafe(current.directory);
    if (visitedDirs.has(realDir)) {
      continue;
    }
    visitedDirs.add(realDir);
    let listing: fs.Dirent[];
    try {
      listing = fs.readdirSync(current.directory, { withFileTypes: true });
    } catch {
      continue;
    }
    listing.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of listing) {
      entries += 1;
      if (entries > entryCap) {
        return { files, truncated: true };
      }
      const full = path.join(current.directory, entry.name);
      let isDirectory = entry.isDirectory();
      let isFile = entry.isFile();
      if (entry.isSymbolicLink()) {
        try {
          const stats = fs.statSync(full);
          isDirectory = stats.isDirectory();
          isFile = stats.isFile();
        } catch {
          isFile = false;
        }
      }
      if (isDirectory) {
        if (IGNORED_DIRECTORIES.has(entry.name) || current.depth >= MAX_WALK_DEPTH) {
          continue;
        }
        queue.push({ directory: full, depth: current.depth + 1 });
        continue;
      }
      if (isFile) {
        files.push(full);
      }
    }
  }
  return { files, truncated };
}

function looksBinary(buffer: Buffer): boolean {
  const slice = buffer.subarray(0, BINARY_SNIFF_BYTES);
  return slice.includes(0);
}

function normalizeForCompare(target: string): string {
  const resolved = realPathSafe(target);
  if (resolved.length > 1) {
    return resolved.replace(/[\\/]+$/, '');
  }
  return resolved;
}

function clampLine(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(1, Math.floor(parsed));
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function exists(target: string): boolean {
  try {
    fs.statSync(target);
    return true;
  } catch {
    return false;
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
