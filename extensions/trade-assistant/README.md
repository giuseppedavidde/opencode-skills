# Trade Assistant

VS Code extension that exposes the capabilities of the `trade` agent and hosts a chat panel.
The extension does not hardcode capability lists.
At activation it reads live files and derives the surface from them.

## Sources of truth

1. `agents/trade.md` frontmatter and body.
   The extension reads the agent name, model, permissions, MCP tools and workflow headings.
2. `~/.copilot/mcp-config.json`.
   The extension reads the `mcpServers.trading` command, arguments and environment.
3. `skills/*/SKILL.md` frontmatter.
   The extension builds the skill catalogue from `name` and `description`.

## Repository root detection

The extension resolves the repository in this order:

1. The `tradeAssistant.repoRoot` setting.
2. Every open workspace folder and up to four parent directories, checking for `agents/trade.md` and `skills/`.
3. `<home>/Progetti/Github/opencode-skills`.
4. The extension install folder.

The check requires both `agents/trade.md` and `skills/`.
When no candidate matches, a warning offers `Locate repository` and writes the chosen folder to the global setting.

## Chat panel

The **Chat** view lives in the `tradeAssistant` activity bar container.
It is a webview with a message list, a composer and a session selector.

1. The extension sends each turn to one chat provider. See [Chat providers](#chat-providers).
2. The model receives the live `agents/trade.md` body, the skill catalogue, the trading MCP tools and four local file tools.
3. A tool call runs on the trading MCP server over stdio JSON-RPC, or on the local file tools.
4. A long tool result is compressed: each line is cut at 400 characters and the total at 8000 characters, with the head and the tail kept.
5. When the turn reaches `tradeAssistant.chat.maxToolIterations`, the extension sends one last request with no tools, so the model must answer with the results it already has.
6. The extension writes each user message, assistant message, tool call and tool result to a JSONL transcript.
7. A reload restores the exact conversation.

The panel never places orders.
It refuses a tool whose name matches `place`, `order`, `trade_execute`, `buy`, `sell`, `close_position` or `transfer`.

## Chat providers

The setting `tradeAssistant.chat.provider` selects the backend.

| Value | Behaviour |
| --- | --- |
| `auto` | Uses OpenCode Go when a key exists in `~/.local/share/opencode/auth.json`. Falls back to GitHub Copilot models. |
| `opencode-go` | Always uses OpenCode Go models (see the protocol rule below). |
| `copilot` | Always uses GitHub Copilot language models. |

### OpenCode Go

`opencode-go` speaks the OpenAI chat-completions protocol.

1. Base URL: `https://opencode.ai/zen/go/v1`.
2. Endpoints: `POST /chat/completions` and `GET /models`.
3. The extension reads the key at runtime from `~/.local/share/opencode/auth.json`, at the JSON path `["opencode-go"]["key"]`.
   The key starts with `oc_sk_`.
4. The extension never logs the key, never writes it to disk and never sends it to the webview.
5. Every request sends these mandatory headers. The API answers HTTP 400 `MissingSessionID` without them.

| Header | Value |
| --- | --- |
| `Authorization` | `Bearer <key>` |
| `content-type` | `application/json` |
| `user-agent` | `trade-assistant/0.3.0` |
| `x-opencode-session` | The stable chat session id. The value does not change across turns of one session. |

The model id is exactly the id from `GET /models`, for example `deepseek-v4.1-flash`.
The extension strips the `opencode-go/` prefix and the `#effort` suffix from `agents/trade.md` and from `tradeAssistant.chat.model`.

The direct client speaks only the chat-completions protocol. `GET /models` lists the protocols of each model in `api`:

1. A model with `chat-completions` uses the direct client.
2. A model without it (for example `gemini-4-argon`, which needs `generate-content`) uses the VS Code language model API with the vendor `tradeAssistant.chat.lmVendor` (default `opencodego`).
3. Install the extension `OnesoftQwQ.opencode-go-copilot-provider` for step 2. Without it, the chat uses a GitHub Copilot model and the log says so.
Responses stream over SSE.
The extension joins text deltas, joins tool-call argument fragments by index and counts the reported tokens.

When the key is missing, the panel shows:

`OpenCode Go key not found in ~/.local/share/opencode/auth.json. Run "opencode auth login" or set tradeAssistant.chat.provider to copilot.`

Run `Trade Assistant: Show Provider Status` to print the provider, the model, the key presence and the allowed roots.
The command never prints the key.

## File tools

Four local tools let the model read files on this PC when the user gives a path.

| Tool | Input | Output |
| --- | --- | --- |
| `read_file` | `path`, optional `startLine`, `endLine` | Numbered lines. Caps: 400 lines and 40 KB. |
| `list_dir` | `path` | Entry type and size. Cap: 400 entries. |
| `find_files` | `pattern`, optional `path` | Glob match with `*` and `**`. Cap: 200 files. |
| `search_text` | `pattern`, optional `path`, `glob` | `file:line` matches. Cap: 100 matches. |

1. A path may start with `~`. A relative path resolves against the first allowed root that exists.
2. Every tool refuses a path outside the allowed roots. The refusal names the setting `tradeAssistant.fileAccess.roots`.
3. Every tool refuses these paths, even inside an allowed root:
   `.ssh/id_*`, `**/auth.json`, `**/.netrc`, `**/*.pem`, `**/credentials*`, `**/.aws/credentials`.
4. `read_file` refuses binary content.
5. `find_files` and `search_text` skip `node_modules` and `.git`.
6. Symlinks resolve to the real path before the root check.

The default allowed roots are the workspace folders, the resolved repository root and the home directory.
Set `tradeAssistant.fileAccess.roots` to replace this list.

### Transcript storage

One JSONL file per session under `<globalStorage>/chat`.
No transcript leaves the local machine.
`Export` opens the current transcript as an untitled markdown document.

### Copilot model selection

The Copilot provider asks `vscode.lm.selectChatModels({ vendor: 'copilot' })` first.
It falls back to `selectChatModels({})`.
If no model is available, the panel shows an actionable message.

## Commands

| Command | Action |
| --- | --- |
| `Trade Assistant: New Chat Session` | Starts a new transcript and focuses the chat view. |
| `Trade Assistant: Export Transcript` | Opens the current transcript as untitled markdown. |
| `Trade Assistant: Open Trade Agent` | Opens `agents/trade.md` in a preview editor. |
| `Trade Assistant: List Skills` | Opens a QuickPick of parsed skills and opens the chosen `SKILL.md`. |
| `Trade Assistant: Run Trading Tool` | Asks for a ticker and opens a terminal that runs the configured MCP command with `--help`. |
| `Trade Assistant: Show Skill Mismatch` | Writes the drift between repo `skills/` and `~/.copilot/skills` to the output channel. |
| `Trade Assistant: Show Provider Status` | Writes the provider, the model, the key presence and the allowed file roots to the output channel. |
| `Trade Assistant: Allow Folder for File Access` | Adds one or more folders to `tradeAssistant.fileAccess.roots`. |

No command places orders or deletes files.

## Tree view

The **Trade Assistant** activity bar view has two groups.

1. **MCP Tools**: one item for each allowed MCP tool in `agents/trade.md`.
2. **Skills**: one item for each parsed skill.

## Sync behaviour

A `FileSystemWatcher` watches four targets.

1. `agents/*.md`
2. `skills/**/SKILL.md`
3. the configured `mcp-config.json` file
4. `mcp/src/**/*.py`

Every event triggers a debounced re-parse. The debounce delay is at least 500 ms.
The extension compares the new capability signature with the previous one.
An identical parse does not change the tree or the command surface.
No window reload is necessary.

A Python change under `mcp/src` marks the MCP client stale.
The client restarts before the next chat turn, so the chat runs the modified source.
A restart happens only when a source file is newer than the running process.
The client also restarts when the capability signature changes.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `tradeAssistant.chat.provider` | `auto` | Model backend: `auto`, `opencode-go` or `copilot`. |
| `tradeAssistant.chat.model` | `''` | OpenCode Go model id. Empty value uses the `model` field of `agents/trade.md`. |
| `tradeAssistant.fileAccess.roots` | `[]` | Allowed roots for the file tools. Empty value uses workspace folders, repository root and home. |
| `tradeAssistant.repoRoot` | auto-detect | Absolute path to the opencode-skills repository. Empty value runs the detection chain. |
| `tradeAssistant.mcpConfigPath` | `~/.copilot/mcp-config.json` | Absolute path to the MCP config. |
| `tradeAssistant.tradingServerName` | `trading` | Server name in `mcpServers`. |
| `tradeAssistant.debounceMs` | `600` | Debounce delay. Minimum value is 500. |
| `tradeAssistant.chat.modelFamily` | `''` | Copilot model family or id. Empty value auto-selects. |
| `tradeAssistant.chat.maxToolIterations` | `14` | Maximum tool rounds per turn. Range 1 to 40. After the limit the model must answer without tools. |
| `tradeAssistant.chat.temperature` | `0.2` | Sampling temperature. Range 0 to 2. |

## Development

1. Run `npm install`.
2. Run `npm run compile`.
3. Run `npm test` for headless unit tests.
4. Press `F5` in VS Code to start an Extension Development Host.

## Verification

1. Run `npx tsc --noEmit`.
2. Run `npm test`.
3. Run `npx @vscode/vsce ls`.

The unit tests cover JSON-RPC line parsing, tool schema mapping, transcript round-trip, staleness detection and unsafe tool blocking.
They also cover auth key parsing, model id normalization, SSE line parsing with split chunks, tool-call delta merging with fragmented arguments, path expansion, the `isWithin` prefix guard, blocked-path refusal and the `read_file` line cap.
No test uses the network.
