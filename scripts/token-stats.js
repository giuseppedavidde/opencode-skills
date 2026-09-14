#!/usr/bin/env node
// token-stats.js — Report aggregato del token saving di headroom (zero dipendenze).
//
// Fonti:
//   - ~/.headroom/session_stats.jsonl           (compress + retrieve; HEADROOM_WORKSPACE_DIR)
//   - ~/.config/opencode/stats/gate_events.jsonl (token_saving per-agente; GATE_LOG_DIR)
//   - ~/.config/opencode/context-store/<hash>.txt (dimensioni per stimare i retrieve; CONTEXT_STORE_DIR)
//
// Uso: node scripts/token-stats.js [--json]
// Gestisce file mancanti/righe corrotte senza crash. Termina sempre con exit 0.
import { existsSync, readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const HOME = homedir();
const HEADROOM_WS = env.HEADROOM_WORKSPACE_DIR || join(HOME, ".headroom");
const SESSION_STATS = join(HEADROOM_WS, "session_stats.jsonl");
const GATE_DIR = env.GATE_LOG_DIR || join(HOME, ".config", "opencode", "stats");
const GATE_EVENTS = join(GATE_DIR, "gate_events.jsonl");
const STORE_DIR = env.CONTEXT_STORE_DIR || join(HOME, ".config", "opencode", "context-store");
const JSON_MODE = process.argv.includes("--json");

function fmtNum(n) {
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
function fmtBytes(b) {
  if (b >= 1048576) return `${(b / 1048576).toFixed(2)} MB`;
  if (b >= 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${b} B`;
}
function dayKey(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function parseTs(evt) {
  if (typeof evt.timestamp === "number") return evt.timestamp * 1000;
  if (typeof evt.ts === "string") {
    const t = Date.parse(evt.ts);
    return Number.isNaN(t) ? null : t;
  }
  return null;
}
function readJsonl(path) {
  const out = { exists: existsSync(path), total: 0, invalid: 0, events: [] };
  if (!out.exists) return out;
  try {
    const lines = readFileSync(path, "utf-8").split("\n");
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      out.total++;
      try {
        out.events.push(JSON.parse(line));
      } catch (_e) {
        out.invalid++;
      }
    }
  } catch (_e) {
    /* ignore */
  }
  return out;
}

function storeIndex() {
  const byHash = new Map();
  try {
    if (!existsSync(STORE_DIR)) return byHash;
    for (const f of readdirSync(STORE_DIR)) {
      if (!f.endsWith(".txt")) continue;
      const hash = f.replace(/\.txt$/, "");
      try {
        byHash.set(hash, statSync(join(STORE_DIR, f)).size);
      } catch (_e) {
        /* ignore */
      }
    }
  } catch (_e) {
    /* ignore */
  }
  return byHash;
}

function main() {
  const stats = readJsonl(SESSION_STATS);
  const gate = readJsonl(GATE_EVENTS);
  const store = storeIndex();

  let compressions = 0;
  let tokensSaved = 0;
  let origBytes = 0;
  let injBytes = 0;
  let bytesEvents = 0;
  let retrievals = 0;
  let retrievedBytes = 0;
  let retrievedUnknown = 0;
  const perDay = new Map();
  let minTs = null;
  let maxTs = null;

  for (const evt of stats.events) {
    const ts = parseTs(evt);
    if (ts !== null) {
      if (minTs === null || ts < minTs) minTs = ts;
      if (maxTs === null || ts > maxTs) maxTs = ts;
    }
    if (evt.type === "compress") {
      compressions++;
      const saved = typeof evt.tokens_saved === "number"
        ? evt.tokens_saved
        : Math.max(0, (Number(evt.input_tokens) || 0) - (Number(evt.output_tokens) || 0));
      tokensSaved += saved;
      if (typeof evt.original_bytes === "number") {
        origBytes += evt.original_bytes;
        injBytes += Number(evt.injected_bytes) || 0;
        bytesEvents++;
      }
      if (ts !== null) {
        const k = dayKey(ts);
        const d = perDay.get(k) || { compressions: 0, tokensSaved: 0 };
        d.compressions++;
        d.tokensSaved += saved;
        perDay.set(k, d);
      }
    } else if (evt.type === "retrieve") {
      retrievals++;
      const h = String(evt.hash || "");
      let size = 0;
      let found = false;
      for (const [full, bytes] of store) {
        if (full.startsWith(h)) {
          size = bytes;
          found = true;
          break;
        }
      }
      if (found) retrievedBytes += size;
      else retrievedUnknown++;
    }
  }

  const perAgent = new Map();
  for (const evt of gate.events) {
    if (evt.case !== "token_saving") continue;
    const a = evt.subagent_type || "unknown";
    const d = perAgent.get(a) || { tokensSaved: 0, tasks: 0 };
    d.tokensSaved += Number(evt.tokens_saved) || 0;
    d.tasks++;
    perAgent.set(a, d);
  }

  const reduction = bytesEvents > 0 && origBytes > 0 ? ((origBytes - injBytes) / origBytes) * 100 : 0;
  const retrievedTokens = retrievedBytes / 4;
  const netTokens = tokensSaved - retrievedTokens;

  const today = dayKey(Date.now());
  const since = Date.now() - 7 * 86400000;
  const last7 = [...perDay.entries()]
    .filter(([k]) => Date.parse(k) >= Date.parse(dayKey(since)))
    .sort((a, b) => (a[0] < b[0] ? -1 : 1));

  const result = {
    period: { from: minTs ? new Date(minTs).toISOString() : null, to: maxTs ? new Date(maxTs).toISOString() : null },
    totals: { compressions, tokens_saved: tokensSaved, original_bytes: origBytes, injected_bytes: injBytes, reduction_pct: Math.round(reduction * 10) / 10 },
    today: perDay.get(today) || { compressions: 0, tokensSaved: 0 },
    last7: last7.map(([day, d]) => ({ day, compressions: d.compressions, tokens_saved: d.tokensSaved })),
    per_agent: [...perAgent.entries()].map(([agent, d]) => ({ agent, tokens_saved: d.tokensSaved, tasks: d.tasks })),
    retrieve: { count: retrievals, bytes_estimated: retrievedBytes, tokens_estimated: Math.round(retrievedTokens), unknown: retrievedUnknown },
    net_tokens: Math.round(netTokens),
    verdict: netTokens > 0 ? "headroom sta ottimizzando" : "ATTENZIONE: headroom non ottimizza (net <= 0)",
    sources: { session_stats: { path: SESSION_STATS, exists: stats.exists, lines: stats.total, invalid: stats.invalid },
               gate_events: { path: GATE_EVENTS, exists: gate.exists, lines: gate.total, invalid: gate.invalid },
               context_store: { path: STORE_DIR, files: store.size } },
  };

  if (JSON_MODE) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  const L = [];
  L.push("📊 TOKEN-STATS — headroom");
  L.push(result.period.from ? `Periodo: ${result.period.from.slice(0, 10)} → ${result.period.to.slice(0, 10)}` : "Periodo: (nessun evento)");
  L.push("");
  L.push("TOTALI");
  L.push(`  Compressioni:          ${fmtNum(compressions)}`);
  L.push(`  Token salvati:         ${fmtNum(tokensSaved)}`);
  L.push(`  Bytes orig → iniettati: ${fmtBytes(origBytes)} → ${fmtBytes(injBytes)}  (riduzione ${result.totals.reduction_pct}%)`);
  L.push("");
  L.push("RETRIEVE");
  L.push(`  Retrieve:              ${fmtNum(retrievals)}`);
  L.push(`  Bytes ri-recuperati:   ${fmtBytes(retrievedBytes)} (stima ~${fmtNum(retrievedTokens)} token)` + (retrievedUnknown ? ` [${retrievedUnknown} non risolti]` : ""));
  L.push(`  ⚖️  STIMA NETTA:        ${fmtNum(netTokens)} token  → ${result.verdict}` + (netTokens > 0 ? " ✅" : " ⚠️"));
  L.push("");
  L.push(`OGGI (${today})`);
  L.push(`  Compressioni: ${fmtNum(result.today.compressions)}   Token salvati: ${fmtNum(result.today.tokensSaved)}`);
  L.push("ULTIMI 7 GIORNI");
  if (last7.length === 0) L.push("  (nessun evento)");
  for (const [day, d] of last7) L.push(`  ${day}: comp=${fmtNum(d.compressions)} saved=${fmtNum(d.tokensSaved)}`);
  L.push("");
  L.push("PER AGENTE (da token_saving)");
  if (perAgent.size === 0) L.push("  (nessun evento token_saving)");
  for (const [agent, d] of [...perAgent.entries()].sort((a, b) => b[1].tokensSaved - a[1].tokensSaved)) {
    L.push(`  ${agent} → ${fmtNum(d.tokensSaved)} token salvati (${d.tasks} task)`);
  }
  L.push("");
  L.push("SOURCES");
  L.push(`  session_stats: ${SESSION_STATS}  [${stats.exists ? `${stats.total} righe, ${stats.invalid} corrotte` : "MANCANTE"}]`);
  L.push(`  gate_events:   ${GATE_EVENTS}  [${gate.exists ? `${gate.total} righe, ${gate.invalid} corrotte` : "MANCANTE"}]`);
  L.push(`  context-store: ${STORE_DIR}  [${store.size} file]`);
  console.log(L.join("\n"));
}

try {
  main();
} catch (err) {
  console.log(`FATAL token-stats: ${err && err.message ? err.message : err}`);
} finally {
  process.exitCode = 0;
}
