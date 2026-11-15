import assert from 'node:assert/strict';
import test from 'node:test';
import type { FetchLike, FlexClientConfig, HttpResponseLike } from '../src/flex/client.ts';
import { FlexClient, redactSecrets } from '../src/flex/client.ts';
import { FlexApiError, FlexCancelledError, FlexNetworkError, FlexProtocolError, FlexTimeoutError } from '../src/flex/errors.ts';

const SEND_OK =
  "<FlexStatementResponse timestamp='now'><Status>Success</Status><ReferenceCode>999000111</ReferenceCode><url>legacy</url></FlexStatementResponse>";
const NOT_READY =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage></FlexStatementResponse>";
const REPORT = '<?xml version="1.0"?><FlexQueryResponse><FlexStatements><FlexStatement><Trades><TradeConfirm symbol="AAPL" /></Trades></FlexStatement></FlexStatements></FlexQueryResponse>';
const TOKEN_EXPIRED =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>";
const TOKEN_INVALID =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1015</ErrorCode><ErrorMessage>Token is invalid.</ErrorMessage></FlexStatementResponse>";

interface Scripted {
  readonly fetchImpl: FetchLike;
  readonly calls: string[];
}

function scripted(responses: (string | { status: number })[]): Scripted {
  const calls: string[] = [];
  let index = 0;
  const fetchImpl: FetchLike = async (url: string) => {
    calls.push(url);
    const item = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (typeof item === 'object') {
      return { ok: false, status: item.status, text: async () => '' };
    }
    const body = item ?? '';
    return { ok: true, status: 200, text: async () => body } satisfies HttpResponseLike;
  };
  return { fetchImpl, calls };
}

function client(overrides: { fetchImpl: FetchLike; now?: () => number; sleepImpl?: (ms: number, signal?: AbortSignal) => Promise<void>; [key: string]: unknown }): FlexClient {
  return new FlexClient({
    token: '528191644107458877539776',
    queryId: '800969',
    minIntervalMs: 0,
    initialDelayMs: 1,
    maxAttempts: 5,
    deadlineMs: 60_000,
    sleepImpl: async () => undefined,
    ...overrides
  } as FlexClientConfig);
}

test('polls through 1019 until the report is ready', async () => {
  const script = scripted([SEND_OK, NOT_READY, NOT_READY, REPORT]);
  const result = await client({ fetchImpl: script.fetchImpl }).fetchStatement();
  assert.equal(result.referenceCode, '999000111');
  assert.equal(result.attempts, 3);
  assert.match(result.xml, /FlexQueryResponse/);
  assert.equal(script.calls.length, 4);
  assert.match(script.calls[0] ?? '', /SendRequest\?t=/);
  assert.match(script.calls[1] ?? '', /GetStatement\?t=.*q=999000111&v=3/);
});

test('a non-retryable GetStatement error aborts immediately', async () => {
  const script = scripted([SEND_OK, TOKEN_INVALID]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexApiError);
      assert.equal(error.code, '1015');
      assert.equal(error.retryable, false);
      return true;
    }
  );
  assert.equal(script.calls.length, 2);
});

test('SendRequest failures are surfaced without polling', async () => {
  const script = scripted([TOKEN_EXPIRED]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(),
    (error: unknown) => error instanceof FlexApiError && error.code === '1012'
  );
  assert.equal(script.calls.length, 1);
});

test('gives up after maxAttempts with a protocol error', async () => {
  const script = scripted([SEND_OK, NOT_READY]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 3 }).fetchStatement(),
    (error: unknown) => error instanceof FlexProtocolError
  );
  assert.equal(script.calls.length, 4, 'one SendRequest plus three GetStatement polls');
});

test('an unparseable body is retried and then fails closed', async () => {
  const script = scripted([SEND_OK, '<html>503 gateway</html>']);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 2 }).fetchStatement(),
    (error: unknown) => error instanceof FlexProtocolError
  );
});

test('unparseable body followed by a report still succeeds', async () => {
  const script = scripted([SEND_OK, '<html>slow</html>', REPORT]);
  const result = await client({ fetchImpl: script.fetchImpl }).fetchStatement();
  assert.equal(result.attempts, 2);
});

