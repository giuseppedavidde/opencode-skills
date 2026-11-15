/**
 * Shared portfolio context between the Portfolio surfaces and the chat view.
 *
 * The store is deliberately free of `vscode`: the extension layer subscribes to
 * {@link PortfolioContextStore.onDidChange} and forwards the change to the
 * webview. `node:test` can therefore cover it without a host.
 */
import type { DatasetPayload } from '../panel/protocol.ts';

export type PortfolioContextListener = (dataset: DatasetPayload | undefined) => void;

export class PortfolioContextStore {
  private dataset: DatasetPayload | undefined;
  /** Local time of the last successful `set`, or `undefined` before any fetch. */
  private fetchedAtDate: Date | undefined;
  private readonly listeners: PortfolioContextListener[] = [];

  get(): DatasetPayload | undefined {
    return this.dataset;
  }

  get fetchedAt(): Date | undefined {
    return this.fetchedAtDate;
  }

  /** Replace the dataset the chat sees. `undefined` clears it (no fetch yet). */
  set(dataset: DatasetPayload | undefined): void {
    this.dataset = dataset;
    this.fetchedAtDate = dataset ? new Date() : undefined;
    for (const listener of [...this.listeners]) {
      listener(this.dataset);
    }
  }

  /** Subscribe; returns an unsubscribe function. Never throws on a bad listener. */
  onDidChange(listener: PortfolioContextListener): () => void {
    this.listeners.push(listener);
    return () => {
      const index = this.listeners.indexOf(listener);
      if (index >= 0) {
        this.listeners.splice(index, 1);
      }
    };
  }

  get listenerCount(): number {
    return this.listeners.length;
  }
}
