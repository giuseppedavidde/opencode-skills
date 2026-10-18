# Piano di progettazione — DataProvider pluggable per i dati opzioni (GEX & analisi)

> Documento di progettazione. **Nessun codice implementato** in questo passaggio.
> Obiettivo: rendere pluggable il `DataProvider` del trading MCP per migliorare la
> qualità dei dati opzioni usati dal computo GEX e dall'analisi in generale, con
> provenienza dati esplicita (`data_source`) e degradazione controllata senza chiave.

---

## 0) Stato attuale (fondamenta su cui costruire)

- **Singleton provider**: `DataProvider` (`mcp/src/trading_mcp/data/provider.py:304`),
  istanza unica `data_provider = DataProvider()` (`provider.py:739`), esportata da
  `data/__init__.py`.
- **Cache TTL**: `CacheEntry` (`provider.py:217`), `TickerCache` (`provider.py:245`),
  `DEFAULT_TTL` (`provider.py:319-324`: `options=3600`, `options_chain=60`).
- **Metodi opzioni**: `get_options_expirations` (`provider.py:456`) →
  `_fetch_options_expirations` (`provider.py:724`, `yf.Ticker(symbol).options`);
  `get_options_chain` (`provider.py:486`) → **hard-coded yfinance**
  `yf.Ticker(symbol).option_chain(expiry)` (`provider.py:504-506`).
- **Orchestratore opzioni**: `fetch_options_chain(ticker, expiry, use_cache,
  strike_window, full_chain)` (`options_chain.py:107`) → dict normalizzato con
  `calls`/`puts` (leg dict con `strike`, `gamma`, `openInterest`, `iv_used`,
  `iv_source`), greeks BS calcolati (`options_chain.py:657`, gamma arrotondata `:729`),
  e **provenienza già presente**: `_source` = `"live"` (`:212`), `"cache"`
  (`:157/164/174`), `"fallback"` (`:250`).
- **GEX già consuma la provenienza**: `GexResult.source` (`gex.py:56-83`) popolato con
  `first.get("_source")` (`gex.py:564`); tool `gex_analysis`
  (`tools/_analysis_tools.py:353`) con cache result-level
  (`result_cache.get("gex_analysis", …)`, `:384`) e TTL 5min (`result_cache.py:80`).
- **Pattern esistenti di fetcher opzionali**: `fmp_fetcher.py` (`_load_api_key` legge
  env `TRADING_FMP_API_KEY`/`FMP_API_KEY` **e** `~/.config/opencode/fmp_api_key.txt`),
  `alpha_vantage_fetcher.py`; chiavi in `config.py:63-71`.
- **Overlay GEX**: `GexOverlay` (`breakout_context.py:112-121`) **senza** campo
  provenienza; `build_gex_overlay` (`:487`).
- **Dipendenze**: `pyproject.toml:12-21` — `requests` **non è dichiarato** (oggi arriva
  transitivamente via yfinance); `pytest`/`pylint` in `dev` (`:24-27`), marker `network`
  (`:36-39`), **nessun `conftest.py`**.

---

## 1) Interfaccia astratta e modelli normalizzati

Nuovo package: `src/trading_mcp/data/backends/` con `base.py` (Protocol + modelli),
`registry.py`, e un file per adattatore.

### 1.1 Protocol (typing strutturale, non ABC — coerente con lo stile attuale)

```python
class OptionsBackend(Protocol):
    name: str                                   # "yfinance" | "thetadata" | "polygon" | ...
    capabilities: BackendCapabilities

    def is_available(self) -> bool: ...          # feature/key/daemon detection
    def get_expirations(self, ticker: str) -> list[str]: ...
    def get_chain(self, ticker: str, expiry: str) -> OptionsChain | None: ...
```

### 1.2 Modelli Pydantic (`base.py`, pydantic v2 con type hints)

- `BackendCapabilities(BaseModel)`: `provides_greeks: bool`, `provides_iv: bool`,
  `provides_open_interest: bool`, `historical: bool`, `eod_only: bool`, `us_only: bool`,
  `max_requests_per_minute: int`, `requires_local_daemon: bool`.
