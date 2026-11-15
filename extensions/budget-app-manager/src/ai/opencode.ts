import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { PROVIDER_MODELS } from '../types';
import type { StreamingLlmClient } from './client';

export interface OpenCodeConfig {
  model: string;
  timeoutMs?: number;
  apiKey?: string;
  binary?: string;
  cwd?: string;
}

const SECURE_MODEL_RE = /^[A-Za-z0-9._/:@-]+$/;

function effectiveModel(model: string): string {
  const trimmed = model.trim();
  if (!trimmed) return 'opencode/deepseek-v4-flash-free';
  const prefixed = trimmed.startsWith('opencode-go/') ? trimmed : `opencode-go/${trimmed}`;
  if (prefixed.includes('local')) {
    return 'opencode/deepseek-v4-flash-free';
  }
  return prefixed;
}

export class OpenCodeCliAgent implements StreamingLlmClient {
  private readonly model: string;
  private readonly timeoutMs: number;
  private readonly apiKey: string;
  private readonly binary: string;
  private readonly cwd: string;

  constructor(config: OpenCodeConfig) {
    this.model = effectiveModel(config.model);
    if (!SECURE_MODEL_RE.test(this.model)) {
      throw new Error(`Modello OpenCode non valido: ${config.model}`);
    }
    this.timeoutMs = config.timeoutMs ?? 300_000;
    this.apiKey = config.apiKey ?? '';
    this.binary = config.binary ?? 'opencode';
    this.cwd = config.cwd ?? process.cwd();
  }

  async categorize(prompt: string): Promise<string> {
    const chunks: string[] = [];
    for await (const chunk of this.streamPrompt(prompt)) chunks.push(chunk);
    const text = chunks.join('');
    if (!text.trim()) {
      throw new Error('Nessun output ricevuto da opencode.');
    }
    return text;
  }

  async *streamChat(system: string, user: string): AsyncGenerator<string> {
    const prompt = system ? `${system}\n\nDOMANDA UTENTE: ${user}` : user;
    yield* this.streamPrompt(prompt);
  }

  async *streamPrompt(prompt: string): AsyncGenerator<string> {
    const longPrompt = prompt.length > 10_000;
    let tempDir: string | null = null;
    let child;
    if (longPrompt) {
      tempDir = mkdtempSync(join(tmpdir(), 'budget-opencode-'));
      const file = join(tempDir, 'prompt.txt');
      writeFileSync(file, prompt, 'utf8');
      const command = `${quoteShell(this.binary)} run --format json --model ${this.model} < ${quoteShell(file)}`;
      child = spawn(command, {
        shell: true,
        cwd: this.cwd,
        env: this.childEnv(),
      });
    } else {
      child = spawn(
        this.binary,
        ['run', '--format', 'json', '--model', this.model, prompt],
        { cwd: this.cwd, env: this.childEnv() },
      );
    }

    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGKILL');
    }, this.timeoutMs);
    let stderr = '';
    child.stderr?.on('data', (chunk: Buffer) => {
      if (stderr.length < 8000) stderr += chunk.toString();
    });
    child.on('error', () => {
      // handled by close/error below
    });

    const closed = new Promise<{ code: number | null; signal: NodeJS.Signals | null; spawnError?: Error }>(
      (resolve) => {
        child.once('close', (code, signal) => resolve({ code, signal }));
        child.once('error', (error) => resolve({ code: null, signal: null, spawnError: error }));
      },
    );

    let yielded = false;
    try {
      if (!child.stdout) {
        throw new Error('stdout di opencode non disponibile.');
      }
      const reader = createInterface({ input: child.stdout });
      for await (const rawLine of reader) {
        const line = rawLine.trim();
        if (!line) continue;
        let event: unknown;
        try {
          event = JSON.parse(line) as unknown;
        } catch {
          continue;
        }
        if (!event || typeof event !== 'object') continue;
        const record = event as Record<string, unknown>;
        if (record.type === 'text') {
          const part = record.part;
          if (part && typeof part === 'object') {
            const text = (part as Record<string, unknown>).text;
            if (typeof text === 'string' && text) {
              yielded = true;
              yield text;
            }
          }
        }
      }
    } finally {
      clearTimeout(timer);
    }

    const result = await closed;
    if (tempDir) {
      try {
        rmSync(tempDir, { recursive: true, force: true });
      } catch {
        // ignore
      }
    }
    if (result.spawnError) {
      const code = (result.spawnError as NodeJS.ErrnoException).code;
      if (code === 'ENOENT') {
        throw new Error(
          'opencode CLI non trovato. Installa opencode (https://opencode.ai) oppure scegli un altro provider nella AI Configuration.',
        );
      }
      throw new Error(`opencode: ${result.spawnError.message}`);
    }
    if (timedOut) {
      throw new Error(`Timeout di esecuzione superato (${Math.round(this.timeoutMs / 1000)}s).`);
    }
    if (result.code !== 0 && !yielded) {
      const detail = stderr.trim().slice(0, 500);
      throw new Error(
        detail
          ? `opencode terminato con codice ${result.code}: ${detail}`
          : `opencode terminato con codice ${result.code}.`,
      );
    }
  }

  private childEnv(): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = { ...process.env };
    if (this.apiKey) env.OPENCODE_GO_API_KEY = this.apiKey;
    return env;
  }
}

function quoteShell(value: string): string {
  if (process.platform === 'win32') {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

export async function listOpenCodeCliModels(binary = 'opencode'): Promise<string[]> {
  return new Promise((resolve) => {
    let output = '';
    let settled = false;
    const child = spawn(binary, ['models'], { stdio: ['ignore', 'pipe', 'ignore'] });
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill('SIGKILL');
      resolve(PROVIDER_MODELS.opencode);
    }, 8000);
    child.stdout?.on('data', (chunk: Buffer) => {
      if (output.length < 200_000) output += chunk.toString();
    });
    child.once('error', () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(PROVIDER_MODELS.opencode);
    });
    child.once('close', () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const models = output
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.startsWith('opencode-go/'))
        .map((line) => line.replace(/^opencode-go\//, ''))
        .filter(Boolean);
      resolve(models.length > 0 ? [...new Set(models)] : PROVIDER_MODELS.opencode);
    });
  });
}
