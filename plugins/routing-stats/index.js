// routing-stats — Telemetria LIVE delle decisioni di routing (API V2)
// Registra ogni delegazione a subagent con il blocco VERIFICA.
// Hook V2: ctx.tool.hook("execute.after") sul tool "subagent" (in V1 era "task").
// Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { existsSync, mkdirSync, appendFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const STATS_DIR = env.STATS_DIR || join(homedir(), ".config", "opencode", "stats");
const STATS_FILE = join(STATS_DIR, "routing_events.jsonl");

function ensureDir() {
  if (!existsSync(STATS_DIR)) {
    try {
      mkdirSync(STATS_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

// Testo del result V2 (content stringa o array di parti text), con fallback su output.
function extractText(result) {
  if (typeof result === "string") return result;
  if (!result || typeof result !== "object") return String(result);
  const c = result.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    const texts = c.filter(p => p && p.type === "text" && typeof p.text === "string").map(p => p.text);
    if (texts.length > 0) return texts.join("\n");
  }
  if (typeof result.output === "string") return result.output;
  if (result.output && typeof result.output === "object" && typeof result.output.output === "string") {
    return result.output.output;
  }
  return JSON.stringify(result);
}

function extractSubagentType(input) {
  if (input && typeof input === "object") {
    if (typeof input.agent === "string") return input.agent;
    if (typeof input.subagent_type === "string") return input.subagent_type;
  }
  const argsStr = JSON.stringify(input || {});
  const match = argsStr.match(/"(?:agent|subagent_type)"\s*:\s*"([\w-]+)"/);
  return match ? match[1] : null;
}

function extractPromptSnippet(input) {
  const prompt = (input && typeof input.prompt === "string") ? input.prompt : "";
  return prompt.slice(0, 120);
}

function parseVerifica(text) {
  if (!text || typeof text !== "string") return { has_verifica: false, confidenza: null, escalation: null };

  const hasVerifica = text.includes("## VERIFICA");
  const confMatch = text.match(/- confidenza\s*:\s*(\d+)/);
  const escMatch = text.match(/- escalation_consigliata\s*:\s*(s[ìi]|yes|no)(?=\s|$)/m);

  let escalation = null;
  if (escMatch) {
    const val = escMatch[1].toLowerCase();
    escalation = val === "sì" || val === "si" || val === "yes";
  }

  return {
    has_verifica: hasVerifica,
    confidenza: confMatch ? parseInt(confMatch[1], 10) : null,
    escalation_consigliata: escalation,
  };
}

export default {
  id: "routing-stats",
  async setup(ctx) {
    ensureDir();

    await ctx.tool.hook("execute.after", (event) => {
      if (event.tool !== "subagent" && event.tool !== "task") return;

      const subagentType = extractSubagentType(event.input);
      const promptSnippet = extractPromptSnippet(event.input);
      const verifica = parseVerifica(event.status === "completed" ? extractText(event.result) : "");

      const record = {
        ts: new Date().toISOString(),
        subagent_type: subagentType || "unknown",
        prompt_snippet: promptSnippet,
        has_verifica: verifica.has_verifica,
        confidenza: verifica.confidenza,
        escalation_consigliata: verifica.escalation_consigliata,
      };

      try {
        appendFileSync(STATS_FILE, JSON.stringify(record) + "\n", "utf-8");
      } catch (_err) {
        // Non crashare il tool execution
      }
    });
  },
};
