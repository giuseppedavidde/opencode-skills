// verifica-gate — Enforcement meccanico del blocco ## VERIFICA
// Assicura che ogni subagent rispetti il contratto VERIFICA (router.md).
// Hook: "tool.execute.after" su input.tool === "task"
import { existsSync, mkdirSync, appendFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const GATE_LOG_DIR = env.GATE_LOG_DIR || join(homedir(), ".config", "opencode", "stats");
const GATE_LOG_FILE = join(GATE_LOG_DIR, "gate_events.jsonl");

function ensureLogDir() {
  if (!existsSync(GATE_LOG_DIR)) {
    try {
      mkdirSync(GATE_LOG_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

function extractText(output) {
  if (typeof output === "string") return { text: output, field: "direct" };
  if (output && typeof output === "object") {
    if (typeof output.text === "string") return { text: output.text, field: "text" };
    if (typeof output.result === "string") return { text: output.result, field: "result" };
    if (typeof output.output === "string") return { text: output.output, field: "output" };
    return { text: JSON.stringify(output), field: "stringify" };
  }
  return { text: String(output), field: "string" };
}

function extractPromptSnippet(input) {
  let prompt = "";
  if (input.args && typeof input.args.prompt === "string") prompt = input.args.prompt;
  else if (input.arguments && typeof input.arguments.prompt === "string") prompt = input.arguments.prompt;
  return prompt.slice(0, 80);
}

function extractSubagentType(input) {
  if (input.args && input.args.subagent_type) return input.args.subagent_type;
  if (input.arguments && typeof input.arguments === "object"
      && input.arguments.subagent_type) return input.arguments.subagent_type;
  const argsStr = typeof input.arguments === "string"
    ? input.arguments : JSON.stringify(input.arguments || input.args || {});
  const match = argsStr.match(/"subagent_type"\s*:\s*"([\w-]+)"/);
  return match ? match[1] : null;
}

function parseVerifica(outputText) {
  if (!outputText || typeof outputText !== "string") return { present: false, confidenza: null };

  const sectionMatch = outputText.match(/## VERIFICA\b/i);
  if (!sectionMatch) return { present: false, confidenza: null };

  const confMatch = outputText.match(/confidenza\s*[:：]\s*(\d{1,3})/i);
  const confidenza = confMatch ? parseInt(confMatch[1], 10) : null;

  return { present: true, confidenza };
}

function logEvent(subagentType, caseType, confidenza, promptSnippet) {
  ensureLogDir();
  const event = {
    ts: new Date().toISOString(),
    subagent_type: subagentType || "unknown",
    case: caseType,
    confidenza: confidenza,
    prompt_snippet: promptSnippet,
  };
  try {
    appendFileSync(GATE_LOG_FILE, JSON.stringify(event) + "\n", "utf-8");
  } catch (_err) {
    // best effort — non crashare mai
  }
}

function mutateOutput(output, field, appendText) {
  if (field === "direct") return output + appendText;
  if (field === "text") {
    output.text = (output.text || "") + appendText;
    return output;
  }
  if (field === "result") {
    output.result = (output.result || "") + appendText;
    return output;
  }
  if (field === "output") {
    output.output = (output.output || "") + appendText;
    return output;
  }
  // field "stringify" o altro: sostituisci l'intero output con stringa
  return output + appendText;
}

export const VerificaGatePlugin = async ({ directory: _directory }) => {
  ensureLogDir();

  return {
    "tool.execute.after": async (input, output) => {
      try {
        if (input.tool !== "task") return;

        const { text, field } = extractText(output);
        const verifica = parseVerifica(text);
        const subagentType = extractSubagentType(input);
        const promptSnippet = extractPromptSnippet(input);

        if (!verifica.present) {
          const warning = "\n\n\u26a0\ufe0f [verifica-gate] Il subagent NON ha compilato il blocco ## VERIFICA. Non riassumere come verificato: ri-delega UNA volta chiedendo di compilare il blocco, oppure segnala all'utente che il risultato non e' verificato.";
          logEvent(subagentType, "missing_verifica", null, promptSnippet);
          return mutateOutput(output, field, warning);
        }

        if (verifica.confidenza !== null && verifica.confidenza < 40) {
          const warning = "\n\n\u26a0\ufe0f [verifica-gate] Confidenza < 40: chiedi all'utente se vuole escalation a glm-5.3 (@general) o se va bene cosi (soglie in router.md).";
          logEvent(subagentType, "low_confidence", verifica.confidenza, promptSnippet);
          return mutateOutput(output, field, warning);
        }

        // Nessuna mutazione: verifica presente e confidenza >= 40 o assente
      } catch (_err) {
        // Non crashare mai il tool execution
      }
    },
  };
};
