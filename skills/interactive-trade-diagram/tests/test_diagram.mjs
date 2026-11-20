// Tests of the trade-diagram engine: golden values from tests/reference.py and negative cases.
// Run: node skills/interactive-trade-diagram/tests/test_diagram.mjs   (exit code 1 on any failure)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runDiagram, replaceConfig, invariantIssues } from "../scripts/check_diagram.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const tpl = fs.readFileSync(path.join(here, "..", "assets", "template.html"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(here, "fixtures", "golden_cases.json"), "utf8"));

let failures = 0;
let checks = 0;
const fail = (msg) => { failures++; console.log("  FAIL " + msg); };
const ok = (cond, msg) => { checks++; if (!cond) fail(msg); };
const moneyTol = (v) => 0.01 + 1e-7 * Math.abs(v);
function near(name, a, b, tol) {
  checks++;
  if (b === null || b === undefined) { if (a !== null && a !== undefined) fail(name + ": motore " + a + ", riferimento null"); return; }
  if (!(typeof a === "number" && Math.abs(a - b) <= tol)) fail(name + ": motore " + a + " ≠ riferimento " + b + " (tolleranza " + tol + ")");
}
function nearList(name, a, b, relTol) {
  checks++;
  if (!Array.isArray(a) || a.length !== b.length) { fail(name + ": motore " + JSON.stringify(a) + " ≠ riferimento " + JSON.stringify(b)); return; }
  b.forEach((v, i) => near(name + "[" + i + "]", a[i], v, relTol * Math.max(1, Math.abs(v))));
}
const cfgOf = (name) => JSON.parse(JSON.stringify(data.cases.find((c) => c.name === name).config));
const run = (cfg, opts) => runDiagram(replaceConfig(tpl, cfg), Object.assign({ filename: "case.html" }, opts || {}));

function textOf(node) {
  if (!node) return "";
  if (node.nodeType === 3) return node.textContent;
  return (node.ownText || "") + (node.html || "") + node.children.map(textOf).join(" ");
}
function fire(doc, id, type, extra) {
  const el = doc.getElementById(id);
  (el.listeners.get(type) || []).forEach((fn) => fn.call(el, Object.assign({ target: el, preventDefault() {} }, extra || {})));
}
function allHtml(doc) { return doc.all.map((e) => e.html || "").join("\n"); }

/* ---------- 1. golden cases vs the Python reference ---------- */
for (const c of data.cases) {
  console.log("golden: " + c.name);
  const res = run(c.config, { filename: c.name + ".html" });
  res.errors.forEach((e) => fail("errore del motore: " + e));
  const s = res.summary, e = c.expected;
  if (!s || !s.ok) { fail("riepilogo mancante"); continue; }
  near("T0front", s.T0front, e.T0front, 1e-12);
  nearList("bes", s.bes, e.bes, 1e-6);
  nearList("besToday", s.besToday, e.besToday, 1e-5);
  ok(s.maxProfitUnbounded === e.maxProfitUnbounded, "maxProfitUnbounded " + s.maxProfitUnbounded + " ≠ " + e.maxProfitUnbounded);
  ok(s.maxLossUnbounded === e.maxLossUnbounded, "maxLossUnbounded " + s.maxLossUnbounded + " ≠ " + e.maxLossUnbounded);
  if (!e.maxProfitUnbounded) near("maxProfit", s.maxProfit, e.maxProfit, moneyTol(e.maxProfit));
  if (!e.maxLossUnbounded) near("maxLoss", s.maxLoss, e.maxLoss, moneyTol(e.maxLoss));
  ok(s.zones.length === e.zones.length, "numero di zone " + s.zones.length + " ≠ " + e.zones.length);
  e.zones.forEach((z, i) => {
    const m = s.zones[i];
    if (!m) return;
    ok(m.sign === z.sign, "zona " + i + ": segno " + m.sign + " ≠ " + z.sign);
    near("zona " + i + " from", m.from, z.from, 1e-6 * Math.max(1, z.from));
    if (z.to === null) ok(m.to === null, "zona " + i + ": to deve essere ∞");
    else near("zona " + i + " to", m.to, z.to, 1e-6 * Math.max(1, z.to));
    ok(m.unbounded === z.unbounded, "zona " + i + ": unbounded " + m.unbounded + " ≠ " + z.unbounded);
    if (z.best !== null) near("zona " + i + " best", m.best, z.best, moneyTol(z.best));
    if (z.prob !== null) near("zona " + i + " prob", m.prob, z.prob, 1e-7);
  });
  for (const k of ["pnlExpSpot", "pnlNowSpot", "thetaDay", "vegaPt", "pnlMark", "pnlClose"]) near(k, s[k], e[k], moneyTol(e[k]));
  near("deltaNow", s.deltaNow, e.deltaNow, 1e-6);
  ok(s.closeBasis === e.closeBasis, "closeBasis " + s.closeBasis + " ≠ " + e.closeBasis);
  if (e.sigmaAtm !== null) near("sigmaAtm", s.sigmaAtm, e.sigmaAtm, 1e-12);
  e.legs.forEach((l, i) => {
    near("gamba " + i + " T0", s.legs[i].T0, l.T0, 1e-12);
    near("gamba " + i + " model0", s.legs[i].model0, l.model0, 1e-8 + 1e-9 * Math.abs(l.model0));
    if (l.pItm !== null) near("gamba " + i + " P(ITM)", s.legs[i].pItm, l.pItm, 1e-9);
  });
  ok(s.scenarios.length === e.scenarios.length, "numero di scenari");
  e.scenarios.forEach((r) => {
    const m = s.scenarios.find((x) => Math.abs(x.price - r.price) < 1e-9);
    ok(Boolean(m), "scenario " + r.price + " mancante nel motore");
    if (!m) return;
    for (const k of ["exp", "now", "ivDn", "ivUp"]) near("scenario " + r.price + " " + k, m[k], r[k], moneyTol(r[k]));
  });
}

