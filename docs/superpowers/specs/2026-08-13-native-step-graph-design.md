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

`@lobechat/conversation-flow` accepts both chain forms. **We write the tool-anchored (old) form only.** Flow still folds it into one `assistantGroup`. We do not write assistant-anchored parents.

```
user
 └─ a1  (reasoning + tools[])     parent = user
      └─ tool T1                  parent = a1, tool_call_id = invocation_id
 └─ a2  (reasoning + tools[])     parent = T1.resultMsgId
      └─ tool T2
 └─ aN  (final text)              parent = last tool of a(N-1), or a(N-1) if that turn had no tool
```

Several tools on one LLM turn: every `role=tool` child parents the **current** assistant. The next assistant parents the **last** of those tools.

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

`LcaRunDriver` is the only unit that talks to the chat store. It holds two maps and a current pointer. It does not accumulate a whole Run inside one `StreamingHandler`.

### Ledger

```
current: { assistantId, handler, speaker } | null
lastResultMsgId: string | null   // last sealed tool child; next same-speaker assistant parents this
tools:   Map<invocation_id, { parentId, call, resultMsgId, pluginState, result? }>
hrefs:   Map<basename, url>   // last-wins; only rewriteArtifactMarkdown reads this
```

No third "files" render ledger. Tool cards show `pluginState.files` / `downloadUrl` from **that invocation**. Markdown rewrite may remap `](./name.pdf)` using `hrefs`. It does not suppress any tool card.

### Event → ledger → store

| Projected kind | Ledger | Store |
|---|---|---|
| `open-turn` same speaker | seal current handler; new `current` | `optimisticCreateMessage({ role: 'assistant', parentId })`. First turn may reuse the send-time placeholder. `parentId` = last tool `resultMsgId`, else current/previous assistant, else user. |
| `open-turn` new speaker | seal current; forget last-tool parent | new assistant, `parentId` = user message (new group) |
| `reasoning` / `text` | append on `current.handler` only | existing Handler callbacks on **this** `assistantId` |
| `reasoning-end` | write `duration_ms` on current row | `dispatch { reasoning: { content, duration } }` |
| `tool-start` | upsert `tools[id]` | write `assistant.tools[]` first, then create `role=tool` if new. First `ToolCallStreaming` with `{}` still opens a card. `arguments` = `pickArgs(plugin_state)` (see below). Never skip a known `WIRE` tool. |
| `sandbox-delta` | append `output` / `stderr` on that tool | `updatePluginState` on `resultMsgId` |
| `tool-invoked` | merge full `plugin_state` + `event.files`; set `lastResultMsgId`; update `hrefs` | `optimisticUpdatePluginState` only. **Do not rewrite** `function.arguments` (started `code` must survive an invoked state that omitted it). complete/fail the `toolCalling` operation |
| `tool-denied` | mark error | `failOperation`; no answer text |
| `run-finished` | optional error on current row | do not treat as socket EOF |
| `live-gap` | log | do not abort |

`StreamingHandler` exists only while `current` is open. Next `LlmCallStarted` constructs a **new** Handler on a **new** `assistantId`. The old Handler is `handleFinish`'d and dropped. Its tools stay on the old row.

### Arguments vs pluginState

These are two fields. `ARG_OMIT` failed because it treated **inputs** (`code`, `content`, `path`) as noise.

**Rule (mechanical, in `LcaRunDriver.ts` as `RESULT_KEYS`):** a key is a result if it is in this frozen set. Everything else in `plugin_state` is an argument.

```
RESULT_KEYS = {
  success, executionEnv, stdout, stderr, output,
  exitCode, exit_code, error, errorDetail,
  files, downloadUrl, filename, mimeType, size, sizeBytes,
  hasResources, source, title, resources,
  resultNumbers, results, previewable, attachmentId, url
}
```

- `pickArgs(state)` = `{ k: v in state | k ∉ RESULT_KEYS }`. Empty object is allowed.
- `tool-start` / streaming upsert writes `function.arguments = JSON.stringify(pickArgs(state))`. Create the card even when that object is `{}` (first `ToolCallStreaming` on the sample).
- `tool-invoked` writes **the whole** invoked `plugin_state` (plus `event.files` merged into `pluginState.files`) to the tool row. Do not run `RESULT_KEYS` on the invoked state — native `ExecuteCode` / `ExportFile` read result fields from `pluginState`.
- Do not put `RESULT_KEYS` in `wire.py`. `WIRE` stays name → (identifier, apiName). The result set is UI vocabulary, not a gateway concern.
- `content` stays an argument when it appears on start (`write_file`). On invoke, `activate_skill` may put SKILL.md in `pluginState.content`; that is result data and stays in pluginState because we dump the full invoked state.

