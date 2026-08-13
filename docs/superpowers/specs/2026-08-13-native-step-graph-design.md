# Native Step Graph Projector

**Status:** Draft  
**Date:** 2026-08-13  
**Sample:** `traces/runs/run_8988077c043e.jsonl`（快乐通宝会员标签模型定义 3.0.xlsx → PDF）

## Problem

Journal already records a step track: one `LlmCallStarted` per model call, one `ToolStarted` per invocation. LobeHub already renders a step track: one `assistant` per LLM turn, one `role=tool` child per invocation, `conversation-flow` folds the chain into a single `assistantGroup`.

The current Driver maps **speaker → one assistant row**. Solo always has one speaker, so seven LLM turns collapse into one `reasoning` field and `ProcessFold` shows「共运行了 1 步」. `ARG_OMIT` then strips `code` from `execute_code`, so `hasRenderableArgs` drops the cards. Downloads go through a second file universe (`uploadWithProgress`) instead of the builtin `ExecuteCode` / `ExportFile` renders.

This is not a missing if. The identity unit is wrong. Specs disagree (`docs/run-live.md` says new assistant per `LlmCallStarted`; `CUSTOMIZATIONS.md` and `test_same_speaker_stays_on_one_assistant` lock one assistant per speaker). Tests weld the wrong unit.

## Goal

Project Journal onto the **native LobeHub message graph**. Do not invent UI. Do not patch `StreamingHandler`, `Reasoning.tsx`, or `GeneralChatAgent`.

After this change, `run_8988077c043e` must look like a native Codex / Claude Code turn: 7 Thinking blocks interleaved with tool cards,「共运行了 7 步」, code visible, PDF downloadable from the native `exportFile` / `executeCode` card.

## Non-goals

- Do not implement LCA as `executeHeterogeneousAgent` (desktop CLI pipeline; we do not own it).
- Do not change Journal event names or SSE encoding.
- Do not fix solo `run_id` minting or sandbox directory harvest in this spec (separate mechanisms; they did not cause the merge).
- Do not add a custom Thinking accordion or a custom file-card component.
- Do not keep `ARG_OMIT`, `hasRenderableArgs`, `attachNativeFiles`, or same-speaker assistant reuse under a new name.

## Native contract (do not reimplement)

`@lobechat/conversation-flow` accepts both chain forms and emits one `assistantGroup`:

```
user
 └─ a1  (reasoning + tools[])     parent = user
      └─ tool T1                  parent = a1, tool_call_id = invocation_id
 └─ a2  (reasoning + tools[])     parent = T1  (old) or a1 (new)
      └─ tool T2
 └─ aN  (final text)              no tools
```

`ProcessFold` step count = distinct assistant block ids in the group (`countAssistantLlmCalls`).  
Each assistant has its own `reasoning`. Later turns must not write earlier rows.

Builtin renders already paint our tools:

| LCA tool | WIRE | Reads | Shows |
|---|---|---|---|
| `execute_code` | `lobe-cloud-sandbox` / `executeCode` | `args.code`, `args.language`; `pluginState.output`, `stderr`, `files[]` | highlighter + stdout + file download strip |
| `export_file` | `lobe-cloud-sandbox` / `exportFile` | `args.path`; `pluginState.success`, `filename`, `downloadUrl` | native download button |

`FileListViewer` on the group wants LobeHub file-store ids (`openFilePreview({ fileId })`). Sandbox artifacts are `/files/file_*`. Do not re-upload to fake that. Downloads live on the tool card.

## Units

```
lcaJournal.ts        parse SSE; Journal frame → Projected  (keep)
lcaWire.ts           generated from gateway.runs.wire      (keep)
lcaFinishChat.ts     LobeHub chrome after the run          (keep)
lcaChatRow.ts        placeholder vs persisted row          (keep, slim)
LcaRunDriver.ts      ledger + sync to store                (rewrite)
lcaArtifacts.ts      markdown href rewrite only            (slim)
```

`LcaRunDriver` is the only unit that talks to the chat store. It holds three maps and a current pointer. It does not accumulate a whole Run inside one `StreamingHandler`.

### Ledger

```
current: { assistantId, handler, speaker } | null
tools:   Map<invocation_id, { parentId, call, resultMsgId, pluginState, result? }>
files:   Map<basename, ArtifactFile>   // last harvest wins; not a render path
```

### Event → ledger → store

| Projected kind | Ledger | Store |
|---|---|---|
| `open-turn` same speaker | seal current handler; new `current` | `optimisticCreateMessage({ role: 'assistant', parentId })`. First turn may reuse the send-time placeholder. `parentId` = last tool `resultMsgId` or user message. |
| `open-turn` new speaker | seal current; reset last-tool parent | new assistant, `parentId` = user message (new group) |
| `reasoning` / `text` | append on `current.handler` only | existing Handler callbacks on **this** `assistantId` |
| `reasoning-end` | write `duration_ms` on current row | `dispatch { reasoning: { content, duration } }` |
| `tool-start` | upsert `tools[id]` | write `assistant.tools[]` first, then create `role=tool` if new. `arguments` = tool inputs (`code`, `path`, `language`, `description`, …). Never drop a known `WIRE` tool because args look empty. |
| `sandbox-delta` | append `output` / `stderr` on that tool | `updatePluginState` on `resultMsgId` |
| `tool-invoked` | merge `plugin_state` + `files`; upsert `files` map | `optimisticUpdatePluginState`; complete/fail the `toolCalling` operation |
| `tool-denied` | mark error | `failOperation`; no answer text |
| `run-finished` | optional error on current row | do not treat as socket EOF |
| `live-gap` | log | do not abort |

