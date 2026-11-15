/**
 * The `Open in @trade` handoff: the file name, the header of the written file
 * and the chat query. No `vscode` import, so `node --test` covers the rules.
 */
import type { DatasetPayload } from '../panel/protocol.ts';

/** Hard ceiling of the chat query, in characters. */
export const HANDOFF_MAX_QUERY_LENGTH = 400;

/** `2026-11-15T14:40:43.967Z` -> `20261115T144043Z`, safe in a file name. */
export function handoffStamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
}

/** The header of the handoff file: what the file is and when it was made. */
export function handoffHeader(dataset: DatasetPayload, generatedAtIso: string): string[] {
  return [
    '# IBKR portfolio handoff',
    '',
    'This file is the IBKR dataset of the VS Code extension "IBKR Mexem Portfolio History", ' +
      'plus the live option data of the local trading CLI when that data is available.',
    `Generated at ${generatedAtIso} (UTC).`,
    `Range: ${dataset.meta.range.start} to ${dataset.meta.range.end} (${dataset.meta.range.label}).`,
    `Account filter: ${dataset.meta.accountFilter ?? 'none (all accounts)'}.`,
    `Base currency: ${dataset.baseCurrency}. Trade rows in range: ${dataset.meta.rowsInRange}.`,
    'Every number keeps the currency of its block. Do not convert a figure silently.'
  ];
}

/**
 * A query for `workbench.action.chat.open`, always under
 * {@link HANDOFF_MAX_QUERY_LENGTH} characters, naming the absolute file path.
 * Longest instruction first, then shorter ones; the path is never truncated.
 */
export function buildHandoffQuery(filePath: string): string {
  const candidates = [
    `@trade Read the IBKR portfolio snapshot in ${filePath} and analyse the open positions, the option values and the risk. State every currency.`,
    `@trade Read ${filePath} and analyse the portfolio, the option values and the risk. State every currency.`,
    `@trade Read ${filePath} and analyse the portfolio. State every currency.`,
    `@trade Read ${filePath}`
  ];
  const fitting = candidates.find((candidate) => candidate.length < HANDOFF_MAX_QUERY_LENGTH);
  const longest = candidates[candidates.length - 1];
  return fitting ?? longest ?? '@trade';
}
