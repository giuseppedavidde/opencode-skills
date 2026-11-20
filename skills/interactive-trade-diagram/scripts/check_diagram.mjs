#!/usr/bin/env node
// Self-test of an interactive trade diagram (HTML). No browser, no npm package.
// Usage: node check_diagram.mjs <file.html> [--json] [--quiet] [--no-events]
// Exit code: 0 = no error, 1 = error or failed invariant, 2 = usage or read error.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

const SVG_NS = "http://www.w3.org/2000/svg";
const BAD_TEXT = [/\bNaN\b/, /\bundefined\b/, /\bInfinity\b/, /\[object Object\]/];

class ClassList {
  constructor() { this.set = new Set(); }
  add(...c) { c.forEach((x) => this.set.add(String(x))); }
  remove(...c) { c.forEach((x) => this.set.delete(String(x))); }
  toggle(c, force) {
    const on = force === undefined ? !this.set.has(c) : Boolean(force);
    if (on) this.set.add(c); else this.set.delete(c);
    return on;
  }
  contains(c) { return this.set.has(c); }
  toString() { return [...this.set].join(" "); }
}

class TextNode {
  constructor(text) { this.textContent = String(text); this.parentNode = null; this.nodeType = 3; }
}

class Element {
  constructor(doc, tag, ns) {
    this.ownerDocument = doc;
    this.tagName = String(tag).toUpperCase();
    this.namespaceURI = ns || "http://www.w3.org/1999/xhtml";
    this.nodeType = 1;
    this.attrs = new Map();
    this.children = [];
    this.parentNode = null;
    this.style = { setProperty(k, v) { this[k] = v; }, getPropertyValue(k) { return this[k] ?? ""; } };
    this.classList = new ClassList();
    this.listeners = new Map();
    this.dataset = {};
    this.ownText = "";
    this.html = null;
    this.value = "";
    this.min = "";
    this.max = "";
    this.step = "";
    doc.all.push(this);
  }
  get id() { return this.attrs.get("id") || ""; }
  set id(v) { this.setAttribute("id", v); }
  get className() { return this.classList.toString(); }
  set className(v) { this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean)); }
  set tabIndex(v) { this.attrs.set("tabindex", String(v)); }
  get tabIndex() { return Number(this.attrs.get("tabindex") ?? -1); }
  setAttribute(k, v) {
    const s = String(v);
    if (k === "class") { this.className = s; return; }
    this.attrs.set(k, s);
    if (k === "id") this.ownerDocument.ids.set(s, this);
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase())] = s;
    if (["value", "min", "max", "step"].includes(k)) this[k] = s;
  }
  getAttribute(k) {
    if (k === "class") return this.className;
    return this.attrs.has(k) ? this.attrs.get(k) : null;
  }
  hasAttribute(k) { return k === "class" ? this.classList.set.size > 0 : this.attrs.has(k); }
  removeAttribute(k) { this.attrs.delete(k); }
  appendChild(c) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    this.children.push(c);
    return c;
  }
  insertBefore(c, ref) {
    if (ref == null) return this.appendChild(c);
    if (c.parentNode) c.parentNode.removeChild(c);
    const i = this.children.indexOf(ref);
    if (i < 0) throw new Error("insertBefore: il riferimento non è un figlio");
    c.parentNode = this;
    this.children.splice(i, 0, c);
    return c;
  }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i < 0) throw new Error("removeChild: il nodo non è un figlio");
    this.children.splice(i, 1);
    c.parentNode = null;
    return c;
  }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get childNodes() { return this.children; }
  get parentElement() { return this.parentNode instanceof Element ? this.parentNode : null; }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) {
    this.children.forEach((c) => { c.parentNode = null; });
    this.children = [];
    this.html = null;
    this.ownText = v == null ? "" : String(v);
  }
  get innerHTML() { return this.html ?? this.ownText; }
  set innerHTML(v) {
    this.children.forEach((c) => { c.parentNode = null; });
    this.children = [];
    this.ownText = "";
    this.html = String(v);
  }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  removeEventListener(type, fn) {
    const l = this.listeners.get(type);
    if (l) this.listeners.set(type, l.filter((f) => f !== fn));
  }
  getBoundingClientRect() { return { left: 0, top: 0, right: 920, bottom: 520, width: 920, height: 520, x: 0, y: 0 }; }
  setPointerCapture() {}
  releasePointerCapture() {}
  focus() {}
  blur() {}
  querySelector(sel) { throw new Error("querySelector non è supportato dal self-test (" + sel + "): usa getElementById"); }
  querySelectorAll(sel) { throw new Error("querySelectorAll non è supportato dal self-test (" + sel + "): usa getElementById"); }
}

