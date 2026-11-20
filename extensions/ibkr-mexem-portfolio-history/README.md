# IBKR Mexem Portfolio History

A VS Code extension. It downloads an IBKR Flex Query report. It shows realized P&L charts and portfolio statistics for a date range that you choose.

It reads both a **Trade Confirmation Flex Query** (`<TradeConfirm>` rows) and an **Activity Flex Query** with `type="AF"` (`<Trade>` rows).

- No IB Trader Workstation. No TWS API. No 2FA automation.
- No telemetry. No remote scripts. All chart code is bundled locally.
- Credentials are stored in VS Code SecretStorage.

---

## 1. Requirements

| Item | Version |
| --- | --- |
| VS Code | 1.90 or newer |
| Node | 22.18 or newer for development and tests. 20.3 or newer only to run the bundled extension |
| IBKR account | Flex Web Service enabled |

The extension needs **two values** from IBKR Client Portal:

1. A **Flex Web Service token**.
2. A numeric **Query ID** for one saved Flex query.

IBKR does **not** allow username/password login for programmatic report download. Username plus 2FA cannot be automated. This extension does not try. See section 6.

---

## 2. Install

### 2.1 Development (F5)

```bash
git clone <this folder>
cd ibkr-mexem-portfolio-history
npm install
npm run compile
```

Open the folder in VS Code and press `F5`. A second VS Code window starts with the extension loaded. Run **IBKR History: Open Portfolio Panel** from the Command Palette.

### 2.2 Packaged

```bash
npm run package                    # production bundle, minified
npx @vscode/vsce package           # writes ibkr-mexem-portfolio-history-0.4.1.vsix
code --install-extension ibkr-mexem-portfolio-history-0.4.1.vsix
```

---

## 3. Create the Flex token (Client Portal)

1. Log in to Client Portal with the username that owns the Flex queries.
2. Click **Performance & Reports**.
3. Click **Flex Queries**.
4. Click **Flex Web Service Configuration** (gear icon, right side).
5. Enable **Flex Web Service Status** and click **Save**.
6. Copy **Current Token**.
7. Optional: click **Generate A New Token** to set the lifetime (6 hours to 1 year) and an IP allow-list.
8. Paste the token into the extension panel.

Notes:
- A new token invalidates the old token.
- Restricted IPs cause Flex error `1013`.
- The token stays valid for the configured lifetime. Flex error `1012` means it expired.

---

## 4. Create the Flex query

Use a **Trade Confirmation Flex Query** or an **Activity Flex Query**. Both give per-execution rows. Section 4.1 lists the difference. A Trade Confirmation query also carries `openCloseIndicator` and `orderReference`.

1. Go to **Performance & Reports** -> **Flex Queries**.
2. In **Trade Confirmation Flex Query** (or **Activity Flex Query**), click the **+** icon.
3. Set **Query Name** (for example `mexem-trades`).
4. Set **Period** to **Year To Date**. See section 5 for the reason.
5. Set **Format** to **XML**.
6. Set **Include Audit Trail Fields** to **Yes**. This is required for `orderReference`.
7. In **Sections**, select only **Trades**.
8. In the **Trades** section, enable these fields:

   `accountId`, `symbol`, `description`, `assetCategory`, `currency`, `exchange`,
   `tradeDate`, `tradeTime`, `buySell`, `quantity`, `tradePrice`, `proceeds`,
   `commission`, `netCash`, `openCloseIndicator`, `fifoPnlRealized`, `orderReference`

   An Activity query names the commission field `ibCommission` and always sends `dateTime` instead of `tradeTime`. Select `ibCommission` there. See section 4.1.

9. Save the query.
10. Click the **i** icon next to the query name. Copy the numeric **Query ID**.
11. Paste the Query ID into the extension panel.

Recommended but optional: `openDate` or `openDateTime`. The extension computes the average holding period only when the report carries an opening date. Standard Trade Confirmation reports do not include it, so the metric shows `n/a`.

### 4.1 Supported Flex query types

The extension reads two report shapes. Both arrive as XML and both are parsed locally.

| Query type | Row element | What the row carries |
| --- | --- | --- |
| Activity Flex Query (`type="AF"`) | `<Trade accountId="…" … />` | One row per execution. The commission is `ibCommission`. There is no `openCloseIndicator` and no `orderReference`. The report holds one `FlexStatement` per day, so rows are collected from **every** statement and de-duplicated by `tradeID` then `transactionID`. |
| Trade Confirmation Flex Query | `<TradeConfirm accountId="…" … />` | One row per execution. The commission is `commission`. `openCloseIndicator` and `orderReference` are present when those fields are enabled. |

Both shapes work in the same build. The output channel logs the detected type once per fetch, for example `Detected Flex query type: AF (declared type="AF")`, and the diagnostics report repeats it.

An Activity query needs one extra step for the date: `tradeDate` plus `dateTime` (format `20260102;135015`) supply the row timestamp. The extension also accepts `2026-01-02` and `10:05:00`.

---

## 5. The date-range limitation (important)

**Confirmed fact:** the Flex Web Service request accepts **no date-range parameter**.

The request is:

```text
GET https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t=<TOKEN>&q=<QUERY_ID>&v=3
```

The only parameters are `t` (token), `q` (query ID) and `v` (version, must be `3`). The period comes from the saved query.

The IBKR documentation also warns:

> Flex queries using a variable duration, such as "Last N Days" will always use the maximum possible days for a given request, rather than following the last used number of days in Client Portal. It is recommended to use the precise request values such as "Last Month", "Last Quarter", "Year To Date", etc.

Therefore this extension does what it can, and says so:

1. It sends **no** fake date parameters. Probing undocumented parameters would risk Flex error `1020` and is not attempted.
2. It downloads the report that the saved query produces.
3. It filters the rows **locally** to the range you pick in the panel.
4. The panel shows a permanent notice: *"Filtering happens locally on the downloaded report."*
5. The result warnings always repeat the exact local window applied.

