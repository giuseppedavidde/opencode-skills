import { FlexApiError, FlexCancelledError, FlexNetworkError, FlexProtocolError, FlexTimeoutError, lookupFlexError } from './errors.ts';
import type { FlexFailureDiagnostics } from './errors.ts';
import { parseEnvelope, parseSendRequestResponse } from './parser.ts';

export const FLEX_BASE_URL = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService';
export const FLEX_DEFAULT_USER_AGENT = 'ibkr-mexem-portfolio-history/0.3 (VS Code extension)';

/** Documented rate limit: 1 request per second, 10 per minute per token. */
export const RATE_LIMIT_DELAY_MS = 60_000;

/** Defaults. The deadline is the authoritative stop; the attempt counter is a safety net. */
export const DEFAULT_DEADLINE_MS = 900_000;
export const DEFAULT_MAX_ATTEMPTS = 120;
export const DEFAULT_INITIAL_DELAY_MS = 2_000;
export const DEFAULT_MAX_DELAY_MS = 20_000;

/**
 * Error 1001 means "statement could not be generated at this time". IBKR asks for
 * a retry after about 10 s. Retries use 10 s, 20 s, then 30 s.
 */
export const DEFAULT_MAX_SEND_ATTEMPTS = 4;
export const SEND_RETRY_STEP_MS = 10_000;
export const SEND_RETRY_MAX_DELAY_MS = 30_000;

/** Maximum number of characters kept from a failing response body. */
export const BODY_SNIPPET_LIMIT = 500;

export interface HttpResponseLike {
  readonly ok: boolean;
  readonly status: number;
  text(): Promise<string>;
}

export type FetchLike = (
  url: string,
  init: { signal?: AbortSignal; headers: Record<string, string> }
) => Promise<HttpResponseLike>;

/** Progress detail handed to {@link FlexClientConfig.onAttempt}. */
export interface AttemptInfo {
  readonly elapsedMs: number;
  readonly lastStatus: string;
  readonly lastErrorCode: string;
}

export interface FlexClientConfig {
  readonly token: string;
  readonly queryId: string;
  readonly baseUrl?: string;
  readonly userAgent?: string;
  readonly requestTimeoutMs?: number;
  readonly deadlineMs?: number;
  readonly maxAttempts?: number;
  /** SendRequest attempts after a transient generation error such as 1001. */
  readonly maxSendAttempts?: number;
  readonly initialDelayMs?: number;
  readonly maxDelayMs?: number;
  readonly minIntervalMs?: number;
  readonly fetchImpl?: FetchLike;
  readonly sleepImpl?: (ms: number, signal?: AbortSignal) => Promise<void>;
  readonly now?: () => number;
  readonly onAttempt?: (attempt: number, maxAttempts: number, detail: string, info: AttemptInfo) => void;
  readonly onSendAttempt?: (attempt: number, maxAttempts: number, detail: string, info: AttemptInfo) => void;
}

export interface FlexFetchResult {
  readonly xml: string;
  readonly referenceCode: string;
  readonly attempts: number;
  readonly requestCount: number;
  readonly durationMs: number;
}

/** Never print a token, a query ID or a full URL: this helper exists for that. */
export function redactSecrets(text: string, secrets: readonly (string | undefined)[]): string {
  let result = text;
  for (const secret of secrets) {
    if (secret && secret.length >= 3) {
      result = result.split(secret).join('***');
    }
  }
  return result.replace(/([?&]t=)[^&\s]+/g, '$1***').replace(/([?&]q=)[^&\s]+/g, '$1***');
}

export function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new FlexCancelledError());
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort(): void {
      clearTimeout(timer);
      reject(new FlexCancelledError());
    }
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

interface RequestBody {
  readonly text: string;
}

export class FlexClient {
  private readonly token: string;
  private readonly queryId: string;
  private readonly baseUrl: string;
  private readonly userAgent: string;
  private readonly requestTimeoutMs: number;
  private readonly deadlineMs: number;
  private readonly maxAttempts: number;
  private readonly maxSendAttempts: number;
  private readonly initialDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly minIntervalMs: number;
  private readonly fetchImpl: FetchLike;
  private readonly sleepImpl: (ms: number, signal?: AbortSignal) => Promise<void>;
  private readonly now: () => number;
  private readonly onAttempt:
    | ((attempt: number, maxAttempts: number, detail: string, info: AttemptInfo) => void)
    | undefined;
  private readonly onSendAttempt:
    | ((attempt: number, maxAttempts: number, detail: string, info: AttemptInfo) => void)
    | undefined;

