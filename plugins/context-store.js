// context-store — Persiste i contenuti compressi da headroom su disco
// e genera un indice a blocchi <hash>_index.json per il Selective Retrieval.
// Hook: "tool.execute.after" su headroom_compress e read tool
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

function findToolName(input) {
  return input && typeof input.tool === "string" ? input.tool : "";
}

function extractContent(input) {
  if (!input) return "";

  let args = null;
  if (input.args && typeof input.args === "object") args = input.args;
  else if (input.arguments && typeof input.arguments === "object") args = input.arguments;
  else if (typeof input.arguments === "string") {
    try { args = JSON.parse(input.arguments); } catch (_) { /* ignore */ }
  }

  if (args && typeof args.content === "string") return args.content;
  if (args && typeof args === "string") return args;

  return "";
}

function extractHash(output) {
  if (!output) return null;

  if (output && typeof output.hash === "string" && output.hash.length > 0) {
    return output.hash;
  }

  const outStr = typeof output === "string" ? output : JSON.stringify(output);
  const match = outStr.match(/hash=([a-zA-Z0-9_-]+)/);
  if (match) return match[1];

  return null;
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

export const ContextStorePlugin = async ({ directory: _directory }) => {
  ensureDir();

  return {
    "tool.execute.after": async (input, output) => {
      const toolName = findToolName(input);
      if (!toolName.includes("headroom_compress")) return;

      const content = extractContent(input);
      if (!content || content.length === 0) return;

      let hash = extractHash(output);
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
    },
  };
};
