// context-store — Persiste i contenuti compressi da headroom su disco
// in modo che i subagent possano leggerli senza che il router ripaghi i token.
// Hook: "tool.execute.after" su tool che contiene "headroom_compress"
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
      const tmpPath = filePath + ".tmp";

      try {
        writeFileSync(tmpPath, content, "utf-8");
        renameSync(tmpPath, filePath);
        console.error(`[context-store] saved ${hash} (${Buffer.byteLength(content, "utf-8")} bytes)`);
      } catch (err) {
        console.error(`[context-store] ERROR writing ${hash}: ${err.message}`);
      }
    },
  };
};