Consequences:

- If the saved query period is **shorter** than the range you select, older trades are missing. The extension cannot detect this. It does report the first and last trade date it received when the selection is empty.
- If the saved query period is **longer**, extra rows are downloaded and then discarded. That is safe, only slower.
- Recommended setting: **Period = Year To Date**, or **Last 365 days** for a rolling window.

### 5.1 What was verified, and where

Source, verified 2026-11-14:
`https://www.interactivebrokers.com/campus/ibkr-api-page/flex-web-service/`

The live URL above currently redirects to a 404 page. The content was read from the Internet Archive snapshot of 2026-06-17 of the same page, and cross-checked against the Client Portal guide `https://www.ibkrguides.com/clientportal/performanceandstatements/flex-web-service.htm`.

Confirmed from that documentation:

| Fact | Value |
| --- | --- |
| Send request endpoint | `/AccountManagement/FlexWebService/SendRequest` |
| Parameters | `t` = token, `q` = query ID, `v` = 3 (required) |
| Retrieve endpoint | `/AccountManagement/FlexWebService/GetStatement` |
| Retrieve parameters | `t` = token, `q` = ReferenceCode, `v` = 3 |
| Required header | `User-Agent` on every request |
| Rate limit | 1 request per second, 10 per minute per token (error `1018`) |
| Ready signal | `ErrorCode 1019` = "Statement generation in progress" |
| Success envelope | `FlexStatementResponse` with `Status`, `ReferenceCode`, legacy `url` |
| Failure envelope | `FlexStatementResponse` with `Status`, `ErrorCode`, `ErrorMessage` |
| Error codes | `1001` to `1021`, see section 9 |
| Date range in request | **not supported** |
| Data freshness | Trade Confirmation: 5 to 10 minutes after execution. Activity Statement: once per business day |

A live probe on 2026-11-14 with a dummy token returned exactly the documented failure envelope:

```xml
<FlexStatementResponse timestamp='14 November, 2026 07:08 AM EST'>
<Status>Fail</Status>
<ErrorCode>1020</ErrorCode>
<ErrorMessage>Invalid request or unable to validate request.</ErrorMessage>
</FlexStatementResponse>
```

---

## 6. Security

- The token and the Query ID are stored with `context.secrets` (**VS Code SecretStorage**). They live in the OS keyring, not in `settings.json`.
- SecretStorage scope is the VS Code profile, not the workspace. Close the folder and the credentials remain.
- The token is never sent back to the webview. The panel only receives booleans (`hasToken`) and a masked Query ID.
- The token is never logged. All log output goes through a redaction helper that replaces `t=` and `q=` URL values and the token value.
- The full report XML is never logged and never written to disk unless you export the CSV.
- No telemetry, no analytics, no remote code. The webview content security policy is `default-src 'none'` with a per-render nonce. Chart.js is bundled into `media/webview.js`.
- Revoke access at any time: **IBKR History: Clear Stored Flex Credentials**, or Client Portal -> **Generate A New Token**.

Non-secret options only are in `settings.json`, all under `ibkrHistory.*`: retry attempts, delays, deadline, request timeout, and the P&L fallback switch.

---

## 7. Using the panel

1. Run **IBKR History: Open Portfolio Panel**, or click the **IBKR Portfolio** icon in the Activity Bar.
2. Paste the token. Leave the field empty to reuse a stored token.
3. Type the Query ID, or leave it empty to reuse a stored one.
4. Choose a range: YTD, last 30/90/365 days, or a custom start and end.
5. Optional: type an account ID to keep one account only. The match is exact and case-insensitive.
6. Click **Fetch report**. The notification shows progress. Click **Cancel** to abort.
7. Read realized P&L in the account base currency. The report supplies it; see section 7.4.
8. Use the controls above the **Trades in range** table to filter, sort and page through every trade. See section 7.8.
9. Click **Export CSV** to write the full filtered set to a file. The export is never limited to the visible page.

### 7.1 Charts

| Chart | Content |
| --- | --- |
| Cumulative realized P&L | Running sum of realized P&L per closing trade |
| Drawdown | Distance below the running peak of that curve |
| Monthly realized P&L | Sum per calendar month |
| P&L by symbol | Top 20 symbols by P&L, best and worst tails |
| Trade P&L distribution | Histogram of realized P&L per trade, 24 bins |

### 7.2 Statistics and definitions

| Statistic | Definition |
| --- | --- |
| Total realized P&L | Sum of per-trade realized P&L |
| Gross profit / gross loss | Sum of positive / negative per-trade values |
| Profit factor | gross profit / abs(gross loss). `∞` when there is no losing trade |
| Win rate | winning trades / trades with realized P&L |
| Average / largest win, loss | Descriptive statistics on the same per-trade values |
| Commissions by trade currency | Sum of absolute commissions per trade currency, plus an estimated base-currency total |
| Average holding period | Mean of `tradeDate - openDate`, only when the report has opening dates |
| Best / worst symbol | Symbol with the highest / lowest sum of realized P&L |
| Max drawdown | Lowest point of the cumulative curve below its running peak, amount and percent of peak |
| Sharpe-like | `mean(daily realized P&L) / stdev(daily realized P&L) * sqrt(252)` |

**Sharpe-like assumption.** The value uses daily realized P&L in account currency, not daily returns. There is no risk-free rate and no equity denominator. It is a consistency measure of your realized results, **not** a portfolio Sharpe ratio.

### 7.3 How realized P&L is derived

Per row, in this order:

