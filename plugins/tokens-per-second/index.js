// tokens-per-second — Telemetria della velocità di generazione (API V2)
// V1 usava l'hook "event" su "message.updated" + client.app.log (rimossi in V2).
// V2: ctx.event.subscribe() (AsyncIterable) + AbortController nel cleanup di setup().
//   - "message.updated" non esiste più: si usano "session.step.started" / "session.step.ended"
//     (un "step" = una singola chiamata al provider, analogo del vecchio assistant message).
//   - La durata è (step.ended.created - step.started.data.started) in ms.
//   - ctx non espone più client.app.log: il log va su stderr/console (visibile con
//     `opencode --print-logs` in modalità --standalone) + riga JSONL nel file stats.
// Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { appendFileSync, existsSync, mkdirSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { env } from "process";

const STATS_DIR = env.STATS_DIR || join(homedir(), ".config", "opencode", "stats");
const STATS_FILE = join(STATS_DIR, "tokens_per_second.jsonl");

function ensureDir() {
  if (!existsSync(STATS_DIR)) {
    try {
      mkdirSync(STATS_DIR, { recursive: true });
    } catch (_e) {
      // best effort
    }
  }
}

export default {
  id: "tokens-per-second",
  async setup(ctx) {
    ensureDir();

    // Traccia lo start (e il model) di ogni step in-flight, per assistantMessageID.
    const pending = new Map();
    const controller = new AbortController();

    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          try {
            const data = event && event.data ? event.data : {};
            if (event.type === "session.step.started") {
              pending.set(data.assistantMessageID, {
                started: typeof data.started === "number" ? data.started : event.created,
                modelID: data.model && data.model.id,
                agent: data.agent,
                sessionID: data.sessionID,
              });
            } else if (event.type === "session.step.ended") {
              const entry = pending.get(data.assistantMessageID);
              pending.delete(data.assistantMessageID);
              if (!entry) continue;

              const outputTokens = data.tokens ? Number(data.tokens.output) || 0 : 0;
              const inputTokens = data.tokens ? Number(data.tokens.input) || 0 : 0;
              const durationSec = (event.created - entry.started) / 1000;
              if (durationSec <= 0 || outputTokens <= 0) continue;

              const tps = outputTokens / durationSec;
              const line = `${tps.toFixed(1)} t/s | ${outputTokens} token | ${durationSec.toFixed(1)}s | ${entry.modelID || "?"}`;

              // Best effort: in V2 non c'è client.app.log; console.error finisce nei server logs.
              console.error(`[tokens-per-second] ${line}`);

              try {
                appendFileSync(STATS_FILE, JSON.stringify({
                  ts: new Date().toISOString(),
                  tokens_per_second: Math.round(tps * 10) / 10,
                  output_tokens: outputTokens,
                  input_tokens: inputTokens,
                  duration_seconds: Math.round(durationSec * 10) / 10,
                  modelID: entry.modelID || null,
                  agent: entry.agent || null,
                  sessionID: entry.sessionID || data.sessionID || null,
                }) + "\n", "utf-8");
              } catch (_err) {
                // non bloccare mai
              }
            }
          } catch (_err) {
            // evento malformato: ignora
          }
        }
      } catch (_err) {
        // stream abortito allo unload del plugin
      }
    })();

    return () => controller.abort();
  },
};
