#!/usr/bin/env node
// stress-repair-context-store.js — Stress del repair su store sintetico legacy.
//
// Uso: node scripts/stress-repair-context-store.js
// Genera 200 file in formato legacy (header riga 1 + index v1) in una dir temp, esegue
// repair-context-store.js --apply, verifica 200/200 riparati + idempotenza al secondo run.
// Non tocca lo store reale. Termina SEMPRE con exit 0.
import { existsSync, readFileSync, writeFileSync, mkdirSync, rmSync, readdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { createHash } from "crypto";
import { execFileSync } from "child_process";
import { performance } from "perf_hooks";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPAIR = join(HERE, "repair-context-store.js");
const SCRATCH = process.env.HR_STRESS_DIR || "/tmp/opencode/headroom-stress";
const DIR = join(SCRATCH, "c_repair");

function sha256(t) {
  return createHash("sha256").update(t, "utf-8").digest("hex").slice(0, 16);
}
function countRealLines(t) {
  const p = t.split("\n");
  if (p.length > 1 && p[p.length - 1] === "") p.pop();
  return p.length;
}

let PASS = 0;
let FAIL = 0;
function check(cond, label) {
  if (cond) PASS++;
  else {
    FAIL++;
    console.log(`  FAIL: ${label}`);
  }
}

function main() {
  rmSync(DIR, { recursive: true, force: true });
  mkdirSync(DIR, { recursive: true });

  const N = 200;
  const hashes = [];
  for (let i = 0; i < N; i++) {
    const nlines = 3 + (i % 40);
    const content = Array.from({ length: nlines }, (_, k) => `legacy line ${i}-${k} value=${(i * 31 + k) % 997}`).join("\n");
    const hash = sha256(content);
    hashes.push(hash);
    const header = `# [selective-retrieval] Index available at ${hash}_index.json | Total lines: ${countRealLines(content)} | Use start_line/end_line to read specific chunks!\n`;
    writeFileSync(join(DIR, `${hash}.txt`), header + content, "utf-8");
    writeFileSync(join(DIR, `${hash}_index.json`), JSON.stringify({
      hash, total_lines: countRealLines(content), total_bytes: Buffer.byteLength(content),
      chunk_size: 50, total_chunks: Math.ceil(countRealLines(content) / 50), chunks: [],
    }, null, 2), "utf-8");
  }
  console.log(`generati ${N} file legacy in ${DIR}`);

  const env = { ...process.env, CONTEXT_STORE_DIR: DIR };
  const t0 = performance.now();
  const out1 = execFileSync("node", [REPAIR, "--apply"], { env, encoding: "utf-8" });
  const ms1 = performance.now() - t0;
  const m1 = out1.match(/riparati=(\d+)/);
  check(m1 && Number(m1[1]) === N, `primo run: riparati=${m1 ? m1[1] : "?"} (atteso ${N})`);
  console.log(`  run1: ${ms1.toFixed(0)}ms -> ${(out1.match(/📊 Report:.*/) || [""])[0].trim()}`);

  // verifica contenuto riparato
  let okContent = 0, okIndex = 0, noHeader = 0;
  for (const hash of hashes) {
    const raw = readFileSync(join(DIR, `${hash}.txt`), "utf-8");
    if (!raw.startsWith("# [selective-retrieval]")) noHeader++;
    if (sha256(raw) === hash) okContent++;
    try {
      const idx = JSON.parse(readFileSync(join(DIR, `${hash}_index.json`), "utf-8"));
      if (idx.format_version === 2 && idx.total_lines === countRealLines(raw)) okIndex++;
    } catch (_e) { /* ignore */ }
  }
  check(noHeader === N, `nessun header legacy residuo (${noHeader}/${N})`);
  check(okContent === N, `sha256(file)==hash per tutti (${okContent}/${N})`);
  check(okIndex === N, `index v2 coerente (${okIndex}/${N})`);
  console.log(`  verifica: noHeader=${noHeader}/${N} sha=${okContent}/${N} index=${okIndex}/${N}`);

  // idempotenza
  const t1 = performance.now();
  const out2 = execFileSync("node", [REPAIR, "--apply"], { env, encoding: "utf-8" });
  const ms2 = performance.now() - t1;
  const m2r = out2.match(/riparati=(\d+)/);
  const m2o = out2.match(/gia_ok=(\d+)/);
  check(m2r && Number(m2r[1]) === 0, `secondo run: riparati=${m2r ? m2r[1] : "?"} (atteso 0)`);
  check(m2o && Number(m2o[1]) === N, `secondo run: gia_ok=${m2o ? m2o[1] : "?"} (atteso ${N})`);
  console.log(`  run2 (idempotente): ${ms2.toFixed(0)}ms -> ${(out2.match(/📊 Report:.*/) || [""])[0].trim()}`);

  const remaining = readdirSync(DIR).filter((f) => f.endsWith(".tmp")).length;
  check(remaining === 0, `nessun .tmp residuo (${remaining})`);

  writeFileSync(join(SCRATCH, "C-results.json"), JSON.stringify({
    n: N, ms_apply: Math.round(ms1 * 100) / 100, ms_idempotent: Math.round(ms2 * 100) / 100,
    noHeader, okContent, okIndex, pass: PASS, fail: FAIL,
  }, null, 2), "utf-8");
  console.log(`\nSUMMARY C: PASS=${PASS} FAIL=${FAIL}`);
}

try {
  main();
} catch (err) {
  console.log(`FATAL C: ${err && err.message ? err.message : err}`);
  FAIL++;
} finally {
  process.exitCode = 0;
}
