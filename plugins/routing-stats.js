// routing-stats — Telemetria LIVE delle decisioni di routing
// Registra ogni delegazione a subagent con il blocco VERIFICA.
// Hook: "tool.execute.after" su input.tool === "task"
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

function extractSubagentType(input) {
  // Prefer input.args (structured object)
  if (input.args && input.args.subagent_type) return input.args.subagent_type;
  // Fallback: input.arguments
  if (input.arguments && typeof input.arguments === "object"
      && input.arguments.subagent_type) return input.arguments.subagent_type;
  // Regex fallback su stringa
  const argsStr = typeof input.arguments === "string"
    ? input.arguments : JSON.stringify(input.arguments || input.args || {});
  const match = argsStr.match(/"subagent_type"\s*:\s*"([\w-]+)"/);
  return match ? match[1] : null;
}

function extractPromptSnippet(input) {
  let prompt = "";
  if (input.args && typeof input.args.prompt === "string") prompt = input.args.prompt;
  else if (input.arguments && typeof input.arguments.prompt === "string") prompt = input.arguments.prompt;
  return prompt.slice(0, 120);
}

function parseVerifica(output) {
  const outStr = typeof output === "string" ? output : JSON.stringify(output);
  if (!outStr || typeof outStr !== "string") return { has_verifica: false, confidenza: null, escalation: null };

  const hasVerifica = outStr.includes("## VERIFICA");
  const confMatch = outStr.match(/- confidenza\s*:\s*(\d+)\s*$/m);
  const escMatch = outStr.match(/- escalation_consigliata\s*:\s*(s[ìi]|yes|no)\s*$/m);

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

export const RoutingStatsPlugin = async ({ directory: _directory }) => {
  ensureDir();

  return {
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "task") return;

      const subagentType = extractSubagentType(input);
      const promptSnippet = extractPromptSnippet(input);
      const verifica = parseVerifica(output);

      const event = {
        ts: new Date().toISOString(),
        subagent_type: subagentType || "unknown",
        prompt_snippet: promptSnippet,
        has_verifica: verifica.has_verifica,
        confidenza: verifica.confidenza,
        escalation_consigliata: verifica.escalation_consigliata,
      };

      try {
        appendFileSync(STATS_FILE, JSON.stringify(event) + "\n", "utf-8");
      } catch (_err) {
        // Non crashare il tool execution
      }
    },
  };
};
