import * as fs from 'node:fs';
import * as path from 'node:path';

export interface PermissionEntry {
  name: string;
  allowed: boolean;
}

export interface TradeAgentCapabilities {
  name: string;
  description: string;
  model: string;
  mode: string;
  steps: number | null;
  permissions: PermissionEntry[];
  mcpTools: string[];
  workflowSteps: string[];
}

export interface TradingServerConfig {
  name: string;
  type: string;
  command: string;
  args: string[];
  env: Record<string, string>;
}

export interface SkillInfo {
  name: string;
  description: string;
  dir: string;
  path: string;
}

export interface SkillDrift {
  missingInInstalled: string[];
  extraInInstalled: string[];
}

export interface CapabilityState {
  agent: TradeAgentCapabilities | null;
  server: TradingServerConfig | null;
  skills: SkillInfo[];
  errors: string[];
}

export interface FsAdapter {
  readdir(dir: string): string[];
  isDirectory(target: string): boolean;
  exists(target: string): boolean;
  readFile(target: string): string;
}

const BUILTIN_PERMISSION_KEYS = new Set([
  'bash',
  'read',
  'edit',
  'write',
  'glob',
  'grep',
  'webfetch',
  'task',
  'skill',
  'external_directory',
  'todowrite',
  'list',
  'patch',
  'apply_patch',
  'question',
  'lsp',
  'codesearch',
  'mcp',
  'websearch',
  'fetch',
  'notebook',
]);

interface SourceLine {
  indent: number;
  text: string;
}

interface Frontmatter {
  data: Record<string, unknown>;
  body: string;
}

export function extractFrontmatter(text: string): Frontmatter {
  const source = text.replace(/\r\n?/g, '\n').replace(/^\uFEFF/, '');
  const lines = source.split('\n');
  if (lines.length === 0 || lines[0].trim() !== '---') {
    return { data: {}, body: source };
  }
  let end = -1;
  for (let index = 1; index < lines.length; index += 1) {
    const marker = lines[index].trim();
    if (marker === '---' || marker === '...') {
      end = index;
      break;
    }
  }
  if (end === -1) {
    return { data: {}, body: source };
  }
  return {
    data: parseYamlSubset(lines.slice(1, end)),
    body: lines.slice(end + 1).join('\n'),
  };
}

export function parseTradeAgent(markdown: string, fallbackName = 'trade'): TradeAgentCapabilities {
  const { data, body } = extractFrontmatter(markdown);
  const permissions = flattenPermissions(data.permission);
  const mcpTools = permissions
    .filter((entry) => entry.allowed && !BUILTIN_PERMISSION_KEYS.has(entry.name))
    .map((entry) => entry.name);
  return {
    name: readString(data.name) || fallbackName,
    description: normalizeSpace(readString(data.description)),
    model: readString(data.model),
    mode: readString(data.mode),
    steps: typeof data.steps === 'number' ? data.steps : null,
    permissions,
    mcpTools,
    workflowSteps: extractWorkflowSteps(body),
  };
}

export function resolveTradingServer(config: unknown, serverName = 'trading'): TradingServerConfig | null {
  let parsed: unknown = config;
  if (typeof config === 'string') {
    try {
      parsed = JSON.parse(config);
    } catch {
      return null;
    }
  }
  if (!isRecord(parsed) || !isRecord(parsed.mcpServers)) {
    return null;
  }
  const entry = parsed.mcpServers[serverName];
  if (!isRecord(entry)) {
    return null;
  }
  const command = readString(entry.command).trim();
  if (!command) {
    return null;
  }
  const args = Array.isArray(entry.args) ? entry.args.filter((arg): arg is string => typeof arg === 'string') : [];
  const env: Record<string, string> = {};
  if (isRecord(entry.env)) {
    for (const [key, value] of Object.entries(entry.env)) {
      if (typeof value === 'string') {
        env[key] = value;
      }
    }
  }
  return {
    name: serverName,
    type: readString(entry.type) || 'stdio',
    command,
    args,
    env,
  };
}