1. Use `fifoPnlRealized` when the field has a value. IBKR sends it on closing trades, net of commissions.
2. Else, for a closing row (`openCloseIndicator` is `C`, `C;O`, or `CLOSE`), use the closing leg's `netCashInBase`. IBKR already converted it to the base currency. Those rows are marked `pnlSource = proceeds`. When `netCashInBase` is missing or zero, the row uses `netCash` only if the trade currency IS the base currency. Otherwise the row stays unknown.
3. Else the row has no realized P&L (`pnlSource = none`). Opening trades are not losses.

A value is used once. The same row never contributes both `fifoPnlRealized` and a fallback figure. The panel reports how many rows used each source. The fallback never mixes a trade-currency amount into a base-currency field.

**The zero-FIFO rule for Activity rows.** An Activity query (`type="AF"`) has no `openCloseIndicator`. IBKR writes `fifoPnlRealized="0"` on rows whose cost basis is not closed, so a zero there is not a result. For a row with no close indicator:

- a **non-zero** `fifoPnlRealized` becomes the realized P&L (`pnlSource = fifo`);
- an **exactly zero** `fifoPnlRealized` becomes unknown: `realizedPnl = null`, `pnlSource = none`.

This keeps a "not closed yet" zero out of the win rate, the profit factor and the equity curve. A Trade Confirmation row behaves differently, because its `openCloseIndicator` is authoritative: a closing row keeps `0` as a real result.

You can disable step 2 with `ibkrHistory.pnl.fallbackFromProceeds = false`. The rows then become unknown and leave the statistics. The approximation uses `netCashInBase`, so it is in the base currency. It is not an IBKR figure.

### 7.4 Currency semantics

**IBKR reports realized P&L in the account base currency. It does not report it in the trade currency.** The `currency` attribute of a trade is the TRADE currency only. Read this section before you change a formatter.

#### Which field is in which currency

| Field | Currency |
| --- | --- |
| `fifoPnlRealized` | account base currency |
| `capitalGainsPnl` | account base currency |
| `fxPnl` | account base currency |
| `netCashInBase` | account base currency |
| `cost` | account base currency |
| `proceeds`, `netCash`, `ibCommission`, `tradePrice` | trade currency (`currency`) |

#### Proof from a real Activity report

Account `U16517211`, base currency EUR. Row `AMD 261218P00300000`, SELL to open and BUY to close:

```
<Trade symbol="AMD   261218P00300000" buySell="BUY" quantity="1" tradePrice="0.71"
       proceeds="-71" netCash="-71.7" netCashInBase="-64.856235"
       fifoPnlRealized="756.800887" capitalGainsPnl="793.83308"
       fxPnl="-37.032193" currency="USD" />
<Trade symbol="AMD   261218P00300000" buySell="SELL" quantity="-1" tradePrice="9.5"
       proceeds="950" netCash="949.3" netCashInBase="821.657122"
       fifoPnlRealized="0" currency="USD" />
```

The two sums agree to the last digit:

1. `capitalGainsPnl + fxPnl = 793.83308 - 37.032193 = 756.800887`
2. `netCashInBase(sell to open) - |netCashInBase(buy to close)| = 821.657122 - 64.856235 = 756.800887`
3. Both equal `fifoPnlRealized = 756.800887`.

A trade-currency reading gives a different number. The `currency="USD"` attribute applies to `netCash` and `ibCommission` only. The report confirms the base currency: every one of its 8853 `<ConversionRate>` rows has `toCurrency="EUR"`.

#### How the extension detects the base currency

1. The `ibkrHistory.baseCurrency` setting, when it is not `auto`.
2. `<AccountInformation currency="...">`, when the query returns it.
3. The `toCurrency` of every `<ConversionRate>` row. All rows must agree. On disagreement the extension uses the most frequent value and logs a warning in the output channel.
4. Else `UNKNOWN`. The panel then renders `1234.56 base`. It never renders a dollar sign.

#### What the panel shows

- One P&L series in the selected currency: summary statistics, cumulative curve, drawdown, monthly bars, P&L by symbol and histogram. Section 7.5 explains the currency switch.
- The trade table keeps a **Trade ccy** column. The **Realized P&L** column follows the selected currency.
- A banner names the base currency when it differs from a trade currency.
- Commissions stay per trade currency, in the **Commissions by trade currency** table.
- The base-currency commission total is an estimate (report FX rate). It converts each trade with the `ConversionRate` whose `reportDate` is closest to that trade. It is never exact.

### 7.5 P&L in trade currency

The report carries `<ConversionRate>` rows, so the panel can also express realized P&L in a trade currency. The two totals answer two different questions. They are **not** the same number in different units.

#### Rate direction

One row means: one unit of `fromCurrency` is `rate` units of `toCurrency`.

```
<ConversionRate reportDate="20260630" fromCurrency="USD" toCurrency="EUR" rate="0.87554" />
```

This reads **1 USD = 0.87554 EUR**. To turn a base-currency amount into USD, **divide by the rate**. To turn a USD amount into EUR, multiply by the rate.

#### Formula

```
realized P&L in the trade currency = capitalGainsPnl / rate(tradeCcy → base, tradeDate)
```

`capitalGainsPnl` is base currency and excludes the FX result. Dividing by the rate of the trade date removes both the base-currency unit and the FX effect.

**Do not use `fifoPnlRealized / rate`.** `fifoPnlRealized` already contains `fxPnl`, so that division counts the FX effect twice and gives a different, wrong number.

#### Exactness proof

Real row `LHX 270115C00370000`, closing leg on 20260630, account base currency EUR:

```
tradeDate="20260630" currency="USD" ibCommission="-0.7"
fifoPnlRealized="2881.630354" capitalGainsPnl="2936.168699" fxPnl="-54.538345"
```

| Step | Value |
| --- | --- |
| `capitalGainsPnl + fxPnl = 2936.168699 - 54.538345` | `2881.630354` = `fifoPnlRealized` |
| Rate on 20260630 (`USD → EUR`) | `0.87554` |
| `2936.168699 / 0.87554` | **3353.5517 USD** |
| `2881.630354 / 0.87554` (wrong rule) | 3291.2607 USD |
| Cross-check: `−Σ netCash` over the full open + close round trip | `3353.5518 USD` |

