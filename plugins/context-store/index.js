// context-store — Persiste i contenuti compressi da headroom su disco
// e genera un indice a blocchi <hash>_index.json per il Selective Retrieval.
// Hook V2: ctx.tool.hook("execute.after") sul tool headroom_compress
//
// API V2: Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { existsSync, mkdirSync, writeFileSync, renameSync } from "fs";
import { join } from "path";
import { createHash } from "crypto";
import { homedir } from "os";
import { env } from "process";

const STORE_DIR = env.CONTEXT_STORE_DIR || join(homedir(), ".config", "opencode", "context-store");

function ensureDir() {
  if (!existsSync(STORE_DIR)) {
    try {
      mkdirSync(STORE_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

// Testo del result V2 (content stringa o array di parti text), con fallback su output.
function extractText(result) {
  if (typeof result === "string") return result;
  if (!result || typeof result !== "object") return "";
  const c = result.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    const texts = c.filter(p => p && p.type === "text" && typeof p.text === "string").map(p => p.text);
    if (texts.length > 0) return texts.join("\n");
  }
  if (typeof result.output === "string") return result.output;
  if (result.output && typeof result.output === "object") {
    if (typeof result.output.output === "string") return result.output.output;
    if (typeof result.output.hash === "string") return result.output.hash;
  }
  return JSON.stringify(result);
}

function extractContent(input) {
  if (!input) return "";
  if (typeof input.content === "string") return input.content;
  return "";
}

function extractHash(result) {
  if (result && typeof result === "object") {
    if (typeof result.hash === "string" && result.hash.length > 0) return result.hash;
    if (result.output && typeof result.output === "object"
        && typeof result.output.hash === "string" && result.output.hash.length > 0) {
      return result.output.hash;
    }
  }
  const outStr = extractText(result);
  const match = outStr.match(/hash=([a-zA-Z0-9_-]+)/);
  return match ? match[1] : null;
}

function sha256(content) {
  return createHash("sha256").update(content, "utf-8").digest("hex").slice(0, 16);
}

function generateIndex(hash, content) {
  const lines = content.split("\n");
  const totalLines = lines.length;
  const chunkSize = 50; // 50 lines per chunk for selective retrieval
  const chunks = [];

  for (let i = 0; i < totalLines; i += chunkSize) {
    const end = Math.min(i + chunkSize, totalLines);
    const chunkLines = lines.slice(i, end);
    const headings = chunkLines.filter(l => /^(#|##|###|\s*"(id|name|ticker|title)":)/i.test(l.trim())).map(l => l.trim().slice(0, 60));

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
    total_lines: totalLines,
    total_bytes: Buffer.byteLength(content, "utf-8"),
    chunk_size: chunkSize,
    total_chunks: chunks.length,
    chunks: chunks,
  };
}

export default {
  id: "context-store",
  async setup(ctx) {
    ensureDir();

    await ctx.tool.hook("execute.after", (event) => {
      if (event.status !== "completed") return;
      const toolName = typeof event.tool === "string" ? event.tool : "";
      if (!toolName.includes("headroom_compress")) return;

      const content = extractContent(event.input);
      if (!content || content.length === 0) return;

      let hash = extractHash(event.result);
      if (!hash) {
        hash = sha256(content);
      }

      const filePath = join(STORE_DIR, `${hash}.txt`);
      const indexPath = join(STORE_DIR, `${hash}_index.json`);
      const tmpPath = filePath + ".tmp";
      const tmpIndexPath = indexPath + ".tmp";

      try {
        const indexData = generateIndex(hash, content);
        const indexedHeader = `# [selective-retrieval] Index available at ${hash}_index.json | Total lines: ${indexData.total_lines} | Use start_line/end_line to read specific chunks!\n`;
        const contentWithHeader = indexedHeader + content;

        writeFileSync(tmpPath, contentWithHeader, "utf-8");
        renameSync(tmpPath, filePath);

        writeFileSync(tmpIndexPath, JSON.stringify(indexData, null, 2), "utf-8");
        renameSync(tmpIndexPath, indexPath);

        console.error(`[context-store] saved ${hash} (${indexData.total_bytes} bytes, ${indexData.total_chunks} chunks index)`);
      } catch (err) {
        console.error(`[context-store] ERROR writing ${hash}: ${err.message}`);
      }
    });
  },
};