export function scanSkillCatalogue(skillsDir: string, fsAdapter: FsAdapter): SkillInfo[] {
  let entries: string[];
  try {
    entries = fsAdapter.readdir(skillsDir);
  } catch {
    return [];
  }
  const skills: SkillInfo[] = [];
  for (const entry of [...entries].sort()) {
    if (entry.startsWith('.')) {
      continue;
    }
    const dir = path.join(skillsDir, entry);
    let directory = false;
    try {
      directory = fsAdapter.isDirectory(dir);
    } catch {
      directory = false;
    }
    if (!directory) {
      continue;
    }
    const file = path.join(dir, 'SKILL.md');
    if (!fsAdapter.exists(file)) {
      continue;
    }
    let content: string;
    try {
      content = fsAdapter.readFile(file);
    } catch {
      continue;
    }
    const { data } = extractFrontmatter(content);
    skills.push({
      name: readString(data.name) || entry,
      description: normalizeSpace(readString(data.description)),
      dir,
      path: file,
    });
  }
  return skills;
}

export function diffSkillDirectories(repoSkillsDir: string, installedSkillsDir: string, fsAdapter: FsAdapter): SkillDrift {
  const repo = new Set(scanSkillCatalogue(repoSkillsDir, fsAdapter).map((skill) => path.basename(skill.dir)));
  const installed = new Set(scanSkillCatalogue(installedSkillsDir, fsAdapter).map((skill) => path.basename(skill.dir)));
  return {
    missingInInstalled: [...repo].filter((name) => !installed.has(name)).sort(),
    extraInInstalled: [...installed].filter((name) => !repo.has(name)).sort(),
  };
}

export function capabilitySignature(state: CapabilityState): string {
  return JSON.stringify({
    agent: state.agent
      ? {
          name: state.agent.name,
          description: state.agent.description,
          model: state.agent.model,
          mode: state.agent.mode,
          steps: state.agent.steps,
          permissions: state.agent.permissions.map((entry) => [entry.name, entry.allowed]),
          mcpTools: state.agent.mcpTools,
          workflowSteps: state.agent.workflowSteps,
        }
      : null,
    server: state.server,
    skills: state.skills.map((skill) => [skill.name, skill.description, skill.path]),
    errors: state.errors,
  });
}

export function createNodeFsAdapter(): FsAdapter {
  return {
    readdir: (dir) => fs.readdirSync(dir),
    isDirectory: (target) => fs.statSync(target).isDirectory(),
    exists: (target) => fs.existsSync(target),
    readFile: (target) => fs.readFileSync(target, 'utf8'),
  };
}

function flattenPermissions(value: unknown): PermissionEntry[] {
  if (!isRecord(value)) {
    return [];
  }
  return Object.entries(value).map(([name, raw]) => ({ name, allowed: isAllowed(raw) }));
}

function isAllowed(raw: unknown): boolean {
  if (raw === 'allow' || raw === true) {
    return true;
  }
  if (isRecord(raw)) {
    return Object.values(raw).some((inner) => isAllowed(inner));
  }
  return false;
}

function extractWorkflowSteps(body: string): string[] {
  const steps: string[] = [];
  const seen = new Set<string>();
  for (const line of body.split('\n')) {
    const match = /^##\s+(.+?)\s*$/.exec(line);
    if (!match) {
      continue;
    }
    const title = match[1].trim();
    if (!title || seen.has(title)) {
      continue;
    }
    seen.add(title);
    steps.push(title);
  }
  return steps;
}

function parseYamlSubset(lines: string[]): Record<string, unknown> {
  const source = lines.map((raw) => {
    const expanded = raw.replace(/\t/g, '  ');
    return { indent: expanded.length - expanded.trimStart().length, text: expanded.trim() };
  });
  return parseMap(source, 0, 0).value;
}