The correct rule and the cash cross-check agree within 0.0001. The wrong rule is off by 62 USD on this row alone.

#### The FX effect

For the same report:

| Aggregate | Value |
| --- | --- |
| `Σ fifoPnlRealized` (base, **includes** FX) | `4585.0542 EUR` |
| `Σ capitalGainsPnl` (base, **excludes** FX) | `4727.9276 EUR` |
| `Σ fxPnl` | `−142.8734 EUR` |
| Identity | `4585.0542 = 4727.9276 − 142.8734` |

- The **EUR base** view includes the FX result.
- The **USD** view excludes the FX result.
- The difference is the FX effect, not a rounding error and not a unit conversion.

The panel shows two cards in every view: **P&L excluding FX** (`Σ capitalGainsPnl`) and **FX result** (`Σ fxPnl`). Both stay in the base currency.

#### The switch

The header carries the segmented control `P&L currency: [EUR base] [USD]`. The options are the base currency first, then every trade currency of the dataset whose pair with the base currency has a rate.

When you switch, these follow:

1. The statistics cards.
2. The cumulative curve and the drawdown curve.
3. The monthly bars, the P&L by symbol and the histogram.
4. The **Realized P&L** column of the trades table, with its header text.
5. The `realized_pnl_<Ccy>` column of the CSV export.

The column header is explicit: `Realized P&L (EUR base, including FX)` or `Realized P&L (USD, excluding FX)`. The **Trade ccy** column never changes.

#### Derivation cases

| Case | Value | `basis` | `exact` |
| --- | --- | --- | --- |
| Target is the base currency | `fifoPnlRealized` | `base` | true |
| Target is the trade currency, `capitalGainsPnl` present | `capitalGainsPnl / rate` | `no-fx` | true |
| Target is the trade currency, `capitalGainsPnl` absent | `fifoPnlRealized / rate` | `no-fx` | **false** |
| Any other target | `fifoPnlRealized × rate(base → target)` | `derived` | **false** |
| No usable rate | `n/a` | any | false |

Non-exact rows carry a `~` marker in the table. Hover it to read the reason. Rows with no realized P&L stay empty in every currency.

#### Missing rates

- An exact `reportDate` match wins.
- Without an exact match the table uses the row with the nearest **earlier** report date. A later row is never used.
- No earlier row means no rate. The row shows `n/a`, leaves the statistics of that view, and the panel warns `N trade(s) could not be converted to USD`. The count is always reported, never hidden.
- No row for the currency pair means no rate. The extension never guesses a cross rate through a third currency.

#### Setting

| Setting | Default | Meaning |
| --- | --- | --- |
| `ibkrHistory.displayCurrency` | `base` | Currency of the P&L series. `base` is the account base currency, which includes the FX result. An ISO 4217 code such as `USD` is the trade-currency view, which excludes it. An explicit non-base value wins over the last choice made in the panel |

The panel writes the last choice to `globalState` per user, so it survives a reload.

#### CSV columns

The export keeps the historical columns and adds one:

| Column | Currency |
| --- | --- |
| `fifoPnlRealized` | base |
| `realizedPnl` | base (same figure as `fifoPnlRealized` when IBKR supplies it) |
| `realized_pnl_<Ccy>` | the display currency of the panel, for example `realized_pnl_USD` |

`realizedPnl` and `realized_pnl_<Ccy>` are both written, so a reader can compare the two questions without recomputing a rate.

### 7.6 Activity Bar icon

The extension adds one icon to the left Activity Bar. The title is **IBKR Portfolio**. Click the icon to open the **Portfolio** sidebar view.

- The sidebar view and the editor tab share the same HTML, message protocol and analytics code. One controller serves both surfaces.
- The sidebar is narrow. The charts scale down. Use the editor tab when you need width.
- The view keeps its charts and its last dataset when you switch to another sidebar container. The provider registers with `retainContextWhenHidden: true`.
- The icon is `media/activitybar-icon.svg`. It uses `fill="currentColor"`, so it follows the active theme.
- The five commands keep their behaviour. If the editor tab is open, the commands target the editor tab. Else they target the sidebar view.

### 7.7 Retry settings

The time limit decides when a fetch stops. The attempt counter is a safety net only. A large Flex report can take several minutes to generate at IBKR, so the default limits are generous.

| Setting | Default | Range | Meaning |
| --- | --- | --- | --- |
| `ibkrHistory.retry.deadlineMs` | `900000` (15 min) | 30000 – 3600000 | Hard time limit for the whole fetch: SendRequest plus every GetStatement poll. This is the authoritative stop |
| `ibkrHistory.retry.maxAttempts` | `120` | 5 – 1000 | Safety net on the number of GetStatement polls. SendRequest attempts and error 1018 do not use one |
| `ibkrHistory.retry.maxSendAttempts` | `4` | 1 – 10 | SendRequest attempts after a transient generation error such as `1001`. Waits 10 s, 20 s, then 30 s |
| `ibkrHistory.retry.initialDelayMs` | `2000` | 250 – 60000 | Delay before the first poll. IBKR allows 1 request per second per token |
| `ibkrHistory.retry.maxDelayMs` | `20000` | 1000 – 120000 | Upper bound for the growing delay. Growth factor is 1.5 |
| `ibkrHistory.baseCurrency` | `auto` | `auto`, `EUR`, `USD`, `GBP`, `CHF` | Account base currency used to label P&L. `auto` reads the report. Set another ISO 4217 code in `settings.json` to override detection |

Three IBKR answers are handled without spending the poll budget as a failure:

