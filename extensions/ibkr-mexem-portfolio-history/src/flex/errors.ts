/**
 * Error codes documented for the Flex Web Service.
 * Source: https://www.interactivebrokers.com/campus/ibkr-api-page/flex-web-service/ (Error Codes)
 */
export interface FlexErrorInfo {
  readonly code: string;
  /** Message as documented by IBKR. */
  readonly message: string;
  /** What the user can do about it. */
  readonly hint: string;
  /** Whether polling again can plausibly succeed without user action. */
  readonly retryable: boolean;
}

export const FLEX_ERRORS: Readonly<Record<string, FlexErrorInfo>> = {
  '1001': {
    code: '1001',
    message: 'Statement could not be generated at this time.',
    hint: 'IBKR was busy. Retry in a minute. If it persists, regenerate the token in Client Portal.',
    retryable: true
  },
  '1003': {
    code: '1003',
    message: 'Statement is not available.',
    hint: 'The query ID may be wrong or the query was deleted. Verify the Query ID in Client Portal > Reporting > Flex Queries.',
    retryable: false
  },
  '1004': {
    code: '1004',
    message: 'Statement is incomplete at this time.',
    hint: 'IBKR is still assembling the report. Retry shortly.',
    retryable: true
  },
  '1005': {
    code: '1005',
    message: 'Settlement data is not ready at this time.',
    hint: 'Retry later the same day, or the next business day.',
    retryable: true
  },
  '1006': {
    code: '1006',
    message: 'FIFO P/L data is not ready at this time.',
    hint: 'Realized P&L for the newest trades is not computed yet. Retry the next business day.',
    retryable: true
  },
  '1007': {
    code: '1007',
    message: 'MTM P/L data is not ready at this time.',
    hint: 'Retry later. This extension only uses FIFO P&L, so the report is still usable once IBKR finishes.',
    retryable: true
  },
  '1008': {
    code: '1008',
    message: 'MTM and FIFO P/L data are not ready at this time.',
    hint: 'Retry the next business day.',
    retryable: true
  },
  '1009': {
    code: '1009',
    message: 'The server is under heavy load.',
    hint: 'Retry in a few minutes.',
    retryable: true
  },
  '1010': {
    code: '1010',
    message: 'Legacy Flex Queries are no longer supported.',
    hint: 'Convert the query to an Activity Flex Query or Trade Confirmation Flex Query in Client Portal.',
    retryable: false
  },
  '1011': {
    code: '1011',
    message: 'Service account is inactive.',
    hint: 'Enable the Flex Web Service in Client Portal > Performance & Reports > Flex Queries > Flex Web Service Configuration.',
    retryable: false
  },
  '1012': {
    code: '1012',
    message: 'Token has expired.',
    hint: 'Generate a new token in Client Portal > Flex Web Service Configuration, then paste it into this panel.',
    retryable: false
  },
  '1013': {
    code: '1013',
    message: 'IP restriction.',
    hint: 'The token is bound to a different IP address. Generate a token without IP restriction or from this network.',
    retryable: false
  },
  '1014': {
    code: '1014',
    message: 'Query is invalid.',
    hint: 'Check the Query ID and that the query still exists and is not a legacy query.',
    retryable: false
  },
  '1015': {
    code: '1015',
    message: 'Token is invalid.',
    hint: 'Copy the Current Token again from Client Portal > Flex Web Service Configuration. Watch for stray spaces.',
    retryable: false
  },
  '1016': {
    code: '1016',
    message: 'Account is invalid.',
    hint: 'The token cannot access the queried account. Regenerate the token from the master account.',
    retryable: false
  },
  '1017': {
    code: '1017',
    message: 'Reference code is invalid.',
    hint: 'Start a new fetch: the reference code expires quickly and is single-use.',
    retryable: false
  },
  '1018': {
    code: '1018',
    message: 'Too many requests have been made from this token.',
    hint: 'The service allows 1 request per second and 10 per minute per token. Wait a full minute.',
    retryable: true
  },
  '1019': {
    code: '1019',
    message: 'Statement generation in progress.',
    hint: 'Normal while IBKR builds the report. The extension keeps polling.',
    retryable: true
  },
  '1020': {
    code: '1020',
    message: 'Invalid request or unable to validate request.',
    hint: 'Token or Query ID is malformed. The Query ID must be numeric and the token must be copied in full.',
    retryable: false
  },
  '1021': {
    code: '1021',
    message: 'Statement could not be retrieved at this time.',
    hint: 'Retry shortly. If it keeps failing, reduce the query period in Client Portal.',
    retryable: true
  }
};

