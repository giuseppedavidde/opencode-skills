// verifica-gate — Enforcement meccanico del blocco ## VERIFICA, Exit-Code Tracking e Task Output Pruning (API V2)
// Assicura che ogni subagent rispetti il contratto VERIFICA (router.md),
// ancora la confidenza agli exit code reali dei comandi shell (pytest/pylint/mypy) e compatta l'output dei task lunghi.
// Hook V2: ctx.tool.hook("execute.after") sui tool "subagent" (V1: task) e "shell" (V1: bash).
// Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { existsSync, mkdirSync, appendFileSync, statSync, openSync, readSync, closeSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const GATE_LOG_DIR = env.GATE_LOG_DIR || join(homedir(), ".config", "opencode", "stats");
const GATE_LOG_FILE = join(GATE_LOG_DIR, "gate_events.jsonl");

// ── Headroom token-saving tracking ──
// Log eventi condiviso scritto dal plugin auto-headroom e dal MCP (formato JSONL).
const HEADROOM_WORKSPACE_DIR = env.HEADROOM_WORKSPACE_DIR || join(homedir(), ".headroom");
const HEADROOM_STATS_FILE = join(HEADROOM_WORKSPACE_DIR, "session_stats.jsonl");

// Tracking incrementale: offset byte già consumato + cumulativi di sessione.
// Approssimazione accettata: task paralleli possono attribuire lo stesso delta.
const headroomState = {
  offsetBytes: 0,
  sessionTokensSaved: 0,
  compressions: 0,
  originalBytes: 0,
  injectedBytes: 0,
};

function initHeadroomOffset() {
  try {
    headroomState.offsetBytes = existsSync(HEADROOM_STATS_FILE) ? statSync(HEADROOM_STATS_FILE).size : 0;
  } catch (_e) {
    headroomState.offsetBytes = 0;
  }
}

// Legge i byte nuovi (offset→EOF), somma i `compress`, aggiorna offset/cumulativi.
// Edge: se il file è più corto dell'offset (pruned/truncated) → reset, delta 0 (mai negativi).
function readHeadroomDelta() {
  const delta = { tokensSaved: 0, compressions: 0, originalBytes: 0, injectedBytes: 0 };
  try {
    if (!existsSync(HEADROOM_STATS_FILE)) return delta;
    const size = statSync(HEADROOM_STATS_FILE).size;
    if (size < headroomState.offsetBytes) {
      headroomState.offsetBytes = size;
      return delta;
    }
    if (size === headroomState.offsetBytes) return delta;

    const length = size - headroomState.offsetBytes;
    const buf = Buffer.alloc(length);
    const fd = openSync(HEADROOM_STATS_FILE, "r");
    try {
      readSync(fd, buf, 0, length, headroomState.offsetBytes);
    } finally {
      closeSync(fd);
    }
    headroomState.offsetBytes = size;

    for (const raw of buf.toString("utf-8").split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      let evt;
      try {
        evt = JSON.parse(line);
      } catch (_e) {
        continue; // riga corrotta: ignora
      }
      if (evt && evt.type === "compress") {
        delta.tokensSaved += Number(evt.tokens_saved) || 0;
        delta.compressions += 1;
        delta.originalBytes += Number(evt.original_bytes) || 0;
        delta.injectedBytes += Number(evt.injected_bytes) || 0;
      }
    }
    headroomState.sessionTokensSaved += delta.tokensSaved;
    headroomState.compressions += delta.compressions;
    headroomState.originalBytes += delta.originalBytes;
    headroomState.injectedBytes += delta.injectedBytes;
  } catch (_e) {
    // best effort: non bloccare mai
  }
  return delta;
}