  private lastRequestAt = 0;
  private requestCount = 0;

  constructor(config: FlexClientConfig) {
    this.token = config.token.trim();
    this.queryId = config.queryId.trim();
    this.baseUrl = (config.baseUrl ?? FLEX_BASE_URL).replace(/\/+$/, '');
    this.userAgent = config.userAgent ?? FLEX_DEFAULT_USER_AGENT;
    this.requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
    this.deadlineMs = Math.max(1, config.deadlineMs ?? DEFAULT_DEADLINE_MS);
    this.maxAttempts = Math.max(1, config.maxAttempts ?? DEFAULT_MAX_ATTEMPTS);
    this.maxSendAttempts = Math.max(1, config.maxSendAttempts ?? DEFAULT_MAX_SEND_ATTEMPTS);
    this.initialDelayMs = Math.max(0, config.initialDelayMs ?? DEFAULT_INITIAL_DELAY_MS);
    this.maxDelayMs = Math.max(this.initialDelayMs, config.maxDelayMs ?? DEFAULT_MAX_DELAY_MS);
    this.minIntervalMs = Math.max(0, config.minIntervalMs ?? 1_100);
    this.fetchImpl = config.fetchImpl ?? ((url, init) => fetch(url, init));
    this.sleepImpl = config.sleepImpl ?? abortableSleep;
    this.now = config.now ?? (() => Date.now());
    this.onAttempt = config.onAttempt;
    this.onSendAttempt = config.onSendAttempt;
  }

  /** Masked description safe to log or show in the UI. */
  describe(): string {
    return (
      `FlexClient(base=${this.baseUrl}, token=***, queryId=***, ` +
      `deadline=${this.deadlineMs}ms, maxAttempts=${this.maxAttempts}, ` +
      `maxSendAttempts=${this.maxSendAttempts})`
    );
  }

  private assertConfig(): void {
    if (!this.token) {
      throw new FlexApiError('1015', 'Flex token is empty.');
    }
    if (!/^\d+$/.test(this.queryId)) {
      throw new FlexApiError('1014', 'Query ID must contain digits only.');
    }
  }

  private async throttle(signal?: AbortSignal): Promise<void> {
    if (this.minIntervalMs <= 0 || this.lastRequestAt === 0) {
      return;
    }
    const waitFor = this.lastRequestAt + this.minIntervalMs - this.now();
    if (waitFor > 0) {
      await this.sleepImpl(waitFor, signal);
    }
  }

  private async request(url: string, signal?: AbortSignal): Promise<RequestBody> {
    if (signal?.aborted) {
      throw new FlexCancelledError();
    }
    const requestStartedAt = this.now();
    const elapsed = (): number => Math.max(0, this.now() - requestStartedAt);
    await this.throttle(signal);
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.requestTimeoutMs);
    const onExternalAbort = (): void => controller.abort();
    signal?.addEventListener('abort', onExternalAbort, { once: true });

