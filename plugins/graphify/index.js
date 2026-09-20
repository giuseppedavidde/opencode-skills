// graphify OpenCode plugin (API V2)
// Injects a knowledge graph reminder before shell tool calls when the graph exists.
// V2: Plugin.define è un helper identità; esportiamo direttamente { id, setup }.
import { existsSync } from "fs";
import { join } from "path";

export default {
  id: "graphify",
  async setup(ctx) {
    const directory = ctx.location && ctx.location.directory;
    let reminded = false;

    await ctx.tool.hook("execute.before", (event) => {
      if (reminded) return;
      if (!directory) return;
      if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;

      if ((event.tool === "shell" || event.tool === "bash")
          && event.input && typeof event.input === "object"
          && typeof event.input.command === "string") {
        event.input = {
          ...event.input,
          command:
            'echo "[graphify] knowledge graph at graphify-out/. For focused questions, run `graphify query \\"<question>\\"` (scoped subgraph, usually much smaller than GRAPH_REPORT.md) instead of grepping raw files. Read GRAPH_REPORT.md only for broad architecture context." && ' +
            event.input.command,
        };
        reminded = true;
      }
    });
  },
};