test('hard deadline produces a timeout error', async () => {
  let clock = 0;
  const script = scripted([SEND_OK, NOT_READY]);
  await assert.rejects(
    () =>
      client({
        fetchImpl: script.fetchImpl,
        deadlineMs: 10,
        initialDelayMs: 1000,
        now: () => clock,
        sleepImpl: async (ms: number) => {
          clock += ms;
        }
      }).fetchStatement(),
    (error: unknown) => error instanceof FlexTimeoutError
  );
});

test('pre-aborted signal cancels before any HTTP call', async () => {
  const script = scripted([SEND_OK, REPORT]);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(controller.signal),
    (error: unknown) => error instanceof FlexCancelledError
  );
  assert.equal(script.calls.length, 0);
});

test('http status errors are typed', async () => {
  const script = scripted([{ status: 401 }]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(),
    (error: unknown) => error instanceof FlexNetworkError && error.retryable === false
  );
  const serverError = scripted([{ status: 503 }]);
  await assert.rejects(
    () => client({ fetchImpl: serverError.fetchImpl, maxAttempts: 2 }).fetchStatement(),
    (error: unknown) => error instanceof FlexNetworkError && error.retryable === true
  );
});

test('invalid query id never reaches the network', async () => {
  const script = scripted([SEND_OK]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, queryId: 'not-a-number' }).fetchStatement(),
    (error: unknown) => error instanceof FlexApiError && error.code === '1014'
  );
  assert.equal(script.calls.length, 0);
});

test('empty token never reaches the network', async () => {
  const script = scripted([SEND_OK]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, token: '   ' }).fetchStatement(),
    (error: unknown) => error instanceof FlexApiError && error.code === '1015'
  );
  assert.equal(script.calls.length, 0);
});

test('redaction removes tokens and query parameters', () => {
  const token = '528191644107458877539776';
  const text = `GET /SendRequest?t=${token}&q=800969&v=3 token=${token}`;
  const redacted = redactSecrets(text, [token]);
  assert.equal(redacted.includes(token), false);
  assert.equal(redacted.includes('800969'), false);
  assert.match(redacted, /t=\*\*\*/);
  assert.match(redacted, /q=\*\*\*/);
});

test('describe never exposes credentials', () => {
  const description = client({ fetchImpl: scripted([SEND_OK]).fetchImpl }).describe();
  assert.equal(description.includes('528191644107458877539776'), false);
  assert.equal(description.includes('800969'), false);
  assert.match(description, /token=\*\*\*/);
});

/* ------------------------------------------------------------------ *
 * Regression tests for the reported failure: a Year-To-Date report    *
 * needs minutes, so the deadline must stop the fetch, not the counter. *
 * ------------------------------------------------------------------ */

const RATE_LIMITED =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1018</ErrorCode><ErrorMessage>Too many requests.</ErrorMessage></FlexStatementResponse>";
const REFERENCE_INVALID =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1017</ErrorCode><ErrorMessage>Reference code is invalid.</ErrorMessage></FlexStatementResponse>";

test('twenty 1019 responses followed by a report still succeed', async () => {
  const responses = [SEND_OK, ...Array.from({ length: 20 }, () => NOT_READY), REPORT];
  const script = scripted(responses);
  const result = await client({ fetchImpl: script.fetchImpl, maxAttempts: 120 }).fetchStatement();
  assert.equal(result.attempts, 21, 'every 1019 is one poll');
  assert.match(result.xml, /FlexQueryResponse/);
  assert.equal(script.calls.length, 22);
});

test('the default attempt budget no longer aborts before the deadline', () => {
  const defaults = new FlexClient({
    token: '528191644107458877539776',
    queryId: '800969',
    fetchImpl: scripted([SEND_OK]).fetchImpl
  });
  const description = defaults.describe();
  assert.match(description, /deadline=900000ms/);
  assert.match(description, /maxAttempts=120/);
});

test('1018 waits a full minute and does not consume the poll budget', async () => {
  // A fake clock keeps the expected wait exact: the deadline must not clip it here.
  let clock = 0;
  const waits: number[] = [];
  const script = scripted([SEND_OK, RATE_LIMITED, REPORT]);
  const result = await client({
    fetchImpl: script.fetchImpl,
    maxAttempts: 1,
    initialDelayMs: 2_000,
    maxDelayMs: 20_000,
    deadlineMs: 1_800_000,
    now: () => clock,
    sleepImpl: async (ms: number) => {
      waits.push(ms);
      clock += ms;
    }
  }).fetchStatement();
  assert.equal(result.attempts, 1, 'the rejected 1018 poll is refunded');
  assert.deepEqual(waits, [2_000, 60_000], 'maxDelayMs must not clip the documented 60 s rate-limit wait');
  assert.match(result.xml, /FlexQueryResponse/);
});