function formatTokens(n) {
  return n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function formatKB(bytes) {
  return (bytes / 1024).toFixed(1);
}

function buildTokenSavingLine(delta) {
  if (!delta || delta.tokensSaved === 0) {
    return `📊 Token saving: 0 token salvati durante questo task (nessuna compressione) | sessione: ${formatTokens(headroomState.sessionTokensSaved)} token`;
  }
  return `📊 Token saving: ~${formatTokens(delta.tokensSaved)} token salvati durante questo task (${delta.compressions} compressioni, ${formatKB(delta.originalBytes)} KB → ${formatKB(delta.injectedBytes)} KB iniettati) | sessione: ${formatTokens(headroomState.sessionTokensSaved)} token`;
}

// Inserisce la riga come ULTIMA riga della sezione ## VERIFICA (o in coda se assente).
function appendTokenLine(text, tokenLine) {
  if (!text) return tokenLine;
  return text.includes("## VERIFICA") ? `${text}\n${tokenLine}` : `${text}\n\n${tokenLine}`;
}

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

// Testo del result V2 (content stringa o array di parti text), con fallback su output.
function extractText(result) {
  if (typeof result === "string") return { text: result, kind: "direct" };
  if (!result || typeof result !== "object") return { text: String(result), kind: "string" };
  const c = result.content;
  if (typeof c === "string") return { text: c, kind: "content-string" };
  if (Array.isArray(c)) {
    const texts = c.filter(p => p && p.type === "text" && typeof p.text === "string").map(p => p.text);
    if (texts.length > 0) return { text: texts.join("\n"), kind: "content-array" };
  }
  if (typeof result.output === "string") return { text: result.output, kind: "output" };
  if (result.output && typeof result.output === "object" && typeof result.output.output === "string") {
    return { text: result.output.output, kind: "output.output" };
  }
  return { text: JSON.stringify(result), kind: "stringify" };
}

// Ritorna un NUOVO result con il testo sostituito (execute.after muta event.result).
function replaceResultText(result, kind, originalText, newText) {
  if (kind === "direct") return newText;
  let updated = result;
  if (kind === "content-string") updated = { ...result, content: newText };
  else if (kind === "content-array") updated = { ...result, content: [{ type: "text", text: newText }] };
  else if (kind === "output") updated = { ...result, output: newText };
  else if (kind === "output.output") updated = { ...result, output: { ...result.output, output: newText } };
  else return newText;
  if (updated && typeof updated === "object" && updated.output && typeof updated.output === "object"
      && updated.output.output === originalText) {
    updated = { ...updated, output: { ...updated.output, output: newText } };
  }
  return updated;
}

function extractPromptSnippet(input) {
  const prompt = (input && typeof input.prompt === "string") ? input.prompt : "";
  return prompt.slice(0, 80);
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

function logEvent(subagentType, caseType, confidenza, promptSnippet, extra) {
  ensureLogDir();
  const event = {
    ts: new Date().toISOString(),
    subagent_type: subagentType || "unknown",
    case: caseType,
    confidenza: confidenza,
    prompt_snippet: promptSnippet,
    ...(extra || {}),
  };
  try {
    appendFileSync(GATE_LOG_FILE, JSON.stringify(event) + "\n", "utf-8");
  } catch (_err) {
    // best effort — non crashare mai
  }
}

function pruneTaskOutput(text) {
  // Prune long subagent outputs (>1500 chars) to prevent nested context explosion
  if (!text || text.length <= 1500) return text;

  const head = text.slice(0, 650);
  const tailIndex = text.lastIndexOf("## VERIFICA");
  const tail = tailIndex !== -1 ? text.slice(tailIndex) : text.slice(-650);

  return `${head}\n\n... [Output intermedio di task compresso dal verifica-gate per risparmio token (${text.length - 1300} caratteri omessi)] ...\n\n${tail}`;
}

// Estrae l'exit code dal result V2 (metadata.exit oppure output.exit).
function extractExitCode(result) {
  if (!result || typeof result !== "object") return null;
  if (result.metadata && typeof result.metadata.exit === "number") return result.metadata.exit;
  if (result.output && typeof result.output === "object" && typeof result.output.exit === "number") {
    return result.output.exit;
  }
  return null;
}

export default {
  id: "verifica-gate",
  async setup(ctx) {
    ensureLogDir();
    initHeadroomOffset();

    await ctx.tool.hook("execute.after", (event) => {
      try {
        const toolName = typeof event.tool === "string" ? event.tool : "";

        // Track shell execution exit codes for verification tools (pytest, pylint, mypy, python3)
        if (toolName === "shell" || toolName === "bash") {
          const args = (event.input && typeof event.input === "object") ? event.input : {};
          const cmd = (args.command || "").toString();
          const isVerificationCmd = /\b(pytest|pylint|mypy|python3|unittest|npm test)\b/i.test(cmd);
          const { text } = extractText(event.result);
          const exitCode = extractExitCode(event.result);
          const isFailedExit = event.status === "error" ||
                               (exitCode !== null && exitCode !== 0) ||
                               /\b(FAILED|ERRORS|Exit code: [1-9]|command failed)\b/i.test(text);

          if (isVerificationCmd && isFailedExit) {
            lastFailedBashCommand = { cmd: cmd.slice(0, 80), ts: new Date().toISOString() };
          }
          return;
        }

        if (toolName !== "subagent" && toolName !== "task") return;

        const { text, kind } = extractText(event.result);
        const verifica = parseVerifica(text);
        const subagentType = extractSubagentType(event.input);
        const promptSnippet = extractPromptSnippet(event.input);

        let warning = "";

        // Check if shell verification command failed in this session
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

        // Token saving del task (headroom): delta incrementale dal log eventi condiviso
        const tokenDelta = readHeadroomDelta();
        const tokenLine = buildTokenSavingLine(tokenDelta);
        logEvent(subagentType, "token_saving", null, promptSnippet, {
          tokens_saved: tokenDelta.tokensSaved,
          compressions: tokenDelta.compressions,
          original_bytes: tokenDelta.originalBytes,
          injected_bytes: tokenDelta.injectedBytes,
          session_tokens_saved: headroomState.sessionTokensSaved,
        });

        // Prune + warning, poi inietta la riga token come ULTIMA riga (del ## VERIFICA o in coda)
        const prunedText = pruneTaskOutput(text) + warning;
        const finalText = appendTokenLine(prunedText, tokenLine);
        event.result = replaceResultText(event.result, kind, text, finalText);

      } catch (_err) {
        // Non crashare mai il tool execution
      }
    });
  },
};