- **1001 (statement could not be generated).** SendRequest returns no reference code. The extension sends SendRequest again after 10 s, 20 s, and 30 s. The limit is `ibkrHistory.retry.maxSendAttempts`. The poll counter counts GetStatement calls only.
- **1018 (rate limit).** The extension waits the full documented 60 s, then continues. The attempt is refunded.
- **1017 (reference code expired).** The extension sends the request again automatically, once, to obtain a fresh reference code. A second 1017 fails.

The delay after error 1018 is a protocol requirement, so `ibkrHistory.retry.maxDelayMs` does not clip it.

Errors 1003, 1010, 1011, 1012, 1013, 1014, 1015, 1016, 1017 and 1020 are definitive. The extension does not retry them. The diagnostics report shows the code and an actionable hint.

Error 1019 is not a rate limit. It means "statement generation in progress". The extension polls GetStatement with the normal growing delay.

Every failure path fills the same diagnostics object. A network error, an exhausted deadline, an empty report and a protocol error all report elapsed time and poll count, so **Copy diagnostics** is never empty. See section 7.7.

### 7.8 Copy diagnostics

When a fetch fails, the panel shows an error and a **Copy diagnostics** button. The same report is available as the command **IBKR History: Copy Diagnostics Report**.

The report goes to the clipboard and contains:

- extension version and the Flex base URL;
- the token as a length only, for example `set, 24 characters (not shown)`;
- the Query ID as a digit count only;
- elapsed seconds, GetStatement polls, SendRequest attempts, the last retry reason, the remaining deadline, the last IBKR status and error code;
- the detected query type (`AF`, `TradeConfirm`, or absent when unknown);
- `Rows parsed: 0` when the report was valid but held no trade rows;
- the first 500 characters of the last response.

The token, the Query ID and the reference code are replaced before the text is built, so none of them can reach the clipboard. Paste the report into an issue instead of a screenshot of the error.

### 7.9 Trades in range

The **Trades in range** card lists every trade of the selected range, newest first by default. It is not a "latest 50" list any more.

| Control | Behaviour |
| --- | --- |
| Filter | Case-insensitive text match on symbol, side (`BUY` / `SELL`) and P&L source (`fifo`, `proceeds`, `none`). The counter shows the filtered total |
| Rows per page | `50`, `100`, `250` or `All`. Default `100` |
| `‹ Prev` / `Next ›` | Move one page. Disabled at the first and the last page |
| Counter | `Showing 1–100 of 412`, where 412 is the filtered row count |
| Date, Symbol, Qty, Price, Realized P&L | Click a header to sort. Click again to reverse. An arrow marks the active column. Date starts descending, every other column starts ascending |

`All` renders in chunks of 500 rows per animation frame and shows `Rendering…` until the last chunk is appended, so the sidebar does not freeze. The table scrolls both vertically and horizontally, and the header stays sticky. The controls wrap on a narrow sidebar.

**Payload ceiling.** The webview receives every filtered trade up to `maxTradeRows`, a safety ceiling that defaults to 5000 rows. The charts, the statistics and the CSV export always use the full filtered set; only the table payload is capped. When the cap applies:

- the caption reads `Rows shown 5000 of 6000 in range`;
- a warning names `maxTradeRows` and the real total;
- `meta.rowsInRange` still reports the real total, never the capped count.

Narrow the date range or the account filter to see trades beyond the ceiling in the table. The CSV export is unaffected: it always writes every filtered row.

---

## 8. Trade Chat

The **Trade Chat** view lives in the same **IBKR Portfolio** Activity Bar container as the panel. It talks to the `trade` analyst persona and already holds the **Trades in range** dataset in context. You can ask about realized P&L, symbols, drawdown, monthly results and the trade list without pasting any data.

Open it with the Activity Bar icon, or run **IBKR History: Open Trade Chat**.

With `ibkrHistory.chat.marketData` on, the context also carries the live option prices of the open option positions (§8.6). **Open in @trade** writes the same context to a file and opens the `@trade` agent on it.

### 8.1 Setup: the two backends

The chat has two backends. `ibkrHistory.chat.backend` selects one of them.

**`lm` (default, primary).** The extension uses the **VS Code Language Model API**. The model dropdown is filled from `vscode.lm.selectChatModels()`. A message runs on the Copilot or opencode-go subscription that is already signed in to VS Code, for example through the `onesoftqwq.opencode-go-copilot-provider` extension. **No API key is needed.** If the list is empty, the view says so: install and sign in to a language model provider, or switch the backend to `http`.

**`http` (secondary).** The extension posts to `{baseUrl}/chat/completions` with an API key. It looks for the key in this order and uses the first match:

| Order | Source | How to set it |
| --- | --- | --- |
| 1 | VS Code SecretStorage, key `ibkrHistory.chat.apiKey` | Run **IBKR History: Set Chat API Key**. The input is masked. Delete it with **IBKR History: Clear Chat API Key** |
| 2 | Environment variable `OPENCODE_API_KEY` | Set it in the shell that launches VS Code |
| 3 | `~/.local/share/opencode/auth.json`, entry `opencode-go.key` | Read-only. The extension never writes this file. A missing file, invalid JSON or a missing entry is ignored |

The key never reaches the webview, never appears in an error message and is never logged. **IBKR History: Set Chat API Key** stores it in the OS keyring through SecretStorage. The `lm` backend ignores the key completely.

### 8.2 Models

In `lm` mode the dropdown is **dynamic**. It lists the models that `vscode.lm.selectChatModels()` returns for this VS Code profile. The label is the model `name`, then the `family`, then the raw id. Duplicate ids are removed and the list is sorted by label. Changing the dropdown writes `ibkrHistory.chat.model`, which is a **preference**: an id that the provider does not expose falls back to an exact `family` match, then to the first available model.