- `OptionRight(StrEnum)`: `CALL`, `PUT` (evita la stringa magica `"calls"/"puts"`).
- `OptionQuote(BaseModel)` — **leg normalizzato**:
  - `strike: float`, `right: OptionRight`, `expiry: date`
  - `bid: float | None`, `ask: float | None`, `last: float | None`
  - `volume: int = 0`, `open_interest: int = 0`
  - `implied_volatility: float | None` (decimale annualizzato, es. 0.20)
  - `delta: float | None`, `gamma: float | None`, `theta: float | None`, `vega: float | None`
  - `contract_multiplier: int = 100`, `currency: str = "USD"`
- `OptionsChain(BaseModel)`: `ticker: str`, `spot: float`, `expiry: date`,
  `quotes: list[OptionQuote]`, `as_of: datetime`, `source: str` (id backend),
  `greeks_are_native: bool`, `iv_is_native: bool`.

### 1.3 Convenzioni/unità (documentate nel docstring del modulo — critiche)

- `gamma` = **per-share** (1/unità di sottostante), stessa convenzione della formula
  GEX `±gamma·OI·100·S²·0.01` e di `options_chain.py:657`. **Gli adattatori devono
  normalizzare** i vendor che forniscono gamma "per contratto" (×100) o dollar-gamma
  (rischio già emerso in E1/E6).
- `implied_volatility` = decimale annualizzato; `open_interest` = n. contratti;
  `contract_multiplier = 100`.
- Il **bridge** `OptionsChain → leg-dict di options_chain.py` (`strike`, `gamma`,
  `openInterest`, `iv_used`, `iv_source`) mantiene la backward compatibility con
  `aggregate_strikes`/`_chain_to_list`.

---

## 2) Adattatori concreti

| Backend | Auth / dipendenze | Dati | Limiti free | Note |
|---|---|---|---|---|
| **YFinanceBackend** (default) | nessuna; `yfinance` già in deps | IV (affidabilità media), OI (EOD), **no greeks nativi** | rate-limit non ufficiale | Wrap del codice attuale (`provider.py:504-506`); `greeks_are_native=False` → greeks BS calcolati downstream |
| **ThetaDataBackend** | `thetadata` Python + **Java Theta Terminal daemon** su `127.0.0.1:25510`; env `THETADATA_API_KEY` (per storico) | IV/greeks/OI **reali**, anche storici | free tier limitato, **US-only** | `is_available()` = ping HTTP a localhost + import; `requires_local_daemon=True` |
| **PolygonBackend** | REST `api.polygon.io`, Bearer `POLYGON_API_KEY` | snapshot/aggregates opzioni; greeks nativi solo su piani superiori | **5 req/min**, EOD/delayed | **richiede rate-limiter + batching** per il GEX multi-expiry |
| **MarketDataBackend** | REST `api.marketdata.app`, token `MARKETDATA_API_KEY` | opzioni con greeks/IV | free ~100 req/giorno | Adattatore sottile su base REST comune |
| **TradierBackend** | REST sandbox, `TRADIER_TOKEN` | greeks/IV | sandbox ~120 req/min | alternativa |
| **AlpacaBackend** | `ALPACA_API_KEY/SECRET` | options data (Alpaca Data API) | tier free | opzionale |

- **Base REST condivisa**: `RestOptionsBackend` con `_http_get(path, params, headers)`
  iniettabile (per test offline), gestione `429`/`Retry-After`, token-bucket per
  `max_requests_per_minute`.
- **Feature detection**: `is_available()` verifica (a) key/env presente, (b) dipendenza
  importabile, (c) per ThetaData ping del daemon; se una fallisce il backend è **escluso**
  dal registry senza errori.
- **Fallback a catena** dentro il registry/provider (vedi §3).

---

## 3) Selezione backend, priorità, fallback, rate limiting

- **`config.py`** (accanto a `FMP_API_KEY` `:64`): nuove costanti
  - `OPTIONS_BACKENDS: list[str]` da env `TRADING_OPTIONS_BACKENDS` (csv),
    **default `["yfinance"]`** → zero-config invariato;
  - `POLYGON_API_KEY`, `MARKETDATA_API_KEY`, `TRADIER_TOKEN`, `ALPACA_KEY/SECRET`,
    `THETADATA_URL` (default `http://127.0.0.1:25510`).
- **`backends/registry.py`**: `build_backends(priority: list[str]) -> list[OptionsBackend]`
  → istanzia, filtra con `is_available()`, e **garantisce yfinance come ultimo** elemento
  (rete di sicurezza).