function parseMap(source: SourceLine[], start: number, indent: number): { value: Record<string, unknown>; next: number } {
  const value: Record<string, unknown> = {};
  let index = start;
  while (index < source.length) {
    const line = source[index];
    if (line.text === '' || line.text.startsWith('#')) {
      index += 1;
      continue;
    }
    if (line.indent < indent) {
      break;
    }
    if (line.indent > indent || line.text.startsWith('- ')) {
      index += 1;
      continue;
    }
    const match = /^("[^"]*"|'[^']*'|[^:]+):(?:\s+(.*))?$/.exec(line.text);
    if (!match) {
      index += 1;
      continue;
    }
    const key = unquote(match[1].trim());
    const rest = (match[2] ?? '').trim();
    index += 1;
    if (rest === '') {
      let next = index;
      while (next < source.length && (source[next].text === '' || source[next].text.startsWith('#'))) {
        next += 1;
      }
      if (next < source.length && source[next].indent > indent) {
        const childIndent = source[next].indent;
        if (source[next].text.startsWith('- ')) {
          const list = parseList(source, next, childIndent);
          value[key] = list.value;
          index = list.next;
        } else {
          const child = parseMap(source, next, childIndent);
          value[key] = child.value;
          index = child.next;
        }
      } else {
        value[key] = null;
      }
      continue;
    }
    if (/^[|>][+-]?$/.test(rest)) {
      const block = parseBlockScalar(source, index, indent, rest[0] === '>');
      value[key] = block.value;
      index = block.next;
      continue;
    }
    value[key] = parseScalar(rest);
  }
  return { value, next: index };
}

function parseList(source: SourceLine[], start: number, indent: number): { value: unknown[]; next: number } {
  const value: unknown[] = [];
  let index = start;
  while (index < source.length) {
    const line = source[index];
    if (line.text === '' || line.text.startsWith('#')) {
      index += 1;
      continue;
    }
    if (line.indent !== indent || !line.text.startsWith('- ')) {
      break;
    }
    value.push(parseScalar(line.text.slice(2)));
    index += 1;
  }
  return { value, next: index };
}

function parseBlockScalar(source: SourceLine[], start: number, parentIndent: number, folded: boolean): { value: string; next: number } {
  const parts: string[] = [];
  let index = start;
  while (index < source.length) {
    const line = source[index];
    if (line.text === '') {
      parts.push('');
      index += 1;
      continue;
    }
    if (line.indent <= parentIndent) {
      break;
    }
    parts.push(line.text);
    index += 1;
  }
  while (parts.length > 0 && parts[parts.length - 1] === '') {
    parts.pop();
  }
  return { value: folded ? foldLines(parts) : parts.join('\n'), next: index };
}

function foldLines(parts: string[]): string {
  const merged: string[] = [];
  for (const part of parts) {
    if (part === '') {
      merged.push('\n');
      continue;
    }
    if (merged.length === 0 || merged[merged.length - 1] === '\n') {
      merged.push(part);
      continue;
    }
    merged[merged.length - 1] = `${merged[merged.length - 1]} ${part}`;
  }
  return merged.join('').replace(/ ?\n ?/g, '\n').trim();
}

function parseScalar(raw: string): unknown {
  const value = stripInlineComment(raw).trim();
  if (value === '') {
    return '';
  }
  if (/^(true|false)$/i.test(value)) {
    return value.toLowerCase() === 'true';
  }
  if (/^null$/i.test(value)) {
    return null;
  }
  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }
  return unquote(value);
}

function stripInlineComment(raw: string): string {
  let quote = '';
  for (let index = 0; index < raw.length; index += 1) {
    const char = raw[index];
    if (quote) {
      if (char === quote) {
        quote = '';
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === '#' && (index === 0 || /\s/.test(raw[index - 1]))) {
      return raw.slice(0, index);
    }
  }
  return raw;
}

function unquote(value: string): string {
  if (value.length >= 2) {
    const first = value[0];
    const last = value[value.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1);
    }
  }
  return value;
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function normalizeSpace(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