In `http` mode the dropdown is the fixed fallback list of the provider: `glm-5.3`, `glm-5.2`, `glm-5.1`, `kimi-k2.7-code`, `kimi-k2.6`, `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp`, `deepseek-v4-pro`, `mimo-v2.5`, `mimo-v2.5-pro`, `minimax-m3`, `minimax-m2.7`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.6-plus`. That list is deprecated: it exists only for the `http` backend.

### 8.3 Privacy

> **`lm`: Portfolio data is sent to the VS Code language model provider. Option prices, when enabled, come from yfinance.**
>
> **`http`: Portfolio data is sent to opencode.ai. Option prices, when enabled, come from yfinance.**

The notice under the header always matches the active backend. The first send asks for consent in a modal dialog. The dialog names the destination and lists what leaves the machine: symbols, quantities, prices, trade dates, realized P&L, commissions per trade currency and account ids. **Send and remember** stores the consent in `globalState` under `ibkrHistory.chat.consent`. Reset it with **IBKR History: Reset Chat Data Consent**; the next send asks again.

The live option prices of §8.6 are public market data. The local trading CLI fetches them from yfinance, never from IBKR.

The Flex token is **never** part of the chat context. The context builder has no credential input at all, and a unit test asserts that a key never appears in the context. The `http` backend sends the API key only in the request header; the `lm` backend has no key to send.

### 8.4 Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `ibkrHistory.chat.backend` | `lm` | `lm` uses the VS Code Language Model API and the provider signed in to VS Code. `http` uses `{baseUrl}/chat/completions` with an API key |
| `ibkrHistory.chat.model` | `deepseek-v4-pro` | Preferred model id. In `lm` mode the list is dynamic and an unknown id falls back to a `family` match, then to the first model. In `http` mode the id is sent as is |
| `ibkrHistory.chat.baseUrl` | `https://opencode.ai/zen/go/v1` | `http` only. The request goes to `{baseUrl}/chat/completions` |
| `ibkrHistory.chat.temperature` | `0.3` | `http` only. Sampling temperature, 0 to 2 |
| `ibkrHistory.chat.maxTokens` | `2048` | `http` only. Maximum tokens in one answer |
| `ibkrHistory.chat.maxContextTrades` | `400` | Maximum trades embedded as CSV. The statistics, the monthly table and the symbol table always cover every row in range |
| `ibkrHistory.chat.maxHistoryMessages` | `20` | Maximum user and assistant messages kept. The oldest turns go first; the portfolio context is always sent |
| `ibkrHistory.chat.marketData` | `true` | Append the live option prices of the open option positions to the context. Turn it off to send the Flex dataset only |
| `ibkrHistory.chat.marketDataCommand` | `~/.local/share/opencode/trading-mcp-venv/bin/python -m trading_mcp.trading_cli` | Command template of the local trading CLI. The extension appends `fetch options <TICKER> --expiry <DATE>` and runs the parts without a shell. A leading `~/` expands to the home directory |

### 8.5 What the context contains

Every request sends the portfolio context. The `http` backend puts it in a `system` message. The `lm` backend puts the persona and the same context in the **first user message**, because `LanguageModelChatMessage` has no system role. The first message carries:

- the header: generation time, range and preset, account filter, accounts, base currency and its source, trade currencies, row accounting;
- a **currency map**, one line per block, naming the exact currency of every number. It is the first section after the header, because a currency mix is the most likely wrong answer;
- the **panel notices**, in the same words the portfolio panel shows: the trade-currency banner and the trade-currency-vs-base banner, including the FX effect amount. A statement the user reads in the panel is also a statement in the context;
- the full statistics block, tile by tile like the panel: realized P&L with the exact currency label (`includes the FX result` for the base view, `EXCLUDES the FX result` for a trade-currency view), P&L excluding FX, FX result, trades with realized P&L, gross profit and loss, profit factor, win rate, wins, losses and break-even, average win and loss, largest win and loss, max drawdown with its percentage, Sharpe-like ratio with its rule, trading days, best and worst symbol, average holding days, commissions per trade currency and the base estimate;
- a **chart series block**: the cumulative realized P&L curve ends and its peak, the deepest drawdown point with its date, and the fullest daily-P&L histogram bin. The panel draws the full series; the context states the facts an answer can quote;
- the monthly table and the per-symbol table over the full filtered set (top 20 by absolute P&L, plus the remaining symbols and their aggregate);
- a CSV block of the newest trades up to `ibkrHistory.chat.maxContextTrades`. The header is `date,time,symbol,side,qty,price,trade_ccy,realized_pnl_<currency>,pnl_source`, where `<currency>` is the display currency in lower case and the value is the same per-row figure the panel shows. An omitted-row count is stated exactly;
- when `ibkrHistory.chat.marketData` is on and the dataset has an open option position, a **live option data block**: the fetch time in UTC, the yfinance source, the spot price and the DTE per ticker, then one line per contract with the net quantity, the strike, the mark, the position value with the multiplier 100, the unrealized P&L, delta, theta and the implied volatility. A missing number is `n/a` and a failed chain is named with its reason;
- the FX block: total realized P&L in the base currency **including** the FX result, `Σ capitalGainsPnl` **excluding** it, `Σ fxPnl`, the identity between the three, and the exact rule `capitalGainsPnl / rate(tradeCcy → base, tradeDate)`. The block states that a base total and a trade-currency total are not one number in two units;
- every warning of the dataset;
- a currency note and a limitation note.

The context badge shows the current size: `Context: 412 trades · EUR base · generated 2026-11-14 23:20 · ~18k tokens`.

### 8.6 Live option data for the open option positions

Without market data the agent has the Flex dataset only: no live quote, no option chain and no Greeks. It has no news and no macro data either. The system prompt forbids inventing a price or a market event, and requires the model to say when the dataset cannot answer.

