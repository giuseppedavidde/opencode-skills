/**
 * Builds the redacted report copied by "Copy diagnostics" and by the
 * `ibkrHistory.copyDiagnostics` command. No `vscode` import: unit-testable.
 */
import { redactSecrets } from '../flex/client.ts';
import { FlexApiError } from '../flex/errors.ts';
import type { FlexError } from '../flex/errors.ts';

export interface DiagnosticsInput {
  readonly extensionVersion: string;
  readonly baseUrl: string;
  /** Length only. The token itself never enters this function. */
  readonly tokenLength: number;
  /** Digit count only. The Query ID itself never enters this function. */
  readonly queryIdDigits: number;
  readonly elapsedMs: number;
  /** GetStatement polls only. */
  readonly attempts: number;
  readonly maxAttempts?: number;
  /** SendRequest HTTP calls, including retries after a transient error. */
  readonly sendAttempts?: number;
  readonly maxSendAttempts?: number;
  /** Last transient SendRequest error, for example `IBKR error 1001 (...)`. */
  readonly lastRetryReason?: string;
  /** Hard time limit, used to report the remaining retry budget. */
  readonly deadlineMs?: number;
  readonly lastStatus: string;
  readonly lastErrorCode: string;
  readonly bodySnippet: string;
  /** Row shape detected in the report: `AF`, `TradeConfirm`, or absent when unknown. */
  readonly queryType?: string;
  /** Rows the parser produced. Set to 0 on the "empty report" path. */
  readonly rowsParsed?: number;
  /** Reference code to scrub if it appears outside a URL query string. */
  readonly referenceCode?: string;
  /**
   * Extra secret values to scrub wherever they appear. The caller passes the
   * Flex token here; it is used only for redaction and is never written out.
   */
  readonly secrets?: readonly (string | undefined)[];
}

/** Transport and body facts every {@link FlexError} carries. */
export interface FailureFacts {
  readonly attempts: number;
  readonly elapsedMs: number;
  readonly lastStatus: string;
  readonly lastErrorCode: string;
  readonly bodySnippet: string;
  readonly sendAttempts?: number;
  readonly maxSendAttempts?: number;
  readonly lastRetryReason?: string;
}

/**
 * Read the failure facts from any Flex error. Every error class fills
 * `diagnostics`, so this needs no `instanceof` ladder. `FlexApiError` still keeps
 * its own `code`, which is used only when the diagnostics carry no error code.
 */
export function failureFactsOf(error: FlexError): FailureFacts {
  const diagnostics = error.diagnostics;
  const fallbackCode = error instanceof FlexApiError ? (error.code ?? '') : '';
  return {
    attempts: diagnostics.attempts ?? 0,
    elapsedMs: diagnostics.elapsedMs ?? 0,
    lastStatus: diagnostics.lastStatus ?? '',
    lastErrorCode: diagnostics.lastErrorCode || fallbackCode,
    bodySnippet: diagnostics.lastBodySnippet ?? '',
    sendAttempts: diagnostics.sendAttempts,
    maxSendAttempts: diagnostics.maxSendAttempts,
    lastRetryReason: diagnostics.lastRetryReason
  };
}

export function maskToken(tokenLength: number): string {
  return tokenLength > 0 ? `set, ${tokenLength} characters (not shown)` : 'absent';
}

export function buildDiagnosticsReport(input: DiagnosticsInput): string {
  const elapsedSeconds = (Math.max(0, input.elapsedMs) / 1000).toFixed(1);
  const polls = input.maxAttempts === undefined ? `${input.attempts}` : `${input.attempts} of ${input.maxAttempts}`;
  const sends =
    input.sendAttempts === undefined
      ? undefined
      : input.maxSendAttempts !== undefined && input.sendAttempts <= input.maxSendAttempts
        ? `${input.sendAttempts} of ${input.maxSendAttempts}`
        : `${input.sendAttempts}`;
  const deadlineRemaining =
    input.deadlineMs === undefined ? undefined : Math.max(0, input.deadlineMs - input.elapsedMs);
  const snippet = redactSecrets(input.bodySnippet, [input.referenceCode, ...(input.secrets ?? [])]).slice(0, 500);
  const lines = [
    'IBKR Mexem Portfolio History - diagnostics',
    `Extension version: ${input.extensionVersion}`,
    `Base URL: ${input.baseUrl}`,
    `Flex token: ${maskToken(input.tokenLength)}`,
    `Query ID: ${input.queryIdDigits} digits`,
    `Elapsed: ${elapsedSeconds} s`,
    `Polls: ${polls}`
  ];
  if (sends !== undefined) {
    lines.push(`SendRequest attempts: ${sends}`);
  }
  if (input.lastRetryReason) {
    lines.push(`Last retry reason: ${input.lastRetryReason}`);
  }
  if (deadlineRemaining !== undefined) {
    lines.push(`Deadline remaining: ${(deadlineRemaining / 1000).toFixed(1)} s`);
  }
  lines.push(
    `Last IBKR status: ${input.lastStatus || 'none'}`,
    `Last IBKR error code: ${input.lastErrorCode || 'none'}`
  );
  if (input.queryType) {
    lines.push(`Query type: ${input.queryType}`);
  }
  if (input.rowsParsed !== undefined) {
    lines.push(`Rows parsed: ${input.rowsParsed}`);
  }
  lines.push('Last response snippet (first 500 characters):', snippet || '(empty)');
  return lines.join('\n');
}