test('1017 triggers exactly one automatic SendRequest retry', async () => {
  const script = scripted([SEND_OK, REFERENCE_INVALID, SEND_OK, REPORT]);
  const result = await client({ fetchImpl: script.fetchImpl, maxAttempts: 5 }).fetchStatement();
  assert.match(result.xml, /FlexQueryResponse/);
  assert.equal(script.calls.length, 4);
  assert.match(script.calls[0] ?? '', /SendRequest\?t=/);
  assert.match(script.calls[1] ?? '', /GetStatement\?t=.*q=999000111&v=3/);
  assert.match(script.calls[2] ?? '', /SendRequest\?t=/, 'second SendRequest for a fresh reference code');
  assert.match(script.calls[3] ?? '', /GetStatement\?t=.*q=999000111&v=3/);
});

test('a second 1017 fails instead of looping', async () => {
  const script = scripted([SEND_OK, REFERENCE_INVALID, SEND_OK, REFERENCE_INVALID]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 20 }).fetchStatement(),
    (error: unknown) => error instanceof FlexApiError && error.code === '1017'
  );
  assert.equal(script.calls.length, 4);
});

test('the deadline error reports elapsed seconds and polls', async () => {
  let clock = 0;
  const script = scripted([SEND_OK, NOT_READY]);
  await assert.rejects(
    () =>
      client({
        fetchImpl: script.fetchImpl,
        deadlineMs: 1_000,
        initialDelayMs: 500,
        now: () => clock,
        sleepImpl: async (ms: number) => {
          clock += ms;
        }
      }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexTimeoutError);
      assert.match(error.userMessage, /within 1 s after 1 polls/);
      assert.equal(error.elapsedMs, 1_000);
      assert.equal(error.attempts, 1);
      return true;
    }
  );
});

test('a protocol error carries the last IBKR status, code and snippet', async () => {
  const script = scripted([SEND_OK, NOT_READY]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 1, initialDelayMs: 1 }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexProtocolError);
      assert.equal(error.lastStatus, 'Fail');
      assert.equal(error.lastErrorCode, '1019');
      assert.match(error.lastBodySnippet, /1019/);
      assert.equal(error.retryable, true);
      assert.match(error.userMessage, /1 poll/);
      assert.match(error.userMessage, /error code 1019/);
      return true;
    }
  );
});

test('the failure snippet never contains the token or query id', async () => {
  const leaked = `<?xml version="1.0"?><html><body>GET /GetStatement?t=528191644107458877539776&amp;q=800969&amp;v=3</body></html>`;
  const script = scripted([SEND_OK, leaked]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 1, initialDelayMs: 1 }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexProtocolError);
      assert.equal(error.lastBodySnippet.includes('528191644107458877539776'), false);
      assert.equal(error.lastBodySnippet.includes('800969'), false);
      assert.equal(error.userMessage.includes('528191644107458877539776'), false);
      return true;
    }
  );
});

test('a CSV report is rejected as non-retryable instead of polled for minutes', async () => {
  const csv = '"ClientAccountID","CurrencyPrimary","Symbol"\n"U1234567","USD","AAPL"\n';
  const script = scripted([SEND_OK, csv]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxAttempts: 50, initialDelayMs: 1 }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexProtocolError);
      assert.equal(error.retryable, false);
      assert.match(error.userMessage, /not XML/);
      return true;
    }
  );
  assert.equal(script.calls.length, 2, 'no further polling after a CSV body');
});

/* ------------------------------------------------------------------ *
 * Diagnostics must never be discarded: a SendRequest failure and an   *
 * HTTP failure both fill the common `diagnostics` object.             *
 * ------------------------------------------------------------------ */

test('a SendRequest API error keeps the status, code and body snippet', async () => {
  const script = scripted([TOKEN_INVALID]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexApiError);
      assert.equal(error.diagnostics.lastStatus, 'Fail');
      assert.equal(error.diagnostics.lastErrorCode, '1015');
      assert.match(error.diagnostics.lastBodySnippet ?? '', /Token is invalid/);
      return true;
    }
  );
});

