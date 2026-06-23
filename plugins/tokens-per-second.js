export const TokensPerSecondPlugin = async ({ client }) => {
  return {
    event: async ({ event }) => {
      if (event.type !== "message.updated") return;

      const info = event.properties?.info;
      if (!info || info.role !== "assistant") return;
      if (!info.time?.completed || !info.tokens?.output) return;

      const durationSec = (info.time.completed - info.time.created) / 1000;
      if (durationSec <= 0) return;

      const tps = info.tokens.output / durationSec;

      await client.app.log({
        body: {
          service: "tokens-per-second",
          level: "info",
          message: `${tps.toFixed(1)} t/s | ${info.tokens.output} token | ${durationSec.toFixed(1)}s | ${info.modelID || "?"}`,
          extra: {
            tokensPerSecond: Math.round(tps * 10) / 10,
            outputTokens: info.tokens.output,
            inputTokens: info.tokens.input,
            durationSeconds: Math.round(durationSec * 10) / 10,
            modelID: info.modelID,
          },
        },
      });
    },
  };
};
