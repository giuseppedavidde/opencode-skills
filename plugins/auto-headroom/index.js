// auto-headroom — Middleware automatico di compressione token per OpenCode
// Intercetta gli output dei tool (shell, read, grep, glob, webfetch, ecc.) con lunghezza >= 800 caratteri.
// Salva l'originale in context-store (~/.config/opencode/context-store/<hash>.txt) e genera l'indice dei blocchi (<hash>_index.json).
// Restituisce all'LLM una versione compressa con anteprima strutturata + hash per il Selective Retrieval.
// Previene il doppio inserimento dei token (Double-Trip Token Penalty) salvando fino al 90% di prompt token.
//
// API V2: Plugin.define è un helper identità; esportiamo direttamente la forma { id, setup }.
// (Non importiamo "@opencode/plugin" perché il loader V2 non risolve bare specifiers per i plugin locali.)

import { existsSync, mkdirSync, writeFileSync, renameSync, appendFileSync, readFileSync } from "fs";
import { join } from "path";
import { createHash } from "crypto";
import { homedir } from "os";
import { env } from "process";

const STORE_DIR = env.CONTEXT_STORE_DIR || join(homedir(), ".config", "opencode", "context-store");
const HEADROOM_WORKSPACE_DIR = env.HEADROOM_WORKSPACE_DIR || join(homedir(), ".headroom");
const SHARED_STATS_FILE = join(HEADROOM_WORKSPACE_DIR, "session_stats.jsonl");
const COMPRESSION_THRESHOLD = 800; // soglia minima caratteri per compressione automatica
// Versione del formato dello store: incrementala quando cambia la struttura dei file.
// v1 = header "# [selective-retrieval]..." dentro <hash>.txt (legacy, off-by-one).
// v2 = <hash>.txt VERBATIM, total_lines = righe reali, header solo in preview/index.
const STORE_FORMAT_VERSION = 2;