export function lookupFlexError(code: string | undefined): FlexErrorInfo | undefined {
  if (!code) {
    return undefined;
  }
  return FLEX_ERRORS[code.trim()];
}

export class FlexError extends Error {
  readonly userMessage: string;
  /**
   * Facts about the failure, always present so the diagnostics report never
   * has to guess with an `instanceof` ladder. Empty for failures that have no
   * transport history (a cancelled fetch, for example).
   */
  readonly diagnostics: FlexFailureDiagnostics;

  constructor(message: string, userMessage: string, diagnostics: FlexFailureDiagnostics = {}) {
    super(message);
    this.name = new.target.name;
    this.userMessage = userMessage;
    this.diagnostics = diagnostics;
  }
}

export class FlexApiError extends FlexError {
  readonly code: string | undefined;
  readonly retryable: boolean;

  constructor(
    code: string | undefined,
    serverMessage: string,
    diagnostics: FlexFailureDiagnostics = {},
    context = ''
  ) {
    const info = lookupFlexError(code);
    const detail = info ? info.message : serverMessage || 'The Flex Web Service returned an error.';
    const hint = info ? info.hint : 'Check the token and Query ID, then retry.';
    super(
      `Flex error ${code ?? 'unknown'}: ${serverMessage || detail}`,
      `IBKR Flex error ${code ?? ''}: ${detail} ${hint}${context ? ` ${context}` : ''}`.trim(),
      { ...diagnostics, lastErrorCode: diagnostics.lastErrorCode || (code ?? '') }
    );
    this.code = code;
    this.retryable = info?.retryable ?? false;
  }
}

export class FlexCancelledError extends FlexError {
  constructor() {
    super('Flex fetch cancelled.', 'Fetch cancelled.');
  }
}

/** Facts attached to a failure so the user and the log can tell one cause from another. */
export interface FlexFailureDiagnostics {
  /** GetStatement polls only. SendRequest attempts have their own counter. */
  readonly attempts?: number;
  /** HTTP requests sent to /SendRequest, including retries after a transient error. */
  readonly sendAttempts?: number;
  readonly maxSendAttempts?: number;
  /** Last transient SendRequest error, for example `IBKR error 1001 (...)` */
  readonly lastRetryReason?: string;
  readonly elapsedMs?: number;
  readonly lastStatus?: string;
  readonly lastErrorCode?: string;
  readonly lastBodySnippet?: string;
  /** HTTP status of the failing request, when the failure came from one. */
  readonly httpStatus?: number;
}

/** Short, secret-free description used inside error messages. */
export function describeFailure(diagnostics: FlexFailureDiagnostics): string {
  const parts: string[] = [];
  if (diagnostics.attempts !== undefined) {
    parts.push(`${diagnostics.attempts} poll(s)`);
  }
  if (diagnostics.sendAttempts !== undefined) {
    parts.push(
      diagnostics.maxSendAttempts === undefined
        ? `${diagnostics.sendAttempts} SendRequest attempt(s)`
        : `${diagnostics.sendAttempts} of ${diagnostics.maxSendAttempts} SendRequest attempt(s)`
    );
  }
  if (diagnostics.lastRetryReason) {
    parts.push(`last SendRequest retry: ${diagnostics.lastRetryReason}`);
  }
  if (diagnostics.elapsedMs !== undefined) {
    parts.push(`${(diagnostics.elapsedMs / 1000).toFixed(1)} s elapsed`);
  }
  if (diagnostics.httpStatus !== undefined) {
    parts.push(`HTTP ${diagnostics.httpStatus}`);
  }
  if (diagnostics.lastStatus) {
    parts.push(`last IBKR status "${diagnostics.lastStatus}"`);
  }
  if (diagnostics.lastErrorCode) {
    parts.push(`IBKR error code ${diagnostics.lastErrorCode}`);
  }
  if (diagnostics.lastBodySnippet) {
    parts.push(`last body: ${diagnostics.lastBodySnippet}`);
  }
  return parts.join(', ');
}