test('an HTTP failure carries the status and the request elapsed time', async () => {
  const script = scripted([{ status: 503 }]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexNetworkError);
      assert.equal(error.diagnostics.httpStatus, 503);
      assert.equal(error.diagnostics.lastStatus, 'HTTP 503');
      assert.equal(typeof error.diagnostics.elapsedMs, 'number');
      return true;
    }
  );
});

/* ------------------------------------------------------------------ *
 * Error 1001 is transient: IBKR asks for a retry and returns no      *
 * reference code, so SendRequest itself must be retried.             *
 * ------------------------------------------------------------------ */

const GENERATION_FAILED =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1001</ErrorCode><ErrorMessage>Statement could not be generated at this time. Please try again shortly.</ErrorMessage></FlexStatementResponse>";
const STATEMENT_UNAVAILABLE =
  "<FlexStatementResponse timestamp='now'><Status>Fail</Status><ErrorCode>1003</ErrorCode><ErrorMessage>Statement is not available.</ErrorMessage></FlexStatementResponse>";

test('1001 retries SendRequest after 10 s and then succeeds', async () => {
  let clock = 0;
  const waits: number[] = [];
  const script = scripted([GENERATION_FAILED, SEND_OK, REPORT]);
  const result = await client({
    fetchImpl: script.fetchImpl,
    maxSendAttempts: 4,
    initialDelayMs: 1,
    now: () => clock,
    sleepImpl: async (ms: number) => {
      waits.push(ms);
      clock += ms;
    }
  }).fetchStatement();

  assert.equal(result.referenceCode, '999000111');
  assert.equal(result.attempts, 1, 'only the GetStatement poll is counted');
  assert.deepEqual(waits, [10_000, 1], 'the 10 s SendRequest retry, then the first poll delay');
  assert.equal(script.calls.length, 3);
  assert.match(script.calls[0] ?? '', /SendRequest\?t=/);
  assert.match(script.calls[1] ?? '', /SendRequest\?t=/);
  assert.match(script.calls[2] ?? '', /GetStatement\?t=.*q=999000111&v=3/);
});

test('1001 exhausts maxSendAttempts with 10 s, 20 s and 30 s waits', async () => {
  let clock = 0;
  const waits: number[] = [];
  const script = scripted([GENERATION_FAILED]);
  await assert.rejects(
    () =>
      client({
        fetchImpl: script.fetchImpl,
        maxSendAttempts: 4,
        deadlineMs: 900_000,
        now: () => clock,
        sleepImpl: async (ms: number) => {
          waits.push(ms);
          clock += ms;
        }
      }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexApiError);
      assert.equal(error.code, '1001');
      assert.equal(error.retryable, true);
      assert.equal(error.diagnostics.attempts, 0, 'no GetStatement poll was made');
      assert.equal(error.diagnostics.sendAttempts, 4);
      assert.equal(error.diagnostics.maxSendAttempts, 4);
      assert.match(error.diagnostics.lastRetryReason ?? '', /1001/);
      assert.match(error.userMessage, /1001/);
      assert.match(error.userMessage, /4 SendRequest attempts/);
      return true;
    }
  );
  assert.deepEqual(waits, [10_000, 20_000, 30_000]);
  assert.equal(script.calls.length, 4);
  assert.equal(script.calls.every((url) => url.includes('SendRequest')), true);
});

test('1018 on SendRequest waits 60 s and does not spend a generation attempt', async () => {
  let clock = 0;
  const waits: number[] = [];
  const script = scripted([RATE_LIMITED, SEND_OK, REPORT]);
  const result = await client({
    fetchImpl: script.fetchImpl,
    maxSendAttempts: 1,
    deadlineMs: 900_000,
    initialDelayMs: 1,
    now: () => clock,
    sleepImpl: async (ms: number) => {
      waits.push(ms);
      clock += ms;
    }
  }).fetchStatement();

  assert.equal(result.referenceCode, '999000111');
  assert.deepEqual(waits, [60_000, 1]);
  assert.equal(script.calls.length, 3);
});

test('a definitive SendRequest error is never retried', async () => {
  const script = scripted([STATEMENT_UNAVAILABLE]);
  await assert.rejects(
    () => client({ fetchImpl: script.fetchImpl, maxSendAttempts: 4 }).fetchStatement(),
    (error: unknown) => {
      assert.ok(error instanceof FlexApiError);
      assert.equal(error.code, '1003');
      assert.equal(error.retryable, false);
      assert.equal(error.diagnostics.sendAttempts, 1);
      return true;
    }
  );
  assert.equal(script.calls.length, 1);
});