`ibkrHistory.chat.marketData` (default `true`) adds a **Live option data** block when the dataset has an open option position. The position comes from the trade rows: the symbol must parse as an OCC contract such as `LHX   261120C00320000`, and the signed quantities must not sum to zero. The block covers those positions only.

The extension reuses the local market-data CLI named by `ibkrHistory.chat.marketDataCommand`:

```
<python> -m trading_mcp.trading_cli fetch options <TICKER> --expiry <YYYY-MM-DD>
```

The CLI prints JSON on stdout and the prices come from yfinance. The extension runs one request per distinct `root|expiry` pair, at most six per question, in parallel and without a shell. A progress hint in the status bar keeps the view responsive, and the hint is cancellable: the send then continues without the block. A chain is cached for ten minutes, so a second question reuses the data.

The block states the fetch time in UTC, the source, the spot price and the DTE per ticker, then one line per contract with the net quantity, the strike, the mark (`(bid + ask) / 2`), the position value (`mark * 100 * net quantity`), the unrealized P&L (`position value - trade cash flow`), delta, theta and the implied volatility. Every missing number is `n/a`. A failed chain is named with the ticker and the reason, and the answer states the limitation. The Flex dataset stays authoritative for realized P&L.

The **Open in @trade** button, or the command **IBKR History: Analyze in @trade Agent**, writes the same context with the block to `<globalStorage>/handoff/portfolio-<UTC stamp>.md` and opens the chat with the `@trade` agent on that file. The query stays under 400 characters and names the absolute path.

### 8.7 Errors

`lm` backend:

| Condition | Message | Action |
| --- | --- | --- |
| No model in `vscode.lm.selectChatModels()` | No VS Code language model is available | Install and sign in to a provider, or switch `ibkrHistory.chat.backend` to `http` |
| `LanguageModelError.NoPermissions` | VS Code did not grant access to the language model | Allow the request, then press **Retry** |
| `LanguageModelError.Blocked` | The language model is blocked or the quota is exhausted | Check the subscription, then press **Retry** |
| `LanguageModelError.NotFound` | The selected language model is no longer available | Pick another model in the dropdown |

`http` backend:

| Status | Message | Action |
| --- | --- | --- |
| `401` | API key rejected | Run **IBKR History: Set Chat API Key** |
| `402` | Quota exhausted | Check your opencode-go plan |
| `429` | Rate limit reached | Wait a few seconds, then press **Retry** |
| `404` | Model name unknown | Pick another model in the dropdown |
| `5xx` | The chat service returned an error | Retry in a moment |

A failed answer shows the mapped message and a **Retry** button. **Stop** cancels the request and discards the partial answer. The output channel logs the backend, the model id and the row count; it never logs a key.

---

## 9. Development

```bash
npm run compile      # bundle dist/extension.cjs, media/webview.js and media/chat.js
npm run watch        # rebuild on change
npm run typecheck    # tsc --noEmit, strict
npm run lint         # eslint, flat config
npm run test         # node:test on TypeScript sources, no transpiler needed
npm run package      # minified production bundle
npm run verify       # typecheck + lint + test + compile
```

Tests use the built-in `node:test` runner and Node's native TypeScript type stripping. There is no test framework dependency, no ts-node and no transpiler step.

Type stripping without a flag needs Node 22.18 or newer (or 23.6 or newer). Verified on Node 26.13.1. VS Code runs the bundled `dist/extension.cjs`, so the extension itself works on the Node 20 built into VS Code 1.90.

### 9.1 Layout

```text
src/
  extension.ts              activation, command registration
  core/
    types.ts                Trade, DateRange, FormState
    dates.ts                presets, strict date parsing, range filtering
  flex/
    client.ts               SendRequest + GetStatement, backoff, deadline, redaction
    parser.ts               fast-xml-parser -> Trade[] (TradeConfirm + Trade rows), envelope and query-type detection
    errors.ts               documented error codes with actionable hints
  analytics/
    metrics.ts              curve, monthly, symbol, histogram, drawdown, stats
    dataset.ts              per-currency payload + warnings
  config/
    secrets.ts              SecretStorage wrapper
    validation.ts           form validation, shared rules
    settings.ts             non-secret configuration, read from VS Code
    settingsCore.ts         pure clamping and defaults, testable without vscode
  export/csv.ts             CSV writer
  chat/
    portfolioContext.ts     shared dataset store, publish/subscribe, no vscode
    context.ts              system-context builder (statistics, tables, CSV), no vscode
    lm.ts                   vscode.lm adapter helpers, pure and testable without vscode
    chatSettings.ts         chat settings resolution and defaults, no vscode
    client.ts               OpenAI-compatible SSE client, error mapping, no vscode
    credentials.ts          API key resolution order, no vscode
    markdown.ts             escaping-first markdown renderer, no vscode
    chatHtml.ts             CSP + nonce shell for the chat view
    chatViewProvider.ts     chat webview view, consent, streaming
    protocol.ts             chat host <-> webview types, backend, notice, http fallback model list
    webview/main.ts         chat UI, streaming append, markdown render
  panel/
    historyController.ts    shared state, fetch/export/clear flows, message handling
    historyPanel.ts         editor-tab surface (WebviewPanel)
    historyViewProvider.ts  Activity Bar surface (WebviewViewProvider)
    html.ts                 CSP + nonce HTML shell
    diagnostics.ts          redacted clipboard report, testable without vscode
    protocol.ts             host <-> webview message types
    webview/main.ts         UI and Chart.js rendering
    webview/pagination.ts   pure filter/sort/page helpers for the trades table, unit-tested without a DOM
test/                       node:test suites and XML fixtures
media/                      webview.css, webview.js (generated), chat.css, chat.js (generated), activitybar-icon.svg
dist/extension.cjs          generated CommonJS bundle
```

---

### 9.2 Why the bundle is `extension.cjs`, not `extension.js`

