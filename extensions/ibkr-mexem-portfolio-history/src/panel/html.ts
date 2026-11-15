import { randomBytes } from 'node:crypto';
import * as vscode from 'vscode';

export const FLEX_DOCS_URL = 'https://www.interactivebrokers.com/campus/ibkr-api-page/flex-web-service/';
export const CLIENT_PORTAL_FLEX_URL = 'https://portal.interactivebrokers.com/portal/#/main/reports/flexQueries';

export function renderHtml(webview: vscode.Webview, extensionUri: vscode.Uri): string {
  const nonce = randomBytes(16).toString('base64');
  const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', 'webview.js'));
  const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, 'media', 'webview.css'));
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
    "connect-src 'none'",
    "form-action 'none'",
    "base-uri 'none'"
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${styleUri}" />
  <title>IBKR Portfolio History</title>
</head>
<body>
  <header class="topbar">
    <div>
      <h1>IBKR Mexem Portfolio History</h1>
      <p class="subtitle" id="header-summary">Flex Web Service &middot; realized P&amp;L only</p>
    </div>
    <div id="currency-switch" class="currency-switch hidden" role="group" aria-label="Realized P&amp;L currency">
      <span class="currency-switch-label">P&amp;L currency</span>
      <div id="currency-buttons" class="segmented"></div>
    </div>

    <div class="topbar-actions">
      <button id="btn-docs" class="ghost" type="button">Flex docs</button>
      <button id="btn-clear" class="ghost danger" type="button">Clear credentials</button>
    </div>
  </header>

  <section class="card" aria-labelledby="settings-title">
    <h2 id="settings-title">Connection</h2>
    <form id="settings-form" novalidate>
      <div class="grid">
        <label class="field">
          <span>Flex token</span>
          <input id="token" type="password" autocomplete="off" spellcheck="false" placeholder="stored in VS Code SecretStorage" />
          <small id="token-hint" class="hint">Create it in Client Portal &rarr; Reporting &rarr; Flex Queries &rarr; Flex Web Service Configuration.</small>
        </label>
        <label class="field">
          <span>Query ID</span>
          <input id="queryId" type="text" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="e.g. 1234567" />
          <small id="queryId-hint" class="hint">Numeric ID from the Flex query info panel.</small>
        </label>
        <label class="field">
          <span>Date range</span>
          <select id="preset">
            <option value="ytd">Year to date</option>
            <option value="last30">Last 30 days</option>
            <option value="last90">Last 90 days</option>
            <option value="last365">Last 365 days</option>
            <option value="custom">Custom range</option>
          </select>
          <small class="hint">Filtering happens locally on the downloaded report.</small>
        </label>
        <label class="field">
          <span>Account filter (optional)</span>
          <input id="accountId" type="text" autocomplete="off" spellcheck="false" placeholder="all accounts" />
          <small class="hint">Exact match, case-insensitive, e.g. U1234567.</small>
        </label>
        <label class="field hidden" id="custom-start-field">
          <span>Start date</span>
          <input id="customStart" type="date" />
        </label>
        <label class="field hidden" id="custom-end-field">
          <span>End date</span>
          <input id="customEnd" type="date" />
        </label>
      </div>

      <p class="notice" id="range-notice">
        The Flex Web Service does not accept a date range in the request. The saved query defines the period;
        this extension filters the returned trades locally. Set the query period to <strong>Year To Date</strong>
        (or "Last 365 days") in Client Portal.
      </p>

      <div class="actions">
        <button id="btn-fetch" type="submit" class="primary">Fetch report</button>
        <button id="btn-cancel" type="button" class="ghost" disabled>Cancel</button>
        <button id="btn-export" type="button" class="ghost" disabled>Export CSV</button>
        <span id="status" class="status" role="status" aria-live="polite"></span>
      </div>
      <p id="range-hint" class="hint hidden" role="note">Large ranges can take several minutes in IBKR.</p>
      <div id="progress" class="progress hidden" role="progressbar" aria-valuetext="Fetching report">
        <div class="bar"><div id="progress-bar"></div></div>
        <span id="progress-text"></span>
        <span id="progress-meta" class="hint"></span>
      </div>
    </form>
  </section>

  <section id="error-box" class="alert error hidden" role="alert"></section>
  <div id="error-actions" class="actions hidden">
    <button id="btn-copy-diagnostics" type="button" class="ghost">Copy diagnostics</button>
  </div>
  <section id="warning-box" class="alert warn hidden" role="alert"></section>
  <section id="info-box" class="alert info hidden" role="status"></section>
  <section id="base-currency-banner" class="alert info hidden" role="note"></section>

  <section id="results" class="hidden">
    <div class="card">
      <div class="result-head">
        <h2>Summary</h2>
        <span id="base-currency-label" class="hint"></span>
      </div>
      <div id="stats-grid" class="stats-grid"></div>
      <p id="pnl-source-note" class="hint"></p>
    </div>

    <div class="card">
      <h2>Cumulative realized P&amp;L</h2>
      <div class="chart-wrap"><canvas id="chart-equity" role="img" aria-label="Cumulative realized profit and loss over time"></canvas></div>
    </div>

    <div class="card">
      <h2>Drawdown of cumulative realized P&amp;L</h2>
      <div class="chart-wrap"><canvas id="chart-drawdown" role="img" aria-label="Drawdown of the cumulative realized profit and loss curve"></canvas></div>
    </div>

    <div class="two-col">
      <div class="card">
        <h2>Monthly realized P&amp;L</h2>
        <div class="chart-wrap"><canvas id="chart-monthly" role="img" aria-label="Monthly realized profit and loss bars"></canvas></div>
      </div>
      <div class="card">
        <h2>P&amp;L by symbol (top 20)</h2>
        <div class="chart-wrap"><canvas id="chart-symbol" role="img" aria-label="Realized profit and loss by symbol"></canvas></div>
      </div>
    </div>

    <div class="card">
      <h2>Trade P&amp;L distribution</h2>
      <div class="chart-wrap"><canvas id="chart-histogram" role="img" aria-label="Distribution of realized profit and loss per trade"></canvas></div>
    </div>

    <div class="card">
      <div class="result-head">
        <h2>Trades in range</h2>
        <span id="trades-caption" class="hint"></span>
      </div>
      <p id="trades-truncation-note" class="hint warn-text hidden" role="note"></p>
      <div id="trades-controls" class="table-controls">
        <label class="inline-field">
          <span>Filter</span>
          <input id="trades-filter" type="search" autocomplete="off" spellcheck="false" placeholder="symbol, side, source" />
        </label>
        <label class="inline-field">
          <span>Rows per page</span>
          <select id="trades-page-size">
            <option value="50">50</option>
            <option value="100" selected>100</option>
            <option value="250">250</option>
            <option value="all">All</option>
          </select>
        </label>
        <div class="pager">
          <button id="trades-prev" type="button" class="ghost">&#8249; Prev</button>
          <span id="trades-counter" class="hint">Showing 0&ndash;0 of 0</span>
          <button id="trades-next" type="button" class="ghost">Next &#8250;</button>
        </div>
        <span id="trades-rendering" class="hint hidden">Rendering&hellip;</span>
      </div>
      <div class="table-wrap">
        <table id="trades-table">
          <thead>
            <tr>
              <th class="sortable" data-sort="date" tabindex="0" aria-sort="descending" scope="col">Date <span class="sort-arrow"></span></th>
              <th scope="col">Time</th>
              <th class="sortable" data-sort="symbol" tabindex="0" scope="col">Symbol <span class="sort-arrow"></span></th>
              <th scope="col">Side</th>
              <th class="sortable num" data-sort="quantity" tabindex="0" scope="col">Qty <span class="sort-arrow"></span></th>
              <th class="sortable num" data-sort="price" tabindex="0" scope="col">Price <span class="sort-arrow"></span></th>
              <th scope="col">Trade ccy</th>
              <th class="sortable num" data-sort="pnl" tabindex="0" id="th-realized-pnl" scope="col"><span id="th-realized-pnl-label">Realized P&amp;L (base)</span> <span class="sort-arrow"></span></th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>Commissions by trade currency</h2>
      <div class="table-wrap">
        <table id="commissions-table">
          <thead>
            <tr><th>Trade ccy</th><th class="num">Trades</th><th class="num">Commission (trade ccy)</th><th class="num">Estimate in base (report FX rate)</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <p id="commission-note" class="hint"></p>
    </div>
  </section>

  <footer class="footer">
    <span>No telemetry. Credentials never leave this machine except in requests to IBKR.</span>
  </footer>

  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
}
