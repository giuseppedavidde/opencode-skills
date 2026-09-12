#!/usr/bin/env node
// repair-context-store.js — Ripara lo store del plugin auto-headroom al formato corrente.
//
// Uso:
//   node scripts/repair-context-store.js            # DRY-RUN (default, non scrive)
//   node scripts/repair-context-store.js --apply    # applica le riparazioni
//
// Cosa fa: scansiona STORE_DIR (`$CONTEXT_STORE_DIR` o ~/.config/opencode/context-store),
// individua i <hash>.txt in formato legacy (riga 1 = header "# [selective-retrieval]..."),
// rimuove l'header (il file torna VERBATIM) e riscrive <hash>_index.json coerente
// (format_version, total_lines = righe reali). Riscrive anche index mancanti/incoerenti.
// Scritture atomiche (tmp + rename). Verifica sha256(contenuto) == nome file prima di toccare.
import { existsSync, readdirSync, readFileSync, writeFileSync, renameSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { createHash } from "crypto";
import { env } from "process";
import { generateIndex } from "../plugins/auto-headroom.js";

const STORE_DIR = env.CONTEXT_STORE_DIR || join(homedir(), ".config", "opencode", "context-store");
const APPLY = process.argv.includes("--apply");
const HASH_RE = /^([a-f0-9]{16})\.txt$/;
const LEGACY_HEADER_RE = /^#\s*\[selective-retrieval\]/;

function sha256(text) {
  return createHash("sha256").update(text, "utf-8").digest("hex").slice(0, 16);
}

function stripLegacyHeader(raw) {
  if (!LEGACY_HEADER_RE.test(raw)) return raw;
  const nl = raw.indexOf("\n");
  return nl >= 0 ? raw.slice(nl + 1) : "";
}

function atomicWrite(path, data) {
  const tmp = path + ".tmp";
  writeFileSync(tmp, data, "utf-8");
  renameSync(tmp, path);
}

function main() {
  if (!existsSync(STORE_DIR)) {
    console.log(`❌ STORE_DIR non trovato: ${STORE_DIR}`);
    process.exit(1);
  }
  const files = readdirSync(STORE_DIR).filter((f) => HASH_RE.test(f)).sort();
  console.log(`🔧 repair-context-store ${APPLY ? "[APPLY]" : "[DRY-RUN]"} su ${STORE_DIR}`);
  console.log(`   file .txt trovati: ${files.length}\n`);

  let scanned = 0;
  let legacy = 0;
  let repaired = 0;
  let ok = 0;
  let mismatch = 0;
  let errors = 0;

  for (const file of files) {
    scanned++;
    const hash = file.replace(/\.txt$/, "");
    const txtPath = join(STORE_DIR, file);
    const indexPath = join(STORE_DIR, `${hash}_index.json`);
    try {
      const raw = readFileSync(txtPath, "utf-8");
      const hasHeader = LEGACY_HEADER_RE.test(raw);
      const content = hasHeader ? stripLegacyHeader(raw) : raw;

      if (sha256(content) !== hash) {
        mismatch++;
        console.log(`   ⚠️  ${hash}: sha256(contenuto) != nome file — SALTATO (file estraneo?)`);
        continue;
      }

      const wanted = generateIndex(hash, content);
      let existing = null;
      try {
        existing = JSON.parse(readFileSync(indexPath, "utf-8"));
      } catch (_e) {
        existing = null;
      }
      const coherent =
        !hasHeader &&
        existing !== null &&
        existing.format_version === wanted.format_version &&
        existing.total_lines === wanted.total_lines &&
        existing.total_chunks === wanted.total_chunks;
      if (coherent) {
        ok++;
        continue;
      }

      if (hasHeader) legacy++;
      const fileLines = raw.split("\n").length;
      if (APPLY) {
        if (hasHeader) atomicWrite(txtPath, content);
        atomicWrite(indexPath, JSON.stringify(wanted, null, 2));
      }
      repaired++;
      console.log(`   ${APPLY ? "✅ riparato" : "🔎 da riparare"} ${hash}: righe file ${fileLines} -> ${wanted.total_lines} (format v${wanted.format_version})`);
    } catch (err) {
      errors++;
      console.log(`   ❌ ${hash}: ${err.message}`);
    }
  }

  console.log(`\n📊 Report: scansionati=${scanned} legacy=${legacy} ${APPLY ? "riparati" : "da_riparare"}=${repaired} gia_ok=${ok} hash_mismatch=${mismatch} errori=${errors}`);
  if (!APPLY && repaired > 0) {
    console.log("   Rilancia con --apply per applicare le riparazioni.");
  }
  process.exit(errors > 0 ? 1 : 0);
}

main();
