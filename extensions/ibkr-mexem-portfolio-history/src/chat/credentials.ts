/**
 * API key resolution for the chat. `vscode`-free: the extension passes a
 * SecretStorage reader, the tests pass fakes. The key value is never logged.
 */
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

/** SecretStorage key of the chat API key. */
export const CHAT_API_KEY_SECRET = 'ibkrHistory.chat.apiKey';

export type ApiKeySource = 'secret' | 'env' | 'opencodeAuth';

export interface ResolvedApiKey {
  readonly key: string;
  readonly source: ApiKeySource;
}

export interface ApiKeyReaders {
  readonly readSecret?: () => Promise<string | undefined>;
  readonly readEnv?: () => string | undefined;
  readonly readAuthFile?: () => Promise<string | undefined>;
}

export function opencodeAuthPath(): string {
  return join(homedir(), '.local/share/opencode', 'auth.json');
}

/**
 * `{ "opencode-go": { "type": "api", "key": "<key>" } }` -> the key.
 * A missing entry, invalid JSON or a non-string key returns `undefined`.
 */
export function parseOpencodeAuthKey(text: string): string | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (typeof parsed !== 'object' || parsed === null) {
    return undefined;
  }
  const entry = (parsed as Record<string, unknown>)['opencode-go'];
  if (typeof entry !== 'object' || entry === null) {
    return undefined;
  }
  const key = (entry as { key?: unknown }).key;
  if (typeof key !== 'string') {
    return undefined;
  }
  const trimmed = key.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

async function readDefaultAuthFile(): Promise<string | undefined> {
  try {
    return await readFile(opencodeAuthPath(), 'utf8');
  } catch {
    return undefined;
  }
}

/**
 * First match wins: SecretStorage, then `OPENCODE_API_KEY`, then the opencode
 * `auth.json` entry for `opencode-go`.
 */
export async function resolveApiKey(readers: ApiKeyReaders = {}): Promise<ResolvedApiKey | undefined> {
  const fromSecret = (await readers.readSecret?.())?.trim();
  if (fromSecret) {
    return { key: fromSecret, source: 'secret' };
  }

  const fromEnv = (readers.readEnv?.() ?? process.env.OPENCODE_API_KEY)?.trim();
  if (fromEnv) {
    return { key: fromEnv, source: 'env' };
  }

  const authText = await (readers.readAuthFile ?? readDefaultAuthFile)();
  if (!authText) {
    return undefined;
  }
  const key = parseOpencodeAuthKey(authText);
  return key ? { key, source: 'opencodeAuth' } : undefined;
}