export class FlexTimeoutError extends FlexError {
  readonly attempts: number;
  readonly elapsedMs: number;

  constructor(
    deadlineMs: number,
    attempts: number,
    elapsedMs: number = deadlineMs,
    diagnostics: FlexFailureDiagnostics = {}
  ) {
    const elapsedSeconds = Math.round(elapsedMs / 1000);
    super(
      `Flex fetch timed out after ${elapsedMs} ms, ${attempts} polls (deadline ${deadlineMs} ms).`,
      `IBKR did not deliver the report within ${elapsedSeconds} s after ${attempts} polls. ` +
        'Generate the report in Client Portal to confirm the query works. Shorten the query period, ' +
        'or raise ibkrHistory.retry.deadlineMs.',
      { ...diagnostics, attempts, elapsedMs }
    );
    this.attempts = attempts;
    this.elapsedMs = elapsedMs;
  }
}

export class FlexNetworkError extends FlexError {
  readonly retryable: boolean;

  constructor(detail: string, retryable: boolean, diagnostics: FlexFailureDiagnostics = {}) {
    super(
      `Flex network failure: ${detail}`,
      `Network problem talking to IBKR: ${detail} Check the connection, proxy and firewall, then retry.`,
      diagnostics
    );
    this.retryable = retryable;
  }
}

export class FlexProtocolError extends FlexError {
  readonly retryable: boolean;
  readonly attempts: number;
  readonly elapsedMs: number;
  readonly lastStatus: string;
  readonly lastErrorCode: string;
  readonly lastBodySnippet: string;

  constructor(detail: string, retryable = true, diagnostics: FlexFailureDiagnostics = {}) {
    const summary = describeFailure(diagnostics);
    super(
      `Flex protocol failure: ${detail}${summary ? ` (${summary})` : ''}`,
      `The Flex Web Service returned an unexpected response (${detail}). ` +
        (summary ? `Details: ${summary}. ` : '') +
        'Retry; if it persists the service may be down.',
      diagnostics
    );
    this.retryable = retryable;
    this.attempts = diagnostics.attempts ?? 0;
    this.elapsedMs = diagnostics.elapsedMs ?? 0;
    this.lastStatus = diagnostics.lastStatus ?? '';
    this.lastErrorCode = diagnostics.lastErrorCode ?? '';
    this.lastBodySnippet = diagnostics.lastBodySnippet ?? '';
  }
}

export class FlexParseError extends FlexError {
  readonly reason: string;

  constructor(reason: string, diagnostics: FlexFailureDiagnostics = {}) {
    super(
      `Flex XML could not be parsed: ${reason}`,
      `The Flex report is not valid XML (${reason}). Re-run the query in Client Portal; if that works, save the XML and open an issue.`,
      diagnostics
    );
    this.reason = reason;
  }
}

export class FlexEmptyError extends FlexError {
  constructor(diagnostics: FlexFailureDiagnostics = {}) {
    super(
      'Flex report contained no trade rows (neither <TradeConfirm> nor <Trade>).',
      'The Flex report is valid but contains no trade rows. This extension reads <TradeConfirm> rows ' +
        'from a Trade Confirmation Flex Query and <Trade> rows from an Activity Flex Query. ' +
        'Check that the query contains a "Trade Confirmation" section or a "Trades" section, ' +
        'that the query period covers the requested range, and that the account filter matches the report.',
      diagnostics
    );
  }
}
