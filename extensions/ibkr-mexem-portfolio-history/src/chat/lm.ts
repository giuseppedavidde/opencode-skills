/**
 * Adapter for the VS Code Language Model API (`vscode.lm`).
 *
 * The helpers in this module are pure and there is no top-level `vscode`
 * import, so `node --test` drives them with fakes. The real models enter as
 * `LanguageModelInfoLike` values, which keeps `vscode.lm` inside the view
 * provider.
 */
import type { ChatMessage } from './client.ts';
import type { ModelOption } from './protocol.ts';

/** The subset of `vscode.LanguageModelChatSelector` this extension uses. */
export interface LanguageModelSelector {
  readonly vendor?: string;
  readonly family?: string;
  readonly id?: string;
}

/** The subset of `vscode.LanguageModelChat` the pure helpers need. */
export interface LanguageModelInfoLike {
  readonly id: string;
  readonly name: string;
  readonly family?: string;
}

/** The subset of the `vscode.lm` namespace this extension uses. */
export interface LanguageModelApi {
  selectChatModels(selector?: LanguageModelSelector): PromiseLike<readonly LanguageModelInfoLike[]>;
}

/**
 * One message for the Language Model API. The API exposes only the `User` and
 * the `Assistant` statics, so there is no `system` role here.
 */
export interface LanguageModelMessage {
  readonly role: 'user' | 'assistant';
  readonly content: string;
}

/** `name` first, then `family`, then the raw id. */
export function modelLabel(model: LanguageModelInfoLike): string {
  const name = model.name.trim();
  if (name.length > 0) {
    return name;
  }
  const family = (model.family ?? '').trim();
  return family.length > 0 ? family : model.id;
}

/**
 * The dropdown options: one entry per id (the first wins), sorted by label.
 * An empty input returns an empty list, never a placeholder.
 */
export function toModelOptions(models: readonly LanguageModelInfoLike[]): ModelOption[] {
  const seen = new Set<string>();
  const options: ModelOption[] = [];
  for (const model of models) {
    const id = model.id.trim();
    if (id.length === 0 || seen.has(id)) {
      continue;
    }
    seen.add(id);
    options.push({ id, label: modelLabel(model) });
  }
  return options.sort(
    (left, right) =>
      left.label.localeCompare(right.label, 'en', { sensitivity: 'base' }) || left.id.localeCompare(right.id, 'en')
  );
}

/**
 * Exact id first, then an exact family match, then the first model. An empty
 * list returns `undefined` so the caller can post the "no model" hint.
 */
export function selectModel<T extends LanguageModelInfoLike>(
  models: readonly T[],
  wantedId: string
): T | undefined {
  const wanted = wantedId.trim();
  if (wanted.length > 0) {
    const byId = models.find((model) => model.id === wanted);
    if (byId) {
      return byId;
    }
    const byFamily = models.find((model) => (model.family ?? '') === wanted);
    if (byFamily) {
      return byFamily;
    }
  }
  return models[0];
}

/**
 * The turn list for `model.sendRequest`.
 *
 * The persona and the portfolio context go into the **first** user message,
 * because `LanguageModelChatMessage` has no system role. Without history the
 * question joins that first message, so the turns always alternate. With
 * history the turns are `user, assistant, ...` and the question comes last.
 */
export function toLmMessages(
  persona: string,
  contextText: string,
  history: readonly ChatMessage[],
  userText: string
): LanguageModelMessage[] {
  const preamble = `${persona}\n\n---\n\n${contextText}`;
  const turns: LanguageModelMessage[] = [];
  for (const message of history) {
    if (message.role === 'system') {
      continue;
    }
    turns.push({ role: message.role === 'assistant' ? 'assistant' : 'user', content: message.content });
  }
  if (turns.length === 0) {
    return [{ role: 'user', content: `${preamble}\n\n---\n\n${userText}` }];
  }
  return [{ role: 'user', content: preamble }, ...turns, { role: 'user', content: userText }];
}

/** Human message for a rejected `sendRequest`. It never carries a credential. */
export function describeLanguageModelError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const code =
    typeof error === 'object' && error !== null ? (error as { code?: unknown }).code : undefined;
  const known = typeof code === 'string' ? code : '';
  if (known === 'NoPermissions') {
    return `VS Code did not grant access to the language model. Allow the request, then use Retry. ${message}`;
  }
  if (known === 'Blocked') {
    return `The language model is blocked or the quota is exhausted. Check your subscription, then use Retry. ${message}`;
  }
  if (known === 'NotFound') {
    return `The selected language model is no longer available. Pick another model in the dropdown. ${message}`;
  }
  return `The language model request failed: ${message}`;
}