/* ---------- 2. behaviour checks ---------- */
console.log("comportamento");
{
  const res = run(cfgOf("long_call"), { events: false });
  const first = res.document.getElementById("dayRows").children[0];
  ok(res.summary.thetaDay < 0, "long call: theta deve essere negativa");
  ok(/−\$[0-9.]+<\/td>$/.test(first.html || ""), "long call: la colonna theta del giorno 0 deve essere negativa: " + (first.html || "").slice(-60));
}
{
  const res = run(cfgOf("r_zero_bull_put"), { events: false });
  const zones = textOf(res.document.getElementById("zoneCards"));
  ok(zones.includes("K $95.00 (−5.0%)"), "bull put: distanza dallo strike short 95 = −5.0%: " + zones);
  ok(zones.includes("Zona di perdita") && zones.includes("sotto $92.70") && zones.includes("sopra $92.70"), "bull put: zone sotto e sopra il BE");
}
{
  const res = run(cfgOf("call_calendar"), { events: false });
  const labels = textOf(res.document.getElementById("chart"));
  ok(labels.includes("BE $94.27") && labels.includes("BE $107.26"), "calendar: una linea per ogni break-even");
}
{
  const res = run(cfgOf("put_diagonal_eur"), { events: false });
  ok(!/\$/.test(textOf(res.document.getElementById("econCard")) + textOf(res.document.getElementById("legsCard"))), "EUR: nessun simbolo $ nelle card");
  ok(textOf(res.document.getElementById("econCard")).includes("€"), "EUR: simbolo € nelle card");
}
{
  const res = run(cfgOf("low_price_covered_call"), { events: false });
  ok(res.summary.grid.sliderStep <= 0.01 * 3.2, "titolo da $3.20: passo dello slider " + res.summary.grid.sliderStep);
  ok(res.summary.daily.heatRows >= 20, "titolo da $3.20: righe della mappa " + res.summary.daily.heatRows);
  ok(res.summary.scenarios.length >= 4, "titolo da $3.20: scenari");
}
{
  const res = run(cfgOf("short_put"), { events: false });
  const doc = res.document;
  const cell0 = () => doc.getElementById("heat").children[0].children[0].getAttribute("fill");
  const row0 = () => doc.getElementById("dayRows").children[0].html;
  const base = [cell0(), row0()];
  fire(doc, "ivUp", "click");
  ok(cell0() !== base[0], "IV +10: la mappa di calore deve cambiare");
  ok(row0() !== base[1], "IV +10: la tabella deve cambiare");
  ok(doc.getElementById("tblTitle").textContent.includes("IV +10"), "IV +10: titolo della tabella");
  fire(doc, "ivBase", "click");
  ok(cell0() === base[0] && row0() === base[1], "IV invariata: la mappa e la tabella tornano al valore base");
  fire(doc, "heat", "focus");
  ok(doc.getElementById("heatTip").classList.contains("show") && doc.getElementById("heatLive").textContent.includes("P&L"),
    "mappa: il tooltip appare anche con il focus della tastiera");
  fire(doc, "heat", "keydown", { key: "ArrowRight" });
  ok(doc.getElementById("heatLive").textContent.includes("2026-11-21"), "mappa: la freccia destra passa al giorno dopo");
}
{
  const cfg = cfgOf("short_put");
  cfg.legs[0].opened = "2026-11-10";
  cfg.daily = { hist: [
    { date: "2026-11-12", close: 51.2 },
    { date: "2026-11-05", close: 49.0 },
    { date: "2026-11-01", close: 48.0, legs: [{ kind: "put", side: "short", strike: 47, qty: 3, entry: 1.9, iv: 0.5 }], realized: 0 }
  ] };
  const res = run(cfg, { events: false });
  ok(!res.errors.length, "storia valida: nessun errore: " + res.errors.join(" | "));
  const hist = res.document.getElementById("histWrap").html || "";
  ok(/rifiutata/.test(hist) && (hist.match(/rifiutata/g) || []).length === 1, "storia: una riga rifiutata (gambe non ancora aperte)");
  ok(/della riga/.test(hist), "storia: la riga con legs usa le sue gambe");
  ok(res.warnings.some((w) => w.includes("righe rifiutate")), "storia: avviso per le righe rifiutate");
}
{
  const cfg = cfgOf("zero_dte_short_call");
  delete cfg.asOfTime;
  const res = run(cfg, { events: false });
  ok(!res.errors.length && res.warnings.some((w) => w.includes("0DTE")), "0DTE senza asOfTime: avviso, non errore");
  ok(res.summary.T0front === 0, "0DTE senza asOfTime: tempo residuo zero");
}
{
  const res = runDiagram(tpl, { filename: "template.html" });
  ok(!res.errors.length, "esempio del template senza errori: " + res.errors.join(" | "));
  ok(res.events > 20, "esempio del template: eventi simulati " + res.events);
}

