/**
 * The only chat module that starts a process. It reuses the existing local
 * trading CLI:
 *
 *   <python> -m trading_mcp.trading_cli fetch options <TICKER> --expiry <DATE>
 *
 * One child process per distinct `ticker|expiry` pair, `execFile` with no
 * shell, an in-memory cache of 10 minutes and no thrown error: a failing
 * command becomes an `errors` entry.
 */
import { execFile } from 'node:child_process';
import {
  buildFetchArgs,
  chainKey,
  MARKET_DATA_CONCURRENCY,
  MAX_MARKET_DATA_REQUESTS,
  parseChainJson,
  parseMarketDataCommand
} from './marketData.ts';
import type { ChainData, MarketDataError } from './marketData.ts';

/** A fetch takes 10 s to 20 s on this machine; a stuck command stops here. */
export const DEFAULT_MARKET_DATA_TIMEOUT_MS = 30_000;

/** The cache reuses a chain for ten minutes. */
export const MARKET_DATA_CACHE_TTL_MS = 10 * 60_000;

export interface MarketDataRun {
  readonly stdout: string;
  readonly stderr: string;
  readonly code: number;
}

export type MarketDataRunner = (
  command: string,
  args: readonly string[],
  timeoutMs: number
) => Promise<MarketDataRun>;

export interface MarketDataServiceOptions {
  /** Whitespace-separated template of `ibkrHistory.chat.marketDataCommand`. */
  readonly commandTemplate: string;
  readonly timeoutMs?: number;
  /** Injected by the tests; the default calls `execFile`. */
  readonly runner?: MarketDataRunner;
  /** Injected clock, in epoch milliseconds. */
  readonly now?: () => number;
}

export interface MarketDataRequest {
  readonly ticker: string;
  readonly expiry: string;
}

export interface MarketDataResult {
  readonly chains: Map<string, ChainData>;
  readonly errors: readonly MarketDataError[];
  /** ISO time of the end of the fetch. */
  readonly fetchedAt: string;
  /** Number of distinct `ticker|expiry` pairs of this call. */
  readonly requested: number;
  /** Keys left out by {@link MAX_MARKET_DATA_REQUESTS}. */
  readonly omitted: readonly string[];
}

const MAX_BUFFER = 8 * 1024 * 1024;

const defaultRunner: MarketDataRunner = (command, args, timeoutMs) =>
  new Promise<MarketDataRun>((resolve) => {
    execFile(
      command,
      [...args],
      { timeout: timeoutMs, maxBuffer: MAX_BUFFER, shell: false, windowsHide: true },
      (error, stdout, stderr) => {
        const failure = error as (Error & { code?: unknown; killed?: boolean }) | null;
        const rawCode = failure?.code;
        const code =
          failure === null || failure === undefined
            ? 0
            : typeof rawCode === 'number'
              ? rawCode
              : failure.killed === true
                ? -1
                : 1;
        resolve({
          stdout: typeof stdout === 'string' ? stdout : '',
          stderr: typeof stderr === 'string' ? stderr : '',
          code
        });
      }
    );
  });

/** First 200 characters of stderr on one line. stdout is never logged. */
function stderrSnippet(stderr: string): string {
  const text = stderr.trim().replace(/\s+/g, ' ');
  return text.length === 0 ? '' : `: ${text.slice(0, 200)}`;
}

export class MarketDataService {
  private readonly commandTemplate: string;
  private readonly timeoutMs: number;
  private readonly runner: MarketDataRunner;
  private readonly now: () => number;
  private readonly cache = new Map<string, { readonly chain: ChainData; readonly at: number }>();

  constructor(options: MarketDataServiceOptions) {
    this.commandTemplate = options.commandTemplate;
    this.timeoutMs = Math.max(1000, Math.trunc(options.timeoutMs ?? DEFAULT_MARKET_DATA_TIMEOUT_MS));
    this.runner = options.runner ?? defaultRunner;
    this.now = options.now ?? Date.now;
  }

  get cacheSize(): number {
    return this.cache.size;
  }

  /** Drop every cached chain. The provider rebuilds the service when the command changes. */
  clear(): void {
    this.cache.clear();
  }

  /**
   * Fetch every chain of `requests` in parallel, from the cache when it is
   * younger than ten minutes. Never throws.
   */
  async fetchChains(requests: readonly MarketDataRequest[]): Promise<MarketDataResult> {
    const unique: MarketDataRequest[] = [];
    const seen = new Set<string>();
    for (const request of requests) {
      const key = chainKey(request.ticker, request.expiry);
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      unique.push({ ticker: request.ticker, expiry: request.expiry });
    }

    const selected = unique.slice(0, MAX_MARKET_DATA_REQUESTS);
    const omitted = unique
      .slice(MAX_MARKET_DATA_REQUESTS)
      .map((request) => chainKey(request.ticker, request.expiry));
    const errors: MarketDataError[] = [];
    const chains = new Map<string, ChainData>();
    const startedAt = this.now();
    const fetchedAt = new Date(startedAt).toISOString();
    const resolved = parseMarketDataCommand(this.commandTemplate);

    if (!resolved) {
      for (const request of selected) {
        errors.push({ ticker: request.ticker, message: `${request.expiry}: ibkrHistory.chat.marketDataCommand is empty.` });
      }
      return { chains, errors, fetchedAt, requested: unique.length, omitted };
    }

    const pending = [...selected];
    const worker = async (): Promise<void> => {
      for (let request = pending.shift(); request !== undefined; request = pending.shift()) {
        const key = chainKey(request.ticker, request.expiry);
        const cached = this.cache.get(key);
        if (cached && startedAt - cached.at < MARKET_DATA_CACHE_TTL_MS) {
          chains.set(key, cached.chain);
          continue;
        }
        const args = buildFetchArgs(resolved.baseArgs, request.ticker, request.expiry);
        if (!args) {
          errors.push({ ticker: request.ticker, message: `${request.expiry}: ${request.ticker} is not a valid ticker.` });
          continue;
        }
        try {
          const run = await this.runner(resolved.command, args, this.timeoutMs);
          if (run.code !== 0) {
            errors.push({
              ticker: request.ticker,
              message: `${request.expiry}: the trading CLI exited with code ${run.code}${stderrSnippet(run.stderr)}`
            });
            continue;
          }
          const chain = parseChainJson(run.stdout, request.ticker);
          if (!chain) {
            errors.push({
              ticker: request.ticker,
              message: `${request.expiry}: the trading CLI output is not a JSON option chain${stderrSnippet(run.stderr)}`
            });
            continue;
          }
          chains.set(key, chain);
          this.cache.set(key, { chain, at: startedAt });
        } catch (error) {
          errors.push({
            ticker: request.ticker,
            message: `${request.expiry}: ${error instanceof Error ? error.message : String(error)}`
          });
        }
      }
    };

    const workers = Array.from(
      { length: Math.min(MARKET_DATA_CONCURRENCY, selected.length) },
      () => worker()
    );
    await Promise.all(workers);

    return { chains, errors, fetchedAt, requested: unique.length, omitted };
  }
}
