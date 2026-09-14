#!/usr/bin/env node
// stress-headroom.js — Stress test del plugin auto-headroom (v2) in isolamento.
//
// Uso:
//   node scripts/stress-headroom.js
//       Run completo (A): threshold, round-trip, index, eventi, scaling, concorrenza, volume, saving.
//   node scripts/stress-headroom.js --emit-for-mcp <storeDir> <wsDir> <outJson>
//       Helper E2E: comprime N payload in <storeDir> (env) e scrive le origini in <outJson>.orig/.
//
// Non tocca lo store reale: usa CONTEXT_STORE_DIR / HEADROOM_WORKSPACE_DIR temporanei.
// Termina SEMPRE con exit 0 (PASS/FAIL stampati internamente).
import { existsSync, readFileSync, writeFileSync, mkdirSync, rmSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { createHash } from "crypto";
import { performance } from "perf_hooks";

const SCRATCH = process.env.HR_STRESS_DIR || "/tmp/opencode/headroom-stress";
const ARGS = process.argv.slice(2);

function sha256(t) {
  return createHash("sha256").update(t, "utf-8").digest("hex").slice(0, 16);
}
function countRealLines(t) {
  if (!t) return 0;
  const p = t.split("\n");
  if (p.length > 1 && p[p.length - 1] === "") p.pop();
  return p.length;
}
function extractHash(s) {
  const m = s.match(/hash=([a-f0-9]{16})/);
  return m ? m[1] : null;
}
function mb(bytes) {
  return Math.round((bytes / 1048576) * 100) / 100;
}

// ── payload builders ──
const UNIT = "Line of log content with numbers 12345 and some text for compression";
function makeAscii(target) {
  const out = [];
  let n = 0;
  while (n < target) {
    const line = `${out.length + 1}: ${UNIT}`;
    out.push(line);
    n += line.length + 1;
  }
  const s = out.join("\n");
  return s.length > target ? s.slice(0, target) : s;
}
function makeJson(target) {
  const rows = [];
  let n = 2;
  while (n < target) {
    const obj = { id: rows.length, name: `item-${rows.length}`, value: rows.length * 3.14, tags: ["a", "b"] };
    const row = JSON.stringify(obj);
    rows.push(row);
    n += row.length + 1;
  }
  return ("[" + rows.join(",") + "]").slice(0, target).padEnd(target, " ");
}
function makeCode(target) {
  const line = "  const value = compute(input, config) ?? defaultVal; // comment";
  const out = [];
  let n = 0;
  while (n < target) {
    out.push(line);
    n += line.length + 1;
  }
  return out.join("\n").slice(0, target);
}
function makeUnicode(target) {
  const unit = "😀 àèìòù 漢字 ";
  let s = "";
  while (s.length < target) s += unit;
  return s;
}
function makeQuasiBinary(target) {
  const out = [];
  let seed = 123456789;
  for (let i = 0; i < target; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    out.push(String.fromCharCode(32 + (seed % 224)));
  }
  return out.join("");
}
const BUILDERS = {
  log: makeAscii,
  json: makeJson,
  code: makeCode,
  single: (t) => "A".repeat(t),
  unicode: makeUnicode,
  repeated: (t) => (UNIT + "\n").repeat(Math.ceil(t / (UNIT.length + 1))).slice(0, t),
  quasibin: makeQuasiBinary,
};

const RESULTS = { sections: {}, pass: 0, fail: 0 };
function check(cond, label) {
  if (cond) RESULTS.pass++;
  else {
    RESULTS.fail++;
    console.log(`  FAIL: ${label}`);
  }
  return cond;
}

async function main() {
  // ── modalità helper E2E ──
  if (ARGS[0] === "--emit-for-mcp") {
    const [, storeDir, wsDir, outJson] = ARGS;
    process.env.CONTEXT_STORE_DIR = storeDir;
    process.env.HEADROOM_WORKSPACE_DIR = wsDir;
    mkdirSync(storeDir, { recursive: true });
    mkdirSync(`${outJson}.orig`, { recursive: true });
    const { AutoHeadroomPlugin } = await import("../plugins/auto-headroom.js");
    const hook = (await AutoHeadroomPlugin({ directory: process.cwd() }))["tool.execute.after"];
    const list = [];
    for (let i = 0; i < 20; i++) {
      const payload = makeAscii(3000 + i * 137) + `\n// e2e nonce ${i}`;
      await hook({ tool: "bash", args: {} }, { output: payload });
      const hash = sha256(payload);
      const orig = `${outJson}.orig/${i}.bin`;
      writeFileSync(orig, payload, "utf-8");
      list.push({ hash, orig, name: `payload-${i}`, bytes: Buffer.byteLength(payload) });
    }
    writeFileSync(outJson, JSON.stringify(list), "utf-8");
    console.log(`emit-for-mcp: ${list.length} payload -> ${storeDir}`);
    return;
  }

  // ── run A ──
  const STORE = join(SCRATCH, "store");
  const WS = join(SCRATCH, "ws");
  process.env.CONTEXT_STORE_DIR = STORE;
  process.env.HEADROOM_WORKSPACE_DIR = WS;
  rmSync(STORE, { recursive: true, force: true });
  rmSync(WS, { recursive: true, force: true });
  mkdirSync(STORE, { recursive: true });
  mkdirSync(WS, { recursive: true });
  const EVENTS = join(WS, "session_stats.jsonl");

  const { AutoHeadroomPlugin } = await import("../plugins/auto-headroom.js");
  const hook = (await AutoHeadroomPlugin({ directory: process.cwd() }))["tool.execute.after"];

  function eventsValid() {
    if (!existsSync(EVENTS)) return { count: 0, invalid: 0, last: null };
    const lines = readFileSync(EVENTS, "utf-8").split("\n").filter((l) => l.trim());
    let invalid = 0;
    let last = null;
    for (const l of lines) {
      try {
        last = JSON.parse(l);
      } catch (_e) {
        invalid++;
      }
    }
    return { count: lines.length, invalid, last };
  }

  function verifyEntry(hash, payload) {
    const txt = join(STORE, `${hash}.txt`);
    const idx = join(STORE, `${hash}_index.json`);
    if (!existsSync(txt) || !existsSync(idx)) return { file: false, index: false, rt: false };
    const rt = readFileSync(txt).equals(Buffer.from(payload, "utf-8"));
    let indexOk = false;
    try {
      const o = JSON.parse(readFileSync(idx, "utf-8"));
      indexOk = o.format_version === 2 && o.total_lines === countRealLines(payload);
    } catch (_e) {
      indexOk = false;
    }
    return { file: true, index: indexOk, rt };
  }

  async function runOne(label, type, payload) {
    const before = process.memoryUsage();
    const t0 = performance.now();
    const res = await hook({ tool: "bash", args: {} }, { output: payload });
    const ms = performance.now() - t0;
    const after = process.memoryUsage();
    const origBytes = Buffer.byteLength(payload, "utf-8");
    const compressed = !!(res && typeof res.output === "string");
    const row = {
      label, type, chars: payload.length, bytes: origBytes, ms: Math.round(ms * 100) / 100,
      heapMB: mb(after.heapUsed - before.heapUsed), rssMB: mb(after.rss),
      compressed, previewBytes: compressed ? Buffer.byteLength(res.output, "utf-8") : origBytes,
    };
    if (origBytes < 800) {
      check(!compressed, `${label}: atteso NON compresso`);
      check(!existsSync(join(STORE, `${sha256(payload)}.txt`)), `${label}: nessun file scritto`);
      row.roundtrip = "n/a";
    } else {
      // v2.1: sopra soglia => compresso SOLO se riduce i byte; altrimenti passthrough.
      check(!compressed || row.previewBytes < origBytes, `${label}: se compresso, preview < originale`);
      if (!compressed) {
        check(!existsSync(join(STORE, `${sha256(payload)}.txt`)), `${label}: passthrough senza file scritto`);
        row.roundtrip = "n/a";
      }
      if (compressed) {
        const hash = extractHash(res.output);
        check(hash === sha256(payload), `${label}: hash nel preview corretto`);
        const v = verifyEntry(hash, payload);
        check(v.rt, `${label}: round-trip byte-identico`);
        check(v.index, `${label}: index coerente (v2/total_lines)`);
        row.hash = hash;
        row.roundtrip = v.rt ? "PASS" : "FAIL";
        row.indexOk = v.index;
        const ev = eventsValid();
        check(ev.invalid === 0 && ev.last && ev.last.hash === hash,
          `${label}: evento JSONL valido per hash`);
      }
    }
    row.savePct = origBytes > 0 ? Math.round((1 - row.previewBytes / origBytes) * 1000) / 10 : 0;
    row.tokensSaved = Math.max(0, Math.round((origBytes - row.previewBytes) / 4));
    return row;
  }

  // A1: threshold esatto
  console.log("== A1 threshold esatto ==");
  for (const n of [799, 800, 801]) {
    const row = await runOne(`threshold-${n}`, "single", "x".repeat(n));
    RESULTS.sections[`threshold-${n}`] = row;
    console.log(`  ${n}B -> compressed=${row.compressed} (sopra-soglia: compresso o passthrough)`);
  }

  // A2/A3/A7: size sweep (log) + scaling + saving
  console.log("== A2/A7 size sweep (log) ==");
  const SIZES = [100, 799, 800, 801, 5120, 102400, 1048576, 5242880, 10485760];
  const scaling = [];
  for (let i = 0; i < SIZES.length; i++) {
    const payload = makeAscii(SIZES[i]) + (SIZES[i] >= 800 ? `\n// sweep ${i}` : "");
    const row = await runOne(`size-${SIZES[i]}`, "log", payload);
    scaling.push(row);
    console.log(`  ${SIZES[i]}B: ${row.ms}ms rss=${row.rssMB}MB preview=${row.previewBytes}B save=${row.savePct}%`);
  }
  RESULTS.sections.scaling = scaling;

  // A4: type sweep a 5KB
  console.log("== A4 type sweep (5KB) ==");
  const TYPES = ["log", "json", "code", "single", "unicode", "repeated", "quasibin"];
  const typeRows = [];
  for (const t of TYPES) {
    const payload = BUILDERS[t](5120) + `\n// type ${t}`;
    const row = await runOne(`type-${t}`, t, payload);
    typeRows.push(row);
    console.log(`  ${t}: chars=${row.chars} bytes=${row.bytes} save=${row.savePct}% rt=${row.roundtrip}`);
  }
  RESULTS.sections.types = typeRows;

  // A7b: payload realistici
  console.log("== A7b payload realistici ==");
  const bigLog = Array.from({ length: 3000 }, (_, i) =>
    i % 250 === 0
      ? `2026-09-12T10:${String(i % 60).padStart(2, "0")}:00Z ERROR service=api request_id=${i} AssertionError: failed at module calculation`
      : `2026-09-12T10:${String(i % 60).padStart(2, "0")}:00Z INFO service=api request_id=${i} processed ok in ${i % 200}ms`
  ).join("\n");
  const bigJson = JSON.stringify(Array.from({ length: 4000 }, (_, i) => ({
    id: i, ticker: "AAPL", score: (i * 7) % 100, signal: i % 2 ? "BUY" : "HOLD", nested: { a: i, b: [i, i + 1] },
  })));
  const source = readFileSync(new URL("../plugins/auto-headroom.js", import.meta.url), "utf-8");
  const realistic = [];
  for (const [name, payload] of [["big-log", bigLog], ["big-json", bigJson], ["plugin-source", source]]) {
    const row = await runOne(`real-${name}`, name, payload);
    realistic.push(row);
    console.log(`  ${name}: ${row.bytes}B -> ${row.previewBytes}B save=${row.savePct}% (${row.tokensSaved} tok) rt=${row.roundtrip}`);
  }
  RESULTS.sections.realistic = realistic;

  // A5: concorrenza
  console.log("== A5 concorrenza (20) ==");
  const base = makeAscii(5000);
  const concPayloads = Array.from({ length: 20 }, (_, i) =>
    i < 2 ? base + "\n// dup" : base + `\n// unique ${i} ${"y".repeat(i * 11)}`
  );
  const evBefore = eventsValid().count;
  const tC0 = performance.now();
  const concRes = await Promise.all(concPayloads.map((p) => hook({ tool: "bash", args: {} }, { output: p })));
  const concMs = performance.now() - tC0;
  let concOk = 0;
  for (let i = 0; i < concPayloads.length; i++) {
    const h = extractHash(concRes[i] && concRes[i].output);
    if (h && h === sha256(concPayloads[i])) {
      const v = verifyEntry(h, concPayloads[i]);
      if (v.rt && v.index) concOk++;
    }
  }
  const evC = eventsValid();
  const tmpLeft = readdirSync(STORE).filter((f) => f.endsWith(".tmp")).length;
  check(concOk === 20, `concorrenza: 20/20 round-trip+index (got ${concOk})`);
  check(evC.count - evBefore === 20 && evC.invalid === 0,
    `concorrenza: 20 eventi JSONL validi (delta ${evC.count - evBefore}, invalid ${evC.invalid})`);
  check(tmpLeft === 0, `concorrenza: nessun .tmp residuo (got ${tmpLeft})`);
  RESULTS.sections.concurrency = { ms: concMs, ok: concOk, events: evC.count, invalid: evC.invalid, tmpLeft };
  console.log(`  ${concOk}/20 ok, events=${evC.count} invalid=${evC.invalid} tmpLeft=${tmpLeft} in ${Math.round(concMs)}ms`);

  // A6: volume 500
  console.log("== A6 volume (500) ==");
  const tV0 = performance.now();
  for (let i = 0; i < 500; i++) {
    const size = 900 + (i % 40) * 200;
    const payload = makeAscii(size) + `\n// vol ${i} ${"z".repeat(i % 17)}`;
    await hook({ tool: "bash", args: {} }, { output: payload });
  }
  const volMs = performance.now() - tV0;
  // audit store
  let pairs = 0, coherent = 0, errors = 0;
  for (const f of readdirSync(STORE)) {
    if (!f.endsWith(".txt")) continue;
    pairs++;
    try {
      const hash = f.replace(/\.txt$/, "");
      const raw = readFileSync(join(STORE, f));
      const idx = JSON.parse(readFileSync(join(STORE, `${hash}_index.json`), "utf-8"));
      const ok = sha256(raw.toString("utf-8")) === hash && idx.format_version === 2 &&
        idx.total_lines === countRealLines(raw.toString("utf-8"));
      if (ok) coherent++;
      else errors++;
    } catch (_e) {
      errors++;
    }
  }
  const evV = eventsValid();
  check(errors === 0 && coherent === pairs && pairs > 0, `volume: ${coherent}/${pairs} coppie coerenti, ${errors} errori`);
  check(evV.invalid === 0, `volume: eventi tutti validi (invalid=${evV.invalid})`);
  RESULTS.sections.volume = { n: 500, ms: volMs, opsPerSec: Math.round((500 / volMs) * 1000 * 100) / 100, pairs, coherent, errors, events: evV.count };
  console.log(`  ${pairs} coppie, coherent=${coherent}, errors=${errors}, ${Math.round((500 / volMs) * 1000)} ops/s, events=${evV.count}`);

  writeFileSync(join(SCRATCH, "A-results.json"), JSON.stringify(RESULTS, null, 2), "utf-8");
  console.log(`\nSUMMARY A: PASS=${RESULTS.pass} FAIL=${RESULTS.fail}`);
}

main().catch((e) => {
  console.log(`FATAL A: ${e && e.message ? e.message : e}`);
  RESULTS.fail++;
  try {
    writeFileSync(join(SCRATCH, "A-results.json"), JSON.stringify(RESULTS, null, 2), "utf-8");
  } catch (_e) { /* ignore */ }
}).finally(() => {
  process.exitCode = 0;
});