class Document {
  constructor() { this.ids = new Map(); this.all = []; this.title = ""; this.listeners = new Map(); }
  getElementById(id) { return this.ids.get(String(id)) || null; }
  createElement(tag) { return new Element(this, tag); }
  createElementNS(ns, tag) { return new Element(this, tag, ns); }
  createTextNode(t) { return new TextNode(t); }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(fn); }
  removeEventListener() {}
  querySelector(sel) { throw new Error("document.querySelector non è supportato dal self-test (" + sel + "): usa getElementById"); }
  querySelectorAll(sel) { throw new Error("document.querySelectorAll non è supportato dal self-test (" + sel + "): usa getElementById"); }
}

function lineAt(text, index) { return text.slice(0, index).split("\n").length; }

/** Build the stub DOM: one element for each tag with an id. */
function buildDocument(html) {
  const doc = new Document();
  const body = html.replace(/<script\b[\s\S]*?<\/script>/gi, (m) => " ".repeat(m.length))
    .replace(/<style\b[\s\S]*?<\/style>/gi, (m) => " ".repeat(m.length));
  const tagRe = /<([a-zA-Z][\w-]*)(\s[^<>]*)?>/g;
  const attrRe = /([^\s=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?/g;
  let m;
  while ((m = tagRe.exec(body))) {
    const attrs = {};
    let a;
    const raw = m[2] || "";
    while ((a = attrRe.exec(raw))) attrs[a[1]] = a[2] == null ? "" : a[2].replace(/^["']|["']$/g, "");
    if (!attrs.id) continue;
    const el = new Element(doc, m[1], m[1].toLowerCase() === "svg" ? SVG_NS : undefined);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  }
  return doc;
}

function extractScripts(html) {
  const out = [];
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html))) {
    const start = m.index + m[0].indexOf(">") + 1;
    out.push({ attrs: m[1] || "", code: m[2], line: lineAt(html, start) });
  }
  return out;
}

/** Offline rule: no remote script, style, frame, image or network call. */
function offlineIssues(html) {
  const issues = [];
  const rules = [
    [/<script\b[^>]*\bsrc\s*=/i, "script esterno (src=)"],
    [/<link\b[^>]*\bhref\s*=\s*["']?\s*(https?:)?\/\//i, "foglio di stile o link remoto"],
    [/<(img|iframe|audio|video|source|embed|object)\b[^>]*\b(src|data)\s*=\s*["']?\s*(https?:)?\/\//i, "risorsa remota"],
    [/@import\b/i, "@import nel CSS"],
    [/url\(\s*["']?\s*(https?:)?\/\//i, "url() remoto nel CSS"],
    [/\bfetch\s*\(/, "chiamata fetch()"],
    [/\bXMLHttpRequest\b/, "XMLHttpRequest"],
    [/\bWebSocket\b/, "WebSocket"],
    [/\bsendBeacon\b/, "navigator.sendBeacon"],
    [/\bimport\s*\(/, "import() dinamico"],
    [/\beval\s*\(|\bnew\s+Function\s*\(/, "eval o new Function"]
  ];
  for (const [re, label] of rules) if (re.test(html)) issues.push("Offline: " + label + " non ammesso");
  return issues;
}

function scanNode(node, where, out) {
  if (!node || out.length > 20) return;
  if (node instanceof TextNode) {
    BAD_TEXT.forEach((re) => { if (re.test(node.textContent)) out.push(where + ": testo «" + node.textContent.slice(0, 80) + "»"); });
    return;
  }
  const texts = [node.ownText, node.html || ""];
  node.attrs.forEach((v, k) => texts.push(k + "=" + v));
  Object.entries(node.style).forEach(([k, v]) => { if (typeof v !== "function") texts.push(k + ":" + v); });
  for (const t of texts) {
    for (const re of BAD_TEXT) {
      if (re.test(t)) { out.push(where + " <" + node.tagName.toLowerCase() + ">: «" + String(t).slice(0, 100) + "»"); break; }
    }
  }
  node.children.forEach((c) => scanNode(c, where, out));
}

function domIssues(doc) {
  const out = [];
  doc.ids.forEach((el, id) => { if (!el.parentNode) scanNode(el, "#" + id, out); });
  BAD_TEXT.forEach((re) => { if (re.test(doc.title)) out.push("document.title: «" + doc.title + "»"); });
  return out.map((s) => "Valore non valido nel DOM: " + s);
}

/**
 * Independent check of the engine output: sample the expiry P&L on a wide log grid.
 * Every sign change needs a reported break-even, every zone needs one sign,
 * and no sample may pass the reported max profit or max loss.
 */
export function invariantIssues(summary, api) {
  const out = [];
  if (!summary || !summary.ok || !api || typeof api.pnlExp !== "function") return out;
  const ref = Math.max(summary.spot, ...summary.bes, 1e-9);
  const xs = [0];
  for (let i = 0; i <= 6000; i++) xs.push(ref * 1e-3 * Math.pow(1e6, i / 6000));
  summary.bes.forEach((b) => { xs.push(b * (1 - 1e-7), b * (1 + 1e-7)); });
  xs.sort((a, b) => a - b);
  const vals = xs.map((x) => api.pnlExp(x));
  if (vals.some((v) => !Number.isFinite(v))) return ["Invariante: il P&L a scadenza non è finito su tutta la griglia."];
  const scale = Math.max(1, ...vals.filter((v, i) => xs[i] <= 4 * ref).map((v) => Math.abs(v)));
  const tol = 1e-6 * scale;
  let prev = null;
  for (let i = 0; i < xs.length; i++) {
    const s = vals[i] > tol ? 1 : vals[i] < -tol ? -1 : 0;
    if (s === 0) continue;
    if (prev && prev.s !== s && !summary.bes.some((b) => b >= prev.x - 1e-9 * prev.x && b <= xs[i] * (1 + 1e-9))) {
      out.push("Invariante: il P&L cambia segno tra " + prev.x.toPrecision(6) + " e " + xs[i].toPrecision(6) + " ma non c'è un break-even.");
      break;
    }
    prev = { x: xs[i], s };
  }
  for (const z of summary.zones) {
    if (z.sign === 0) continue;
    const bad = xs.findIndex((x, i) => x > z.from * (1 + 1e-6) && (z.to === null || x < z.to * (1 - 1e-6)) &&
      ((z.sign > 0 && vals[i] < -tol) || (z.sign < 0 && vals[i] > tol)));
    if (bad >= 0) { out.push("Invariante: segno sbagliato nella zona [" + z.from + ", " + (z.to ?? "∞") + "] a S = " + xs[bad].toPrecision(6) + "."); break; }
  }
  const finite = vals.filter((v) => Math.abs(v) < 1e12);
  if (!summary.maxProfitUnbounded && finite.some((v) => v > summary.maxProfit + tol)) out.push("Invariante: un punto del payoff supera il max profit.");
  if (!summary.maxLossUnbounded && finite.some((v) => v < summary.maxLoss - tol)) out.push("Invariante: un punto del payoff è sotto il max loss.");
  summary.bes.forEach((b) => {
    if (Math.abs(api.pnlExp(b)) > tol) out.push("Invariante: il P&L al break-even " + b + " non è zero.");
  });
  return out;
}

function makeEvent(type, target, extra) {
  return Object.assign({
    type, target, currentTarget: target, clientX: 460, clientY: 240, pointerId: 1,
    preventDefault() {}, stopPropagation() {}
  }, extra || {});
}

/**
 * Run the diagram in a vm context with the DOM stub.
 * @param {string} html  content of the HTML file
 * @param {{filename?: string, events?: boolean}} [opts]
 */
export function runDiagram(html, opts = {}) {
  const filename = opts.filename || "diagram.html";
  const doc = buildDocument(html);
  const winListeners = new Map();
  const runtimeErrors = [];
  const win = {
    document: doc,
    console: { log() {}, info() {}, warn() {}, error() {}, debug() {} },
    navigator: { userAgent: "check_diagram" },
    location: { href: pathToFileURL(path.resolve(filename)).href },
    innerWidth: 1280,
    innerHeight: 900,
    setTimeout: () => 0,
    clearTimeout() {},
    requestAnimationFrame: () => 0,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    matchMedia: () => ({ matches: false, addListener() {}, addEventListener() {} }),
    addEventListener(type, fn) { if (!winListeners.has(type)) winListeners.set(type, []); winListeners.get(type).push(fn); },
    removeEventListener() {}
  };
  win.window = win;
  win.self = win;
  const ctx = vm.createContext(win);
  const report = (where, e) => {
    const msg = (e && e.message) ? e.message : String(e);
    runtimeErrors.push(where + ": " + msg);
    if (typeof win.onerror === "function") {
      try { win.onerror(msg, filename, 0, 0, e); } catch { /* the handler itself failed */ }
    }
  };
  const scripts = extractScripts(html);
  scripts.forEach((s, i) => {
    if (/\bsrc\s*=/.test(s.attrs)) return;
    try {
      vm.runInContext(s.code, ctx, { filename: filename + "#script" + (i + 1), lineOffset: s.line - 1, timeout: 30000 });
    } catch (e) {
      const where = String((e && e.stack) || "").split("\n").find((l) => l.includes(filename)) || "";
      report("script " + (i + 1) + (where ? " (" + where.trim() + ")" : ""), e);
    }
  });
  let events = 0;
  if (opts.events !== false && win.__TD__ && win.__TD__.ready) {
    const keys = ["ArrowRight", "ArrowUp", "End", "ArrowLeft", "ArrowDown", "Home", "Enter", " ", "Escape"];
    const targets = doc.all.filter((el) => el.listeners.size > 0);
    for (const el of targets) {
      for (const [type, fns] of el.listeners) {
        const fire = (extra) => {
          for (const fn of fns.slice()) {
            events++;
            try { fn.call(el, makeEvent(type, el, extra)); } catch (e) { report("evento " + type + " su #" + (el.id || el.tagName.toLowerCase()), e); }
          }
        };
        if (type === "input") {
          const lo = Number(el.min), hi = Number(el.max);
          if (Number.isFinite(lo) && Number.isFinite(hi) && el.min !== "" && el.max !== "") {
            for (const v of [(lo + hi) / 2, hi, lo]) { el.value = String(v); fire(); }
          } else fire();
        } else if (type === "keydown") {
          keys.forEach((key) => fire({ key }));
        } else if (type.startsWith("pointer")) {
          fire({ clientX: 460, clientY: 240 });
          fire({ clientX: 5, clientY: 5 });
        } else fire();
      }
    }
  }
  const TD = win.__TD__ || null;
  const TDI = win.__TDI__ || null;
  const handlerIssues = [];
  if (typeof win.onerror !== "function") handlerIssues.push("Manca window.onerror: gli errori JavaScript non arrivano nel titolo.");
  if (!(winListeners.get("unhandledrejection") || []).length) handlerIssues.push("Manca il gestore unhandledrejection.");
  if (!TD) handlerIssues.push("Il motore non ha creato window.__TD__.");
  else if (!TD.ready) handlerIssues.push("Il motore non ha finito (window.__TD__.ready = false).");
  const badValues = TD && TD.api && typeof TD.api.badValues === "function" ? TD.api.badValues() : [];
  const engineErrors = (TDI ? TDI.errors : []).filter((m) => !m.startsWith("JavaScript"));
  const errors = [
    ...offlineIssues(html),
    ...handlerIssues,
    ...runtimeErrors.map((m) => "Errore JavaScript: " + m),
    ...engineErrors,
    ...invariantIssues(TD && TD.summary, TD && TD.api),
    ...domIssues(doc),
    ...badValues.map((v) => "Valore non finito formattato in: " + v)
  ];
  if (String(doc.title).startsWith("ERR:") && !errors.length) errors.push("Il titolo del documento inizia con ERR: " + doc.title);
  return {
    title: doc.title,
    errors: [...new Set(errors)],
    warnings: TDI ? TDI.warnings.slice() : [],
    summary: TD ? TD.summary : null,
    api: TD ? TD.api : null,
    events,
    document: doc
  };
}

/** Replace the CONFIG block between the CONFIG-BEGIN and CONFIG-END markers. */
export function replaceConfig(html, config) {
  const re = /(\/\* ==== CONFIG-BEGIN[^\n]*\*\/\n)[\s\S]*?(\n\/\* ==== CONFIG-END ==== \*\/)/;
  if (!re.test(html)) throw new Error("marcatori CONFIG-BEGIN / CONFIG-END non trovati");
  const body = typeof config === "string" ? config : "const CONFIG = " + JSON.stringify(config, null, 2) + ";";
  return html.replace(re, (m, a, b) => a + body + b);
}

function fmt(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isFinite(v) ? (Math.round(v * 100) / 100).toLocaleString("en-US") : String(v);
  return String(v);
}

function printReport(file, res) {
  const s = res.summary;
  const lines = [];
  lines.push("File: " + file);
  lines.push("Titolo: " + res.title);
  if (s && s.ok) {
    lines.push("Scadenza front: " + s.frontExpiry + " · giorni: " + s.dayCount + " · valuta: " + s.currency);
    lines.push("Break-even a scadenza: " + (s.bes.length ? s.bes.map((b) => b.toFixed(4)).join(" / ") : "nessuno"));
    lines.push("Max profit: " + (s.maxProfitUnbounded ? "illimitato" : fmt(s.maxProfit)) +
      " · Max loss: " + (s.maxLossUnbounded ? "illimitato" : fmt(s.maxLoss)));
    lines.push("P&L al mark: " + fmt(s.pnlMark) + " · P&L chiusura (" + s.closeBasis + "): " + fmt(s.pnlClose) +
      " · Theta 1 g: " + fmt(s.thetaDay));
    lines.push("Zone: " + s.zones.map((z) => (z.sign > 0 ? "+" : z.sign < 0 ? "−" : "0") + "[" + fmt(z.from) + ", " +
      (z.to == null ? "∞" : fmt(z.to)) + "]").join(" "));
    if (s.daily && s.daily.on) lines.push("Vista giornaliera: " + s.daily.days + " colonne, mappa " + s.daily.heatRows + "×" + s.daily.heatCols);
  }
  lines.push("Eventi simulati: " + res.events);
  res.warnings.forEach((w) => lines.push("AVVISO: " + w));
  res.errors.forEach((e) => lines.push("ERRORE: " + e));
  lines.push(res.errors.length ? "RISULTATO: FALLITO (" + res.errors.length + " errori)" : "RISULTATO: OK");
  return lines.join("\n");
}

function main(argv) {
  const args = argv.slice(2);
  const file = args.find((a) => !a.startsWith("--"));
  if (!file) {
    process.stderr.write("Uso: node check_diagram.mjs <file.html> [--json] [--quiet] [--no-events]\n");
    return 2;
  }
  let html;
  try { html = fs.readFileSync(file, "utf8"); } catch (e) {
    process.stderr.write("Non posso leggere " + file + ": " + e.message + "\n");
    return 2;
  }
  const res = runDiagram(html, { filename: file, events: !args.includes("--no-events") });
  if (args.includes("--json")) {
    process.stdout.write(JSON.stringify({ title: res.title, errors: res.errors, warnings: res.warnings, summary: res.summary }, null, 2) + "\n");
  } else if (!args.includes("--quiet") || res.errors.length) {
    process.stdout.write(printReport(file, res) + "\n");
  }
  return res.errors.length ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv);
}