    try {
      this.requestCount += 1;
      this.lastRequestAt = this.now();
      const response = await this.fetchImpl(url, {
        signal: controller.signal,
        headers: { 'User-Agent': this.userAgent, Accept: 'text/xml, application/xml, text/plain' }
      });
      const text = await response.text();
      if (!response.ok) {
        const retryable = response.status === 429 || response.status >= 500;
        throw new FlexNetworkError(`HTTP ${response.status} from the Flex Web Service.`, retryable, {
          elapsedMs: elapsed(),
          lastStatus: `HTTP ${response.status}`,
          httpStatus: response.status
        });
      }
      return { text };
    } catch (error) {
      if (error instanceof FlexNetworkError) {
        throw error;
      }
      if (error instanceof FlexCancelledError) {
        throw error;
      }
      if (timedOut) {
        throw new FlexNetworkError(`request timed out after ${this.requestTimeoutMs} ms.`, true, {
          elapsedMs: elapsed(),
          lastStatus: 'timeout'
        });
      }
      if (signal?.aborted) {
        throw new FlexCancelledError();
      }
      const detail = error instanceof Error ? error.message : String(error);
      throw new FlexNetworkError(
        detail.includes('fetch failed') ? `connection failed (${detail}).` : `${detail}.`,
        true,
        { elapsedMs: elapsed(), lastStatus: 'network error' }
      );
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onExternalAbort);
    }
  }

  /** First characters of a failing body, with every secret replaced. */
  private snippet(text: string): string {
    return redactSecrets(text, [this.token, this.queryId]).slice(0, BODY_SNIPPET_LIMIT);
  }

  private info(
    startedAt: number,
    attempts: number,
    lastStatus: string,
    lastErrorCode: string
  ): AttemptInfo {
    return { elapsedMs: Math.max(0, this.now() - startedAt), lastStatus, lastErrorCode };
  }

  private report(
    startedAt: number,
    attempts: number,
    lastStatus: string,
    lastErrorCode: string,
    lastBodySnippet: string,
    extra: Partial<FlexFailureDiagnostics> = {}
  ): FlexFailureDiagnostics {
    return {
      attempts,
      elapsedMs: Math.max(0, this.now() - startedAt),
      lastStatus,
      lastErrorCode,
      lastBodySnippet,
      ...extra
    };
  }

  /**
   * Runs SendRequest and returns a fresh reference code.
   * A transient generation error (1001 and friends) is retried: IBKR asks for a
   * retry, and the response carries no reference code to poll.
   * A second call is also used to recover from error 1017 (expired reference code).
   */
  private async sendRequest(
    signal: AbortSignal | undefined,
    onEnvelope: (status: string, code: string, snippet: string) => void,
    deadlineAt = this.now() + this.deadlineMs
  ): Promise<string> {
    const startedAt = this.now();
    const url = `${this.baseUrl}/SendRequest?t=${encodeURIComponent(this.token)}&q=${encodeURIComponent(this.queryId)}&v=3`;
    let attempt = 0;
    let calls = 0;
    let lastStatus = 'none';
    let lastErrorCode = '';
    let lastRetryReason = '';

    const sendFacts = (snippet: string): Partial<FlexFailureDiagnostics> => ({
      sendAttempts: calls,
      maxSendAttempts: this.maxSendAttempts,
      lastRetryReason: lastRetryReason || undefined,
      lastBodySnippet: snippet
    });

    for (;;) {
      if (signal?.aborted) {
        throw new FlexCancelledError();
      }
      attempt += 1;
      calls += 1;
      this.onSendAttempt?.(attempt, this.maxSendAttempts, 'Requesting statement generation', {
        elapsedMs: Math.max(0, this.now() - startedAt),
        lastStatus: 'SendRequest',
        lastErrorCode
      });
      const body = await this.request(url, signal);
      const snippet = this.snippet(body.text);
      const parsed = parseSendRequestResponse(body.text);

      if (parsed.kind === 'reference') {
        onEnvelope('Success', '', snippet);
        return parsed.referenceCode;
      }
      if (parsed.kind === 'unknown') {
        onEnvelope('unparseable', '', snippet);
        throw new FlexProtocolError(
          parsed.detail,
          true,
          this.report(startedAt, 0, 'unparseable', '', snippet, sendFacts(snippet))
        );
      }

      lastStatus = 'Fail';
      lastErrorCode = parsed.code;
      onEnvelope('Fail', parsed.code, snippet);

      const info = lookupFlexError(parsed.code);
      if (!info?.retryable) {
        throw new FlexApiError(
          parsed.code,
          parsed.message,
          this.report(startedAt, 0, lastStatus, parsed.code, snippet, sendFacts(snippet))
        );
      }

      const rateLimited = parsed.code.trim() === '1018';
      const retryWaitMs = rateLimited
        ? RATE_LIMIT_DELAY_MS
        : Math.min(attempt * SEND_RETRY_STEP_MS, SEND_RETRY_MAX_DELAY_MS);
      lastRetryReason = `IBKR error ${parsed.code} (${info.message})`;
      if (rateLimited) {
        attempt -= 1;
      }

      if (attempt >= this.maxSendAttempts) {
        throw new FlexApiError(
          parsed.code,
          parsed.message,
          this.report(startedAt, 0, lastStatus, parsed.code, snippet, sendFacts(snippet)),
          `Gave up after ${calls} SendRequest attempts; IBKR still could not generate the statement. ` +
            'Wait a few minutes and fetch again.'
        );
      }

      const budget = deadlineAt - this.now();
      if (budget <= 0) {
        throw new FlexTimeoutError(
          this.deadlineMs,
          0,
          this.now() - startedAt,
          this.report(startedAt, 0, lastStatus, parsed.code, snippet, sendFacts(snippet))
        );
      }
      const waitFor = Math.min(retryWaitMs, budget);
      this.onSendAttempt?.(
        attempt,
        this.maxSendAttempts,
        `${rateLimited ? 'IBKR rate limit' : `IBKR error ${parsed.code}`}: retrying in ${Math.ceil(waitFor / 1000)} s`,
        { elapsedMs: Math.max(0, this.now() - startedAt), lastStatus, lastErrorCode: parsed.code }
      );
      await this.sleepImpl(waitFor, signal);
    }
  }

  async fetchStatement(signal?: AbortSignal): Promise<FlexFetchResult> {
    this.assertConfig();
    const startedAt = this.now();
    const deadlineAt = startedAt + this.deadlineMs;
    let attempts = 0;
    let lastStatus = 'none';
    let lastErrorCode = '';

    const remember = (status: string, code: string): void => {
      lastStatus = status;
      lastErrorCode = code;
    };

    let referenceCode = await this.sendRequest(signal, remember, deadlineAt);
    let refreshedReference = false;
    let rateLimited = false;
    let delay = this.initialDelayMs;

    for (;;) {
      if (signal?.aborted) {
        throw new FlexCancelledError();
      }

      const remaining = deadlineAt - this.now();
      if (remaining <= 0) {
        throw new FlexTimeoutError(this.deadlineMs, attempts, this.now() - startedAt, {
          lastStatus,
          lastErrorCode
        });
      }

      const waitFor = Math.min(delay, Math.max(0, remaining));
      this.onAttempt?.(
        attempts + 1,
        this.maxAttempts,
        'Waiting for IBKR to generate the report',
        this.info(startedAt, attempts, lastStatus, lastErrorCode)
      );
      await this.sleepImpl(waitFor, signal);
      if (signal?.aborted) {
        throw new FlexCancelledError();
      }
      const afterWait = this.now();
      if (afterWait >= deadlineAt) {
        throw new FlexTimeoutError(this.deadlineMs, attempts, afterWait - startedAt, {
          lastStatus,
          lastErrorCode
        });
      }

      attempts += 1;
      this.onAttempt?.(
        attempts,
        this.maxAttempts,
        'Retrieving statement',
        this.info(startedAt, attempts, lastStatus, lastErrorCode)
      );
      const getUrl = `${this.baseUrl}/GetStatement?t=${encodeURIComponent(this.token)}&q=${encodeURIComponent(referenceCode)}&v=3`;
      const body = await this.request(getUrl, signal);
      const snippet = this.snippet(body.text);
      const envelope = parseEnvelope(body.text);

      if (envelope.kind === 'report') {
        return {
          xml: envelope.xml,
          referenceCode,
          attempts,
          requestCount: this.requestCount,
          durationMs: this.now() - startedAt
        };
      }

      if (envelope.kind === 'unsupported') {
        throw new FlexProtocolError(
          envelope.detail,
          false,
          this.report(startedAt, attempts, lastStatus, lastErrorCode, snippet)
        );
      }

      if (envelope.kind === 'unknown') {
        remember('unparseable', '');
      }

      if (envelope.kind === 'error') {
        remember(envelope.code ? 'Fail' : 'unknown', envelope.code);

        // 1017 means the reference code expired. Obtain a new one once and keep going.
        if (envelope.code.trim() === '1017' && !refreshedReference) {
          refreshedReference = true;
          this.onAttempt?.(
            attempts,
            this.maxAttempts,
            'Reference code expired, requesting a new one',
            this.info(startedAt, attempts, lastStatus, lastErrorCode)
          );
          referenceCode = await this.sendRequest(signal, remember, deadlineAt);
          delay = this.initialDelayMs;
          continue;
        }

        const info = lookupFlexError(envelope.code);
        if (!info?.retryable) {
          throw new FlexApiError(
            envelope.code,
            envelope.message,
            this.report(startedAt, attempts, lastStatus, envelope.code, snippet)
          );
        }
        if (envelope.code.trim() === '1018') {
          // Documented rate limit. Wait a full minute and do not spend the poll budget.
          // The full minute is a protocol requirement, so maxDelayMs must not clip it.
          attempts = Math.max(0, attempts - 1);
          delay = RATE_LIMIT_DELAY_MS;
          rateLimited = true;
        }
      }

      if (attempts >= this.maxAttempts) {
        throw new FlexProtocolError(
          `the statement was still not ready after ${attempts} polls`,
          true,
          this.report(startedAt, attempts, lastStatus, lastErrorCode, snippet)
        );
      }
      if (rateLimited) {
        rateLimited = false;
      } else {
        delay = Math.min(Math.round(delay * 1.5) + 50, this.maxDelayMs);
      }
    }
  }
}