function ensureDir() {
  if (!existsSync(STORE_DIR)) {
    try {
      mkdirSync(STORE_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

function sha256(content) {
  return createHash("sha256").update(content, "utf-8").digest("hex").slice(0, 16);
}

// Estrae il testo consegnato all'LLM dal result V2 (Tool.Result: { output?, content?, metadata? }).
// content è la forma canonica: stringa oppure array di parti { type:"text", text }.
// Fallback su output / output.output per i tool strutturati (shell, read).
function extractText(result) {
  if (typeof result === "string") return { text: result, kind: "direct" };
  if (!result || typeof result !== "object") return { text: String(result), kind: "string" };
  const c = result.content;
  if (typeof c === "string") return { text: c, kind: "content-string" };
  if (Array.isArray(c)) {
    const texts = c.filter(p => p && p.type === "text" && typeof p.text === "string").map(p => p.text);
    if (texts.length > 0) return { text: texts.join("\n"), kind: "content-array" };
  }
  const o = result.output;
  if (typeof o === "string") return { text: o, kind: "output" };
  if (o && typeof o === "object" && typeof o.output === "string") return { text: o.output, kind: "output.output" };
  return { text: JSON.stringify(result), kind: "stringify" };
}

// Ritorna un NUOVO result con il testo sostituito (execute.after muta event.result, non i campi interni).
function replaceResultText(result, kind, originalText, newText) {
  if (kind === "direct") return newText;
  let updated = result;
  if (kind === "content-string") updated = { ...result, content: newText };
  else if (kind === "content-array") updated = { ...result, content: [{ type: "text", text: newText }] };
  else if (kind === "output") updated = { ...result, output: newText };
  else if (kind === "output.output") updated = { ...result, output: { ...result.output, output: newText } };
  else return newText;
  // Mirror di robustezza: se output.output duplicava il testo, tienilo coerente.
  if (updated && typeof updated === "object" && updated.output && typeof updated.output === "object"
      && updated.output.output === originalText) {
    updated = { ...updated, output: { ...updated.output, output: newText } };
  }
  return updated;
}

// Conta le righe "reali" di un testo in modo coerente con:
//   - readlines() di Python e il read tool (offset/limit);
//   - il contenuto verbatim su disco.
// Un eventuale newline finale NON genera una riga vuota fantasma.
// Definizione: n. segmenti di text.split("\n"), scartando l'ultimo se vuoto.
function countRealLines(text) {
  if (!text) return 0;
  const parts = text.split("\n");
  if (parts.length > 1 && parts[parts.length - 1] === "") parts.pop();
  return parts.length;
}

// Vero se il file è nel formato legacy (header selective-retrieval scritto dentro il .txt).
function isLegacyStoreFile(raw) {
  return /^#\s*\[selective-retrieval\]/.test(raw);
}

// Vero se un file di store esistente è già coerente col formato attuale:
// format_version corrente, nessun header legacy, total_lines == righe reali del file.
// Se non lo è, va riscritto (self-heal dei file prodotti da versioni precedenti).
function isStoreEntryCoherent(filePath, indexPath) {
  try {
    if (!existsSync(filePath) || !existsSync(indexPath)) return false;
    const raw = readFileSync(filePath, "utf-8");
    if (isLegacyStoreFile(raw)) return false;
    const idx = JSON.parse(readFileSync(indexPath, "utf-8"));
    return idx.format_version === STORE_FORMAT_VERSION && idx.total_lines === countRealLines(raw);
  } catch (_e) {
    return false;
  }
}

export function generateIndex(hash, content) {
  const lines = content.split("\n");
  const totalLines = countRealLines(content);
  const chunkSize = 50;
  const chunks = [];

  for (let i = 0; i < totalLines; i += chunkSize) {
    const end = Math.min(i + chunkSize, totalLines);
    const chunkLines = lines.slice(i, end);
    const headings = chunkLines
      .filter(l => /^(#|##|###|\s*"(id|name|ticker|title)":|def\s+|class\s+|export\s+)/i.test(l.trim()))
      .map(l => l.trim().slice(0, 60));

    chunks.push({
      chunk_index: Math.floor(i / chunkSize),
      start_line: i + 1,
      end_line: end,
      preview: chunkLines[0] ? chunkLines[0].slice(0, 70) : "",
      headings: headings,
    });
  }

  return {
    hash: hash,
    format_version: STORE_FORMAT_VERSION,
    total_lines: totalLines,
    total_bytes: Buffer.byteLength(content, "utf-8"),
    chunk_size: chunkSize,
    total_chunks: chunks.length,
    chunks: chunks,
  };
}

function saveToContextStore(hash, content) {
  ensureDir();
  const filePath = join(STORE_DIR, `${hash}.txt`);
  const indexPath = join(STORE_DIR, `${hash}_index.json`);

  // Salta la scrittura solo se l'entry esistente è già coerente col formato corrente.
  // Altrimenti riscrive (self-heal di file legacy/incoerenti), in modo atomico.
  if (isStoreEntryCoherent(filePath, indexPath)) {
    return; // Già salvato e coerente
  }

  const tmpPath = filePath + ".tmp";
  const tmpIndexPath = indexPath + ".tmp";

  try {
    const indexData = generateIndex(hash, content);
    // Il file .txt contiene il contenuto originale VERBATIM (nessun header):
    // così index.total_lines coincide con le righe reali del file.
    // Il suggerimento selective-retrieval resta nella preview e nell'index JSON.
    writeFileSync(tmpPath, content, "utf-8");
    renameSync(tmpPath, filePath);

    writeFileSync(tmpIndexPath, JSON.stringify(indexData, null, 2), "utf-8");
    renameSync(tmpIndexPath, indexPath);
  } catch (err) {
    console.error(`[auto-headroom] Error writing ${hash}: ${err.message}`);
  }
}

// Registra l'auto-compressione nel file stats condiviso di headroom (~/.headroom/session_stats.jsonl).
// Riusa il meccanismo esistente _read_shared_events del MCP server.
function appendAutoHeadroomEvent(hash, originalBytes, injectedBytes) {
  try {
    if (!existsSync(HEADROOM_WORKSPACE_DIR)) {
      mkdirSync(HEADROOM_WORKSPACE_DIR, { recursive: true });
    }
    const inputTokens = Math.round(originalBytes / 4);
    const outputTokens = Math.round(injectedBytes / 4);
    const event = {
      type: "compress",
      source: "opencode-plugin",
      hash: hash,
      original_bytes: originalBytes,
      injected_bytes: injectedBytes,
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      tokens_saved: Math.max(0, inputTokens - outputTokens),
      savings_percent: originalBytes > 0
        ? Math.max(0, Math.round((1 - injectedBytes / originalBytes) * 1000) / 10)
        : 0,
      timestamp: Date.now() / 1000,
      pid: process.pid,
    };
    appendFileSync(SHARED_STATS_FILE, JSON.stringify(event) + "\n", "utf-8");
  } catch (err) {
    console.error(`[auto-headroom] Stats event error: ${err.message}`);
  }
}

// Tronca le righe troppo lunghe nel preview: evita che payload single-line o
// JSON compatti facciano ESPANDERE il riassunto iniettato (anomalia preview).
const PREVIEW_LINE_MAX = 300;
function truncatePreviewLine(line) {
  if (line.length <= PREVIEW_LINE_MAX) return line;
  return line.slice(0, PREVIEW_LINE_MAX) + " \u2026";
}

function buildSmartSummary(toolName, text, hash, totalBytes) {
  const lines = text.split("\n");
  const totalLines = lines.length;
  const indexFile = `${hash}_index.json`;
  const txtFile = `${hash}.txt`;

  let headCount = 15;
  let tailCount = 10;
  let errorLines = [];

  // Se è shell o log, cerca righe di errore/warning
  if (toolName === "shell" || toolName === "bash" || /log|test|build/i.test(toolName)) {
    headCount = 12;
    tailCount = 12;
    errorLines = lines.filter(l =>
      /\b(error|failed|exception|traceback|fatal|syntaxerror|assertionerror)\b/i.test(l)
    ).slice(0, 8).map(truncatePreviewLine);
  }

  const canDedupe = totalLines <= headCount + tailCount;
  const headShown = canDedupe ? totalLines : headCount;
  const headLines = lines.slice(0, headShown).map(truncatePreviewLine).join("\n");
  const tailLines = canDedupe ? "" : lines.slice(-tailCount).map(truncatePreviewLine).join("\n");
  const omittedCount = Math.max(0, totalLines - (headCount + tailCount));

  let summary = `⚡ [AUTO-HEADROOM COMPRESSED] Tool '${toolName}' result compressed (${totalBytes} bytes, ${totalLines} lines).\n`;
  summary += `🔑 Context Store Reference: hash=${hash} | File: ${txtFile} | Index: ${indexFile}\n\n`;

  summary += `--- ANTEPRIMA TESTO (Prime ${headShown} righe) ---\n`;
  summary += headLines + "\n";

  if (errorLines.length > 0) {
    summary += `\n--- EVIDENZE / ERRORI RILEVATI (${errorLines.length} righe) ---\n`;
    summary += errorLines.join("\n") + "\n";
  }

  if (omittedCount > 0) {
    summary += `\n... [${omittedCount} righe omesse per risparmio token. Usa hash="${hash}" o fai read su ~/.config/opencode/context-store/${txtFile} con offset/limit] ...\n\n`;
  }

  if (!canDedupe) {
    summary += `--- ANTEPRIMA FINALE (Ultime ${tailCount} righe) ---\n`;
    summary += tailLines + "\n";
  }
  summary += `----------------------------------------------------\n`;
  summary += `📌 Selective Retrieval: Per leggere chunk specifici, consulta ~/.config/opencode/context-store/${indexFile} e usa offset/limit.`;

  return summary;
}

export default {
  id: "auto-headroom",
  async setup(ctx) {
    ensureDir();

    await ctx.tool.hook("execute.after", (event) => {
      try {
        if (event.status !== "completed") return;
        const toolName = typeof event.tool === "string" ? event.tool : "";

        // Ignora i tool interni di gestione headroom e subagent (gestito da verifica-gate)
        if (!toolName ||
            toolName.includes("headroom_compress") ||
            toolName.includes("headroom_retrieve") ||
            toolName.includes("headroom_stats") ||
            toolName === "subagent" ||
            toolName === "task") {
          return;
        }

        // Estrai argomenti (V2: event.input *è* l'oggetto args del tool)
        const args = (event.input && typeof event.input === "object") ? event.input : {};
        const filePathArg = typeof args.path === "string" ? args.path
          : typeof args.filePath === "string" ? args.filePath
          : typeof args.file_path === "string" ? args.file_path : "";

        // Se l'agente sta già facendo selective retrieval (read con offset/limit o start_line/end_line
        // su context-store), lascia passare senza ri-comprimere.
        if (toolName === "read" && filePathArg.includes("context-store")) {
          if (typeof args.offset === "number" || typeof args.limit === "number" ||
              typeof args.start_line === "number" || typeof args.StartLine === "number" ||
              typeof args.end_line === "number" || typeof args.EndLine === "number") {
            return; // Permetti il recupero mirato del chunk senza ri-comprimere!
          }
        }

        const { text, kind } = extractText(event.result);
        if (!text || text.length < COMPRESSION_THRESHOLD) {
          return; // Sotto la soglia, nessuna compressione necessaria
        }

        // Calcola l'hash e genera la versione compressa
        const hash = sha256(text);
        const totalBytes = Buffer.byteLength(text, "utf-8");
        const compressedText = buildSmartSummary(toolName, text, hash, totalBytes);
        const compressedBytes = Buffer.byteLength(compressedText, "utf-8");

        // Guardia anti-espansione: se il preview non riduce i byte, passthrough
        // (nessuna scrittura in context-store, nessun evento stats).
        if (compressedBytes >= totalBytes) {
          return;
        }

        // Salva l'originale in context-store e sostituisci l'output
        saveToContextStore(hash, text);
        appendAutoHeadroomEvent(hash, totalBytes, compressedBytes);
        event.result = replaceResultText(event.result, kind, text, compressedText);

      } catch (err) {
        console.error(`[auto-headroom] Error: ${err.message}`);
        // Non bloccare mai l'esecuzione del tool in caso di errore
      }
    });
  },
};