/* ---------- 3. the self-test must catch these errors ---------- */
console.log("casi negativi");
const mustFail = (label, html, pattern, pageLevel = true) => {
  const res = runDiagram(html, { filename: label + ".html" });
  ok(res.errors.length > 0, label + ": il self-test non trova l'errore");
  if (pattern) ok(res.errors.some((e) => pattern.test(e)), label + ": messaggio atteso " + pattern + ", trovato: " + res.errors.join(" | "));
  if (pageLevel) ok(res.title.startsWith("ERR:"), label + ": il titolo deve iniziare con ERR: (" + res.title + ")");
};
{
  const c = cfgOf("short_put"); c.dte = 31;
  mustFail("dte diverso", replaceConfig(tpl, c), /dte \(31\) non coincide/);
}
{
  const c = cfgOf("short_put"); delete c.expiryISO;
  mustFail("expiryISO mancante", replaceConfig(tpl, c), /expiryISO mancante/);
}
{
  const c = cfgOf("call_calendar"); c.expiryISO = "2027-01-19"; c.dte = 60;
  mustFail("expiryISO non front", replaceConfig(tpl, c), /scadenza più vicina/);
}
{
  const c = cfgOf("short_put"); delete c.r;
  mustFail("r mancante", replaceConfig(tpl, c), /r mancante/);
}
{
  const c = cfgOf("short_put"); c.legs[0].iv = 45;
  mustFail("iv in percento", replaceConfig(tpl, c), /iv fuori scala/);
}
{
  const c = cfgOf("iron_condor"); c.legs[0].currency = "EUR";
  mustFail("valute miste", replaceConfig(tpl, c), /valuta EUR diversa/);
}
{
  const c = cfgOf("short_put"); c.daily = { hist: [{ date: "10.11.2026", close: 50 }] };
  mustFail("data storica non ISO", replaceConfig(tpl, c), /daily\.hist\[0\]: date non valida/);
}
mustFail("CONFIG con errore di sintassi", replaceConfig(tpl, "const CONFIG = { ticker: 'X', ;"), /JavaScript/);
mustFail("script remoto", tpl.replace("</body>", '<script src="https://cdn.example.com/x.js"></script></body>'), /Offline: script esterno/, false);
mustFail("senza onerror", tpl.replace(/<script>\n\/\* Gestione errori[\s\S]*?<\/script>/, ""), /Manca window\.onerror/, false);
{
  const c = cfgOf("short_put");
  const evil = '<img src=x onerror="alert(1)">';
  c.legsNote = evil; c.chips = [{ label: evil, value: evil }]; c.timeline = [{ date: evil, title: evil, detail: evil }];
  c.alerts = [{ level: evil, meaning: evil, action: evil }]; c.greeks = [{ name: evil, value: evil, note: evil }];
  c.bridge = [{ label: evil, value: 1, kind: "flow" }, { label: evil, kind: "total" }];
  c.timelineSide = { title: evil, rows: [[evil, evil, "pos"]], note: evil };
  const res = run(c, { events: false });
  ok(!/<img/i.test(allHtml(res.document)), "XSS: una stringa del CONFIG è entrata come HTML");
  ok(/&lt;img/.test(allHtml(res.document)), "XSS: la stringa deve apparire come testo");
}

{
  const res = run(cfgOf("iron_condor"), { events: false });
  const copy = () => JSON.parse(JSON.stringify(res.summary));
  const s1 = copy(); s1.bes = [s1.bes[0]];
  ok(invariantIssues(s1, res.api).some((m) => m.includes("break-even")), "invariante: un break-even mancante non è trovato");
  const s2 = copy(); s2.zones[1].sign = -1;
  ok(invariantIssues(s2, res.api).some((m) => m.includes("segno sbagliato")), "invariante: un segno di zona sbagliato non è trovato");
  const s3 = copy(); s3.maxProfit = 100;
  ok(invariantIssues(s3, res.api).some((m) => m.includes("max profit")), "invariante: un max profit sbagliato non è trovato");
  ok(invariantIssues(res.summary, res.api).length === 0, "invariante: il riepilogo corretto non deve dare errori");
}

console.log(failures ? "FALLITO: " + failures + " errori su " + checks + " controlli" : "OK: " + checks + " controlli");
process.exitCode = failures ? 1 : 0;