`StreamingHandler` exists only while `current` is open. Next `LlmCallStarted` constructs a **new** Handler on a **new** `assistantId`. The old Handler is `handleFinish`'d and dropped. Its tools stay on the old row.

### Arguments vs pluginState

These are two fields. Stop mixing them.

- **arguments** (JSON on `function.arguments` / `plugin.arguments`): what the model asked for. For `execute_code`: `code`, `language`, `description`. For `export_file`: `path`.
- **pluginState**: execution result. For `execute_code`: `output`, `stderr`, `success`, `files`. For `export_file`: `success`, `filename`, `downloadUrl`, `size`, `mimeType`.

`ToolStarted.plugin_state` today carries both. The projector splits: keys that are inputs go to `arguments`; the rest wait for `ToolInvoked` (or stream into `pluginState` via `SandboxOutputDelta`). A split table lives next to `WIRE`, not as a deny-list of "render noise".

Empty `code` is still a card (`arguments: { language }` or `{ code: '' }`). The native highlighter shows empty. The backend may later deny empty execute; that is not this spec.

### Files

On `ToolInvoked`, copy `event.files` into that tool's `pluginState.files`. `export_file` also needs `downloadUrl` + `filename` from `plugin_state` (already present on the sample). Dedup by basename in the `files` map so a later `export_file` of the same PDF does not require a second execute card. Do not call `uploadWithProgress` / `addFilesToMessage`.

`rewriteArtifactMarkdown` may still rewrite `](./name.pdf)` to `](/files/...)` in answer text. It must not invent `computer://` links. Existing `computer://` in model text can stay as dead text; the card is the download.

## Deleted machinery

Remove from `deploy/lobehub/patches/runtime/` and from `tests/test_journal_native_loop.py`:

- `if (assistantId && sameSpeaker) { handler = makeHandler(assistantId); return }`
- `ARG_OMIT`, `hasRenderableArgs`, silent `return` on tool-start
- `attachNativeFiles`, `useFileStore().uploadWithProgress`, `addFilesToMessage`
- `test_same_speaker_stays_on_one_assistant`
- any test that requires `hasRenderableArgs` / `ARG_OMIT` to exist

Update `docs/run-live.md` and `deploy/lobehub/CUSTOMIZATIONS.md` so both say: **one `LlmCallStarted` = one assistant row**. Same speaker continues the chain (parent = last tool). Different speaker starts a new chain (parent = user).

## Error and edge cases

| Case | Behavior |
|---|---|
| Unknown tool name | `console.warn`; do not create a card; do not drop the stream |
| `ToolCallStreaming` before `ToolStarted` | same id upserts one card; arguments grow as deltas arrive |
| `ToolInvoked` with no prior start | ignore (warn); do not invent a parent |
| Cancel / abort | `POST /runs/{id}/cancel`; seal current row; leave already-written turns in place |
| `waiting_input` | mark metadata on current assistant; do not auto-answer |
| `LiveGap` | warn; continue |
| `*Finished` then late `StepTextDelta` | still current (or last) assistant; tail close seals |
| Reconnect | `Last-Event-ID`; ledger rebuilds from frames after that seq. Already-created message ids stay. Upsert by `invocation_id` / current turn is idempotent |
| Team speaker change mid-run | seal; new assistant parented to the **user** message so flow opens a new group |
| Two files, same basename, different url | `files` map keeps the last; each tool card still shows the files that invocation produced |

## Tests

Replace string-presence tests that lock the old unit with tests that lock the graph.

**Driver (TypeScript, vitest next to the patch or a Node harness that imports the projector functions):**

1. Replay the collapsed event sequence of `run_8988077c043e` (7× `LlmCallStarted`, 6× tool, final text). Assert create-message calls: 7 assistant (counting first reuse), 6 tool; each tool `parentId` equals its owning assistant; next assistant `parentId` equals previous tool (or previous assistant — pick one form and test it).
2. Second `ReasoningDelta` after a new `LlmCallStarted` updates only the new assistant id.
3. `execute_code` ToolStarted with `{ code, description, language, executionEnv }` produces `arguments` containing `code` and a tool row. `executionEnv` is not required in arguments.
4. `export_file` ToolInvoked writes `pluginState.downloadUrl` and `filename`.
5. No `uploadWithProgress` / `addFilesToMessage` in the module.

**Python contract (`tests/test_journal_native_loop.py`):**

- Keep: no `JournalTransport`, no `GeneralChatAgent`, hook is `streamingExecutor`, parse/project split, Finished ≠ EOF, cancel auth.
- Replace same-speaker / ARG_OMIT assertions with: `openTurn` always creates or reuses **once**, then subsequent same-speaker `LlmCallStarted` create a new row; `arguments` include `code` for execute_code.

**Manual / replay against the sample jsonl:** 7 Thinking, 6 cards, one PDF download from the export card, step count 7.

## Files to touch

```
deploy/lobehub/patches/runtime/LcaRunDriver.ts      rewrite
deploy/lobehub/patches/runtime/lcaArtifacts.ts      drop upload helpers if unused
deploy/lobehub/patches/runtime/lcaChatRow.ts        only if persistMissed still needed
docs/run-live.md                                    mapping table + identity unit
deploy/lobehub/CUSTOMIZATIONS.md                    one LLM = one assistant
tests/test_journal_native_loop.py                   new invariants
```

After code change: `python3 deploy/lobehub/patch_lobehub.py apply --reset` (never edit `lobehub-ui/` copies by hand).

## Success

A reviewer can delete `LcaRunDriver.ts` internals and still explain the system: Journal is the book; the Driver upserts a three-map ledger; LobeHub store APIs write the native graph; builtin renders do the rest.

If a future bug is "thinking merged" or "card missing", the first question is "did we write a new assistant / did we put `code` in arguments" — not "which omit list ate it".
