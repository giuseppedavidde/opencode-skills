// verifica-gate — Enforcement meccanico del blocco ## VERIFICA, Exit-Code Tracking e Task Output Pruning
// Assicura che ogni subagent rispetti il contratto VERIFICA (router.md),
// ancora la confidenza agli exit code reali dei comandi bash (pytest/pylint/mypy) e compatta l'output dei task lunghi.
// Hook: "tool.execute.after" su input.tool === "task" | "bash"
import { existsSync, mkdirSync, appendFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const GATE_LOG_DIR = env.GATE_LOG_DIR || join(homedir(), ".config", "opencode", "stats");
const GATE_LOG_FILE = join(GATE_LOG_DIR, "gate_events.jsonl");

// Session-level tracking for failed verification commands (exit status != 0)
let lastFailedBashCommand = null;

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
  if (!outputText || typeof outputText !== "string") return { present: false, confidenza: null, mechanicalError: false };

  const sectionMatch = outputText.match(/## VERIFICA\b/i);
  const present = !!sectionMatch;

  const confMatch = outputText.match(/confidenza\s*[:：]\s*(\d{1,3})/i);
  const confidenza = confMatch ? parseInt(confMatch[1], 10) : null;

  // Mechanical error detection (tests failed, tracebacks, syntax errors)
  const hasErrorPattern = /\b(FAILED|SyntaxError|AssertionError|Traceback \(most recent call last\))\b/i.test(outputText);

  return { present, confidenza, mechanicalError: hasErrorPattern };
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

function replaceOutputText(output, field, newText) {
  if (field === "direct") return newText;
  if (field === "text") { output.text = newText; return output; }
  if (field === "result") { output.result = newText; return output; }
  if (field === "output") { output.output = newText; return output; }
  return newText;
}

function pruneTaskOutput(text) {
  // Prune long subagent outputs (>1500 chars) to prevent nested context explosion
  if (!text || text.length <= 1500) return text;

  const head = text.slice(0, 650);
  const tailIndex = text.lastIndexOf("## VERIFICA");
  const tail = tailIndex !== -1 ? text.slice(tailIndex) : text.slice(-650);

  return `${head}\n\n... [Output intermedio di task compresso dal verifica-gate per risparmio token (${text.length - 1300} caratteri omessi)] ...\n\n${tail}`;
}

export const VerificaGatePlugin = async ({ directory: _directory }) => {
  ensureLogDir();

  return {
    "tool.execute.after": async (input, output) => {
      try {
        // Track bash execution exit codes for verification tools (pytest, pylint, mypy, python3)
        if (input.tool === "bash") {
          const cmd = (input.args?.command || input.arguments?.command || "").toString();
          const isVerificationCmd = /\b(pytest|pylint|mypy|python3|unittest|npm test)\b/i.test(cmd);
          const { text } = extractText(output);
          const isFailedExit = (output && typeof output.exitCode === "number" && output.exitCode !== 0) ||
                               /\b(FAILED|ERRORS|Exit code: [1-9]|command failed)\b/i.test(text);

          if (isVerificationCmd && isFailedExit) {
            lastFailedBashCommand = { cmd: cmd.slice(0, 80), ts: new Date().toISOString() };
          }
          return;
        }

        if (input.tool !== "task") return;

        const { text, field } = extractText(output);
        const verifica = parseVerifica(text);
        const subagentType = extractSubagentType(input);
        const promptSnippet = extractPromptSnippet(input);

        let processedText = text;
        let warning = "";

        // Check if bash verification command failed in this session
        const hasFailedBash = !!lastFailedBashCommand;
        if (hasFailedBash) {
          warning += `\n\n⚠️ [verifica-gate] EXIT CODE FAILURE: Il comando di verifica \`${lastFailedBashCommand.cmd}\` ha restituito un errore/exit-code != 0. Confidenza ancorata a <= 35.`;
          logEvent(subagentType, "exit_code_failure", 35, promptSnippet);
          lastFailedBashCommand = null; // reset
        }

        if (!verifica.present) {
          warning += "\n\n⚠️ [verifica-gate] Il subagent NON ha compilato il blocco ## VERIFICA. Non riassumere come verificato: ri-delega UNA volta chiedendo di compilare il blocco, oppure segnala all'utente che il risultato non e' verificato.";
          logEvent(subagentType, "missing_verifica", null, promptSnippet);
        } else if ((verifica.confidenza !== null && verifica.confidenza < 40) || hasFailedBash) {
          if (!hasFailedBash) {
            warning += "\n\n⚠️ [verifica-gate] Confidenza < 40: ri-delega a @coder per un'analisi approfondita o segnala l'incompiutezza all'utente.";
            logEvent(subagentType, "low_confidence", verifica.confidenza, promptSnippet);
          }
        }

        if (verifica.mechanicalError && (verifica.confidenza === null || verifica.confidenza >= 70) && !hasFailedBash) {
          warning += "\n\n⚠️ [verifica-gate] Rilevati errori meccanici o fallimenti nei test/traceback nell'output. Verificare attentamente l'esito.";
          logEvent(subagentType, "mechanical_error", verifica.confidenza, promptSnippet);
        }

        // Apply task output pruning for long results
        const prunedText = pruneTaskOutput(processedText) + warning;
        return replaceOutputText(output, field, prunedText);

      } catch (_err) {
        // Non crashare mai il tool execution
      }
    },
  };
};