- **`DataProvider`** (`provider.py:304`): nuovo param `backend_priority` in `__init__`
  (`:326`); `get_options_expirations` (`:456`) e `get_options_chain` (`:486`) iterano i
  backend in priorità: primo che risponde vince; su `None`/eccezione → next. Il **valore
  di cache diventa `(data, backend_name)`** per preservare la provenienza (oggi
  `TickerCache.options_chains` è `CacheEntry.data`).
- **Rate limiting**: `TokenBucket(max_per_minute)` per backend; per Polygon (5/min) i fetch
  multi-expiry vengono **spazzati con attesa**; mitigato dal caching TTL
  (`options_chain=60s`, `options=3600s`) e dal result-cache GEX (5 min).
- **Cache**: riuso di `CacheEntry`/`TickerCache` + disk cache esistente di
  `options_chain.py` (`_load_cached_chain`/`_save_cached_chain`); la chiave deve includere
  il backend per non mischiare provenienze.

---

## 4) Propagazione di `data_source`

1. `OptionsChain.source` (nuovo) → bridge → `options_chain.fetch_options_chain` imposta
   `_source` = **id backend** (`"yfinance"`, `"thetadata"`, `"polygon"`, …) quando fresco;
   `"cache"` da disk-cache; `"fallback"` quando sintetico (`options_chain.py:212/250`).
   Back-compat: i valori `"live"/"cache"/"fallback"` restano accettati, si aggiunge l'id
   backend.
2. **`GexResult`** (`gex.py:56-83`): aggiungere `data_source: str` (id backend) e
   `data_quality: str` (es. `"quote+computed-greeks"`, `"native-greeks"`, `"eod"`,
   `"delayed"`), mantenendo `source` (`gex.py:564`) per compatibilità.
3. **`GexOverlay`** (`breakout_context.py:112-121`): aggiungere `data_source: str | None = None`
   e propagarlo in `build_gex_overlay` (`:487`).
4. **Tool** (`tools/_analysis_tools.py`): `gex_analysis` (`:353`) restituisce già il payload
   → nessuna firma nuova, ma il campo arriva; `breakout_context` (`:395`) espone l'overlay
   col campo. `options_context` (`:263`) mantiene `_source`.
5. **schemas.py:284 `GexResult`** (modello legacy duplicato): allineare aggiungendo
   `data_source` — o **deprecare** in favore di quello in `gex.py` (vedi rischi).

---

## 5) Strategia di test e criteri di accettazione

Test (nuovi file `tests/test_options_backends.py`, `tests/test_backend_fallback.py`;
fixture in `tests/fixtures/`):

- **Unit adattatori**: parsing di JSON registrati (ThetaData/Polygon/MarketData) →
  `OptionsChain` normalizzato, con assert su unità (gamma per-share, IV decimale, OI
  contratti).
- **Unit registry/priorità**: ordine, esclusione di backend non disponibili, yfinance
  sempre ultimo.
- **Fallback**: backend primario che solleva/ritorna `None` → cade su yfinance →
  `data_source == "yfinance"`; nessuna eccezione propagata.
- **Zero-config (regressione)**: senza env → solo yfinance → output e `_source` invariati.
- **Propagazione `data_source`**: `analyze_gex` ritorna `data_source`/`data_quality`;
  cache result-level preserva il campo.
- **Rate-limit**: `TokenBucket` rispetta `max_requests_per_minute` (test deterministico con
  clock iniettato).
- **Testabilità offline**: `RestOptionsBackend._http_get` iniettabile via dependency
  injection → nessuna dipendenza da rete; **evitare** di aggiungere `respx` se non
  necessario.
- Marker `@pytest.mark.network` per i test che toccano i vendor reali (come `test_gex.py`).

**Criteri di accettazione**:

1. Default invariato: `pip install` senza env → comportamento e `data_source` attuali.
2. Nessuna regressione: `pytest tests/ -q -m "not network"` verde; `pylint` ≥ baseline.
3. Con `TRADING_OPTIONS_BACKENDS=polygon,yfinance` e key valida → `data_source="polygon"`;
   senza key → degrade a `yfinance` senza crash.
4. GEX = formula corretta invariata (`±gamma·OI·100·S²·0.01`) e flip repricizzato (E1)
   intatti; la provenienza è esplicita e coerente.
5. Rate-limit e caching rispettati (nessun `429` non gestito).

---

## 6) Rischi / trade-off e fuori scope

**Rischi**

- **Semantica gamma per vendor** (per-share vs per-contratto vs dollar-gamma): se non
  normalizzata, reintroduce un errore classe-E1 → è il punto più delicato; richiede test
  dedicati per ogni adattatore.
