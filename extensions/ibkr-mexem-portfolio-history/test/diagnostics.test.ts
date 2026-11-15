import assert from 'node:assert/strict';
import test from 'node:test';
import { FlexApiError, FlexEmptyError, FlexNetworkError } from '../src/flex/errors.ts';
import type { DiagnosticsInput } from '../src/panel/diagnostics.ts';
import { buildDiagnosticsReport, failureFactsOf, maskToken } from '../src/panel/diagnostics.ts';

const TOKEN = '528191644107458877539776';
const QUERY_ID = '1659819';
const REFERENCE = '7729029235';

function report(snippet: string, secrets: readonly string[] = []): string {
  return buildDiagnosticsReport({
    extensionVersion: '0.2.0',
    baseUrl: 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService',
    tokenLength: TOKEN.length,
    queryIdDigits: QUERY_ID.length,
    elapsedMs: 91_500,
    attempts: 27,
    maxAttempts: 120,
    lastStatus: 'Fail',
    lastErrorCode: '1019',
    bodySnippet: snippet,
    referenceCode: REFERENCE,
    secrets
  });
}

test('the diagnostics report carries the facts needed to debug a failure', () => {
  const text = report('<FlexStatementResponse><ErrorCode>1019</ErrorCode></FlexStatementResponse>');
  assert.match(text, /Extension version: 0\.2\.0/);
  assert.match(text, /Base URL: https:\/\/ndcdyn\.interactivebrokers\.com/);
  assert.match(text, /Flex token: set, 24 characters/);
  assert.match(text, /Query ID: 7 digits/);
  assert.match(text, /Elapsed: 91\.5 s/);
  assert.match(text, /Polls: 27 of 120/);
  assert.match(text, /Last IBKR error code: 1019/);
  assert.match(text, /1019/);
});

test('the token, query id and reference code never appear in diagnostics', () => {
  const text = report(
    `GET /GetStatement?t=${TOKEN}&q=${REFERENCE}&v=3 body=${TOKEN} query=${QUERY_ID} ref=${REFERENCE}`,
    [TOKEN, QUERY_ID]
  );
  assert.equal(text.includes(TOKEN), false, 'the token must never be copied');
  assert.equal(text.includes(QUERY_ID), false, 'the query id must never be copied');
  assert.equal(text.includes(REFERENCE), false, 'the reference code must never be copied');
  assert.match(text, /t=\*\*\*/);
});

test('a snippet is capped at 500 characters', () => {
  const text = report('x'.repeat(5_000));
  const snippetLine = text.split('\n').at(-1) ?? '';
  assert.equal(snippetLine.length, 500);
});

test('maskToken reports the length only', () => {
  assert.equal(maskToken(0), 'absent');
  assert.match(maskToken(24), /24 characters/);
});

/* ------------------------------------------------------------------ *
 * Every Flex error fills `diagnostics`, so network and empty-report   *
 * failures produce a report with real facts instead of zeros.         *
 * ------------------------------------------------------------------ */

function reportFromError(error: FailureInput, extra: Partial<DiagnosticsInput> = {}): string {
  const facts = failureFactsOf(error);
  return buildDiagnosticsReport({
    extensionVersion: '0.3.0',
    baseUrl: 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService',
    tokenLength: TOKEN.length,
    queryIdDigits: QUERY_ID.length,
    elapsedMs: facts.elapsedMs,
    attempts: facts.attempts,
    maxAttempts: 120,
    sendAttempts: facts.sendAttempts,
    maxSendAttempts: facts.maxSendAttempts,
    lastRetryReason: facts.lastRetryReason,
    deadlineMs: 900_000,
    lastStatus: facts.lastStatus,
    lastErrorCode: facts.lastErrorCode,
    bodySnippet: facts.bodySnippet,
    referenceCode: REFERENCE,
    secrets: [TOKEN, QUERY_ID],
    ...extra
  });
}

type FailureInput = Parameters<typeof failureFactsOf>[0];