The package is declared `"type": "module"` so that the TypeScript sources and the tests run as real ES modules. Under that declaration a `.js` file is ESM, and the VS Code extension host `require()`s the entry point. A `.cjs` extension keeps the bundle CommonJS. esbuild emits it, and `package.json` declares `"main": "./dist/extension.cjs"`. The `vscode` module stays external in both cases.

### 9.3 Smoke test

`npm run smoke` loads the built bundle against a mocked `vscode` module. It checks nine registered commands, that the retry defaults reach the webview, that `registerWebviewViewProvider` is called for `ibkrHistory.panel` and `ibkrHistory.chat` with `retainContextWhenHidden`, the nonce-based CSP in the editor panel, the sidebar view and the chat view, that the chat dropdown is the dynamic `lm` list and the 15-model `http` fallback list, the absence of remote script URLs, and that neither the token nor the full Query ID ever reaches a webview or the output channel.

---

## 10. Troubleshooting

| Flex code | Message | Action |
| --- | --- | --- |
| `1011` | Service account is inactive | Enable Flex Web Service in Client Portal |
| `1012` | Token has expired | Generate a new token, paste it again |
| `1013` | IP restriction | Generate a token without IP restriction, or run from the allowed IP |
| `1014` | Query is invalid | Check the Query ID, or convert a legacy query to Activity Flex |
| `1015` | Token is invalid | Copy **Current Token** again. No spaces |
| `1017` | Reference code is invalid | Retry the fetch. Codes are single-use and short-lived |
| `1018` | Too many requests | Wait 60 seconds. Limit is 1 request/second, 10/minute |
| `1001` | Statement could not be generated | Transient. The extension retries SendRequest automatically. Raise `ibkrHistory.retry.maxSendAttempts` if it persists |
| `1019` | Statement generation in progress | Normal. The extension keeps polling |
| `1020` | Invalid request | Token or Query ID malformed. Query ID must be numeric |
| `1021` | Statement could not be retrieved | Retry. Shorten the query period if it repeats |
| `1006` | FIFO P/L data not ready | Retry on the next business day |

Other situations:

| Symptom | Cause and action |
| --- | --- |
| *"IBKR returned N trades covering X → Y, but none fall in the selected range"* | The saved query period is narrower than the selected range. Set the query to Year To Date |
| *"No trades match the account filter"* | The account ID is not in the report. Clear the filter |
| *"The Flex report is valid but contains no trade rows"* — **no rows parsed** | The report is valid but holds no `<TradeConfirm>` and no `<Trade>` rows. Either the query has no **Trades** / **Trade Confirmation** section, or its period excludes every trade. Add the section in Client Portal, set the period to Year To Date, then fetch again. **Copy diagnostics** shows the detected query type and `Rows parsed: 0` |
| `Last IBKR error code: none` after a network or empty-report failure | Expected. That failure carries no IBKR error code. Read the status, the poll count and the response snippet lines instead |
| `Polls: 0 of 120` with error code `1001` | Expected: no GetStatement poll ran. Read `SendRequest attempts`, `Last retry reason` and `Deadline remaining` in the same report |
| *"Statement still not ready after N polls"* | The attempt safety net ran out before the report was ready. Raise `ibkrHistory.retry.maxAttempts`, or raise `ibkrHistory.retry.deadlineMs` if the deadline is the cause. Click **Copy diagnostics** and check the last IBKR status: `1019` means the report is still generating |
| Timeout after 15 min | Raise `ibkrHistory.retry.deadlineMs`. Shorten the query period in Client Portal |
| *"the response is not XML"* | The Flex Query output format is CSV. Set it to XML in Client Portal |
| Charts are empty but statistics are not | Only trades with realized P&L enter the charts. Opening trades are excluded |
| *"Only the newest N trades appear"* in the trades table | The previous release capped the table at 50 rows. That cap is gone: the table lists every trade in range, with filtering and paging. If the caption says `Rows shown 5000 of N in range`, the payload hit the `maxTradeRows` safety ceiling of 5000. The charts, the statistics and the CSV export still use all N rows. Narrow the range or the account filter to reach older trades in the table |
| The trades table says `Rendering…` and stays there | A fetch or filter change restarted the incremental render. Wait for the current chunk loop to finish, or change the filter again. The panel is not frozen |
| Average holding period shows `n/a` | The report has no `openDate`/`openDateTime` field |
| `preceding an unexpected end of file` in logs | IBKR returned truncated XML. Retry. The panel does not crash |

---

## 11. Known limitations

1. Local range filtering only. See section 5.
2. Realized P&L only. No mark-to-market, no unrealized P&L, no cash or NAV curve.
3. The equity curve is cumulative realized P&L, not account equity.
4. No FX conversion for trade amounts. P&L is already base currency as IBKR reports it. The commission estimate uses report FX rates and is not exact.
5. Average holding period needs opening dates, which standard Trade Confirmation reports omit.
6. Sharpe-like ratio is P&L based. See section 7.2.
7. CSV export contains the filtered rows only. No summary block.
8. Verified on Linux with Node 26 and VS Code 1.90+ typings. macOS and Windows should work but are untested.
9. `<OpenPositions>` in Activity reports is ignored. Open positions, mark prices and unrealized P&L are a possible future addition. No UI reads them today, and no chart or statistic uses them.
10. The trades table payload is capped at `maxTradeRows` (5000) to protect the webview message channel. The cap is announced, never silent, and never applies to the charts, the statistics or the CSV export.
11. The Trade Chat has no live market data: no quote, no option chain, no Greeks, no news. It answers from the Flex dataset only.
12. The chat context embeds at most `ibkrHistory.chat.maxContextTrades` rows (400). The statistics, the monthly table and the symbol table always cover every row in range, and the omitted count is stated in the context.
13. The conversation lives in the extension host, not on disk. Closing the window clears it.

---

## License

MIT.