- **Limiti free tier**: Polygon 5 req/min rende il GEX multi-expiry lento (12 expiry ≈ 2.4
  min) → mitigare con batching/caching; MarketData ~100 req/day.
- **Copertura US-only** (ThetaData) e **OI aggiornato EOD** (molti vendor) → qualità/timing
  diversi da yfinance intraday; `data_quality` deve renderlo esplicito.
- **ThetaData daemon Java** locale: fragilità operativa (avvio/porta), non testabile in CI →
  `is_available()` deve degredare silenziosamente.
- **Licenze** free tier / ridistribuzione dati: valutare ToS per l'uso del tool.
- **Dipendenze**: `requests` va **dichiarato** in `pyproject.toml`; eventuali SDK
  (`thetadata`, `alpaca-py`) come **optional-dependencies**
  `[project.optional-dependencies].options`.
- **Duplicazione `GexResult`** (`gex.py` vs `schemas.py:284`): rischio di divergenza dei
  campi provenienza.
- **Ambiguità terminologica** `_source` (oggi `"live"`) vs `data_source` (backend id):
  definire una volta e documentare.

**Fuori scope (esplicito)**: dati non-opzioni (equity/OHLCV) restano su yfinance; nessun
paging intraday tick-level; nessun calcolo di max-pain/IV-rank nuovo; nessuna
ridistribuzione dei dati; nessun refactor di E3/E4 (round gamma 4dp, dividend yield) —
restano aperti dal task precedente.

---

## 7) Decomposizione atomica (ordine di esecuzione, file, stima)

| # | Azione | File | Stima |
|---|---|---|---|
| 1 | Modelli normalizzati + `OptionsBackend` Protocol + `BackendCapabilities` | `data/backends/base.py` (nuovo) | S |
| 2 | `RestOptionsBackend` base con `_http_get` iniettabile + `TokenBucket` | `data/backends/rest.py` (nuovo) | M |
| 3 | `YFinanceBackend` che wrappa `provider.py:504-506`/`:724` | `data/backends/yfinance_backend.py` (nuovo) | S |
| 4 | `registry.build_backends()` (filtra con `is_available`, yfinance ultimo) | `data/backends/registry.py` (nuovo) | S |
| 5 | Config: `OPTIONS_BACKENDS` + chiavi backend | `config.py` | S |
| 6 | `DataProvider`: param `backend_priority`, iterazione backend+cache con provenienza (`:326/:456/:486`) | `provider.py` | M |
| 7 | Bridge `OptionsChain → leg-dict`, `_source`=id backend | `data/options_chain.py` | M |
| 8 | `data_source`/`data_quality` su `GexResult` (`:56-83`) e `GexOverlay` (`:112-121`) + propagazione tool (`_analysis_tools.py:353/:395`) | `gex.py`, `breakout_context.py`, `tools/_analysis_tools.py` (opz.) | S-M |
| 9 | Adattatore `PolygonBackend` (rate-limit 5/min, greeks opzionali) | `data/backends/polygon_backend.py` (nuovo) | M |
| 10 | Adattatore `MarketDataBackend` | `data/backends/marketdata_backend.py` (nuovo) | S |
| 11 | Adattatore `ThetaDataBackend` (daemon + feature-detect US-only) | `data/backends/thetadata_backend.py` (nuovo) | M-L |
| 12 | Test: adapter/registry/fallback/propagazione/rate-limit + fixture | `tests/test_options_backends.py`, `tests/test_backend_fallback.py`, `tests/fixtures/*` | M |
| 13 | `pyproject.toml`: `requests` in deps, SDK opzionali in `optional-dependencies` | `pyproject.toml` | S |
| 14 | Doc: convenzioni unità + matrice backend/limiti/quality | `docs/` o docstring modulo | S |

Dipendenza consigliata: **1→2→3→4→5→6→7→12** è il percorso minimo "pluggable con solo
yfinance" (accettazione 1-2); poi 8 (provenienza), poi 9/10/11 in ordine di semplicità
(MarketData → Polygon → ThetaData), chiudendo con 13/14. Non escogitare tutti i backend in
un unico step: ogni adattatore = PR/step atomico con i propri test + fixture.

> Nota: in fase di implementazione conviene delegare la decomposizione fine a
> `@coder_planner` (l'ha già fatto per il fix E1/E2) partendo da questa tabella, passando
> come file target solo 2-3 file per step.