test('a network failure produces a report with elapsed time, polls and the snippet', () => {
  const error = new FlexNetworkError('HTTP 503 from the Flex Web Service.', true, {
    attempts: 2,
    elapsedMs: 1_200,
    lastStatus: 'HTTP 503',
    httpStatus: 503,
    lastBodySnippet: '<html>upstream error</html>'
  });
  const text = reportFromError(error, { queryType: 'AF' });
  assert.match(text, /Elapsed: 1\.2 s/);
  assert.match(text, /Polls: 2 of 120/);
  assert.match(text, /Last IBKR status: HTTP 503/);
  assert.match(text, /upstream error/);
  assert.match(text, /Query type: AF/);
});

test('an empty report produces a report with zero rows and the body snippet', () => {
  const error = new FlexEmptyError({
    attempts: 5,
    elapsedMs: 300_000,
    lastStatus: 'report',
    lastErrorCode: '',
    lastBodySnippet: `<FlexQueryResponse type="AF"><FlexStatements count="227" /></FlexQueryResponse>`
  });
  const text = reportFromError(error, { queryType: 'AF', rowsParsed: 0 });
  assert.match(text, /Elapsed: 300\.0 s/);
  assert.match(text, /Polls: 5 of 120/);
  assert.match(text, /Last IBKR status: report/);
  assert.match(text, /Query type: AF/);
  assert.match(text, /Rows parsed: 0/);
  assert.match(text, /FlexStatements count=/);
});

test('the snippet of a network or empty failure is still redacted', () => {
  const error = new FlexEmptyError({
    attempts: 1,
    elapsedMs: 1_000,
    lastStatus: 'report',
    lastBodySnippet: `GET /GetStatement?t=${TOKEN}&q=${REFERENCE}&v=3 query=${QUERY_ID}`
  });
  const text = reportFromError(error, { rowsParsed: 0 });
  assert.equal(text.includes(TOKEN), false, 'the token must never be copied');
  assert.equal(text.includes(QUERY_ID), false, 'the query id must never be copied');
  assert.equal(text.includes(REFERENCE), false, 'the reference code must never be copied');
  assert.match(text, /t=\*\*\*/);
});

test('an API error keeps its code when the diagnostics carry none', () => {
  const facts = failureFactsOf(new FlexApiError('1015', 'Token is invalid.'));
  assert.equal(facts.lastErrorCode, '1015');
  assert.equal(facts.attempts, 0);

  const withFacts = failureFactsOf(
    new FlexApiError('1012', 'Token has expired.', {
      attempts: 3,
      elapsedMs: 9_000,
      lastStatus: 'Fail',
      lastErrorCode: '',
      lastBodySnippet: '<FlexStatementResponse>'
    })
  );
  assert.equal(withFacts.lastErrorCode, '1012', 'the code is the fallback');
  assert.equal(withFacts.attempts, 3);
});

test('a 1001 failure reports SendRequest attempts separately from polls', () => {
  const error = new FlexApiError('1001', 'Statement could not be generated at this time.', {
    attempts: 0,
    sendAttempts: 4,
    maxSendAttempts: 4,
    lastRetryReason: 'IBKR error 1001 (Statement could not be generated at this time.)',
    elapsedMs: 60_000,
    lastStatus: 'Fail',
    lastErrorCode: '1001',
    lastBodySnippet: '<FlexStatementResponse><ErrorCode>1001</ErrorCode></FlexStatementResponse>'
  });
  const text = reportFromError(error);
  assert.match(text, /Polls: 0 of 120/);
  assert.match(text, /SendRequest attempts: 4 of 4/);
  assert.match(text, /Last retry reason: IBKR error 1001/);
  assert.match(text, /Deadline remaining: 840\.0 s/);
  assert.match(text, /Last IBKR error code: 1001/);
});

test('SendRequest facts are absent when the failure never reached the service', () => {
  const text = reportFromError(new FlexNetworkError('connection reset.', true, {
    elapsedMs: 500,
    lastStatus: 'network error'
  }));
  assert.equal(text.includes('SendRequest attempts:'), false);
  assert.equal(text.includes('Last retry reason:'), false);
});