Empty `code` is still a card. The highlighter shows empty. Denying empty execute on the backend is out of scope.

### Files

On `ToolInvoked`, copy `event.files` into **that tool's** `pluginState.files`. `export_file` keeps `downloadUrl` + `filename` from invoked `plugin_state`. Do not call `uploadWithProgress` / `addFilesToMessage`. Do not write `assistant.fileList` (group `FileListViewer` wants LobeHub file-store ids; we are not in that universe).

`hrefs` is only for `rewriteArtifactMarkdown`: `](./basename)` → `](/files/...)`. Last url for a basename wins. When both `plugin_state.downloadUrl` and `event.files[].url` exist (the sample export has two ids), `hrefs` and the export card download button use `downloadUrl`; `pluginState.files` still lists `event.files`. It does not hide an execute card. Do not invent `computer://` links. Existing `computer://` in model text stays dead text; the card is the download.

Keep `persistMissed` / `sealRow` retry. The placeholder-vs-store race is still real.

## Deleted machinery

Remove from `deploy/lobehub/patches/runtime/` and from `tests/test_journal_native_loop.py`:

- `if (assistantId && sameSpeaker) { handler = makeHandler(assistantId); return }`
- `ARG_OMIT`, `hasRenderableArgs`, silent `return` on tool-start
- `attachNativeFiles`, `useFileStore().uploadWithProgress`, `addFilesToMessage`
- `latestDeliverables` / `toFileList` / `toImageList` wired into `persistRow` (group fileList path)
- `test_same_speaker_stays_on_one_assistant`
- `test_user_file_list_is_latest_deliverable`
- any test that requires `hasRenderableArgs`, `ARG_OMIT`, `addFilesToMessage`, or `uploadWithProgress` to exist (`test_artifacts_rewrite_relative_markdown` keeps only `rewriteArtifactMarkdown`)

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
| Reconnect | Same `runLcaJournal` `while` loop only. On socket drop, open `/live` with `Last-Event-ID` = last seen seq (exclusive). **Do not rebuild** the ledger from history and do not scan the store for old ids. In-memory `current` / `tools` stay. Tool upsert is by `invocation_id`. A replayed `LlmCallStarted` after that seq is a new turn — so the live tail must not re-send already-applied frames. Page reload is out of scope (new Driver instance, no resume). |
| Team speaker change mid-run | seal; new assistant parented to the **user** message so flow opens a new group |
| Two files, same basename, different url | each tool card shows the files that invocation produced; `hrefs` keeps the last url for markdown only |

## Tests

Replace string-presence tests that lock the old unit with tests that lock the graph.

**Python contract (`tests/test_journal_native_loop.py`) is the automated lock.** Patch TS is copied into `lobehub-ui/`; do not add a second vitest stack in this change.

- Keep: no `JournalTransport`, no `GeneralChatAgent`, hook is `streamingExecutor`, parse/project split, Finished ≠ EOF, cancel auth.
- Same speaker, second `LlmCallStarted`: source contains a new `optimisticCreateMessage` path, not `handler = makeHandler(assistantId); return`. `parentId` is `lastResultMsgId` (tool-anchored).
- `pickArgs` / `RESULT_KEYS` exist; `code` is not in `RESULT_KEYS`; `executionEnv` / `output` / `files` / `downloadUrl` are.
- `arguments` include `code` for execute_code (string check on `pickArgs` usage + RESULT_KEYS).
- No `uploadWithProgress`, `addFilesToMessage`, `attachNativeFiles`.
- `rewriteArtifactMarkdown` remains; `latestDeliverables(turnImages)` / `toFileList` in the Driver do not.

Graph shape (7 assistants, tool-anchored parents) is verified by replaying the sample in the UI after `patch_lobehub.py apply --reset`, not by a new test runner.

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

A reviewer can delete `LcaRunDriver.ts` internals and still explain the system: Journal is the book; the Driver upserts a two-map ledger; LobeHub store APIs write the native graph; builtin renders do the rest.

If a future bug is "thinking merged" or "card missing", the first question is "did we write a new assistant / did we put `code` in arguments" — not "which omit list ate it".
