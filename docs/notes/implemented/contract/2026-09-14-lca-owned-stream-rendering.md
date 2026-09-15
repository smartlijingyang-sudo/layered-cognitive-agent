# Agent Note: LCA-owned stream rendering (decouple from LobeHub builtin components)

Status: implemented

## Problem

The LobeHub front-end has been the only consumer of the LCA agent-gateway
WS stream since PR-1 (see 2026-09-07-p1-agent-gateway-bridge.md). The
stream contract (`AgentStreamEvent`, `tool_end.data.result.content`,
`stream_chunk.chunkType` ∈ `text | reasoning | tools_calling`) is
correct — every run `run_8f12bb823f07` … `run_41f8ae40e087` shows the
WS frames carrying the right payloads through Redis Stream and on to
the LobeHub client. The bug is on the *renderer* side: the
`gatewayEventHandler` case statements do not write
`data.result.content` back onto the tool message row in memory, and
the `agent_runtime_end` case has no fallback for the gateway path
that pulls a canonical `uiMessages` snapshot, so the assistant bubble
stops at "Activate Skill:" / "Search pages:" with the actual tool
return text only visible in DOM accordion bodies that nobody clicks.

Vendor-patching the LobeHub handler to fix the gap would be wrong
direction, for three reasons:

1. **Tool result rendering is a hetero/gateway parity problem, not a
   point fix.** `dispatchOnAfterCall` short-circuits when the builtin
   tool has no `onAfterCall` hook (LCA gateway path emits `tools_calling`
   for `lobe-skills` / `activateSkill` whose `SkillsExecutor` /
   `ActivatorExecutor` have none). Fixing it once requires agreeing on
   how hetero vs gateway executors share the result-write surface — a
   cross-track design question that LobeHub owns, not us.

2. **The LobeHub vendor component tree owns state and rendering in
   intertwined ways.** `Tools/Tool/index.tsx` reads `toolMessage.content`
   from the store, which is mutated by `internal_dispatchMessage` /
   `replaceMessages`. Choosing which event writes to which slot,
   and how the `stream_chunk.text` snapshot semantics intersect with
   `result.content` rewrite, requires reading every callsite in
   `gatewayEventHandler.ts` (already 1300 lines) plus the
   `features/Conversation/Messages/AssistantGroup/Tool/*` tree — work
   that belongs in the LobeHub maintainer's handbook, not in our
   patch overlay.

3. **Every LCA surface that wants a richer chat UX (work registration,
   plan tree diff, journal trace toggle, error triage actions) will
   hit the same wall.** The vendor tree is shaped for the native
   AgentGateway consumer; we are feeding it LCA-shaped frames and
   accepting 60–80 % fidelity as a normal outcome. Bumping that
   number further requires LobeHub to grow a "LCA renderer" mode
   that nobody is resourced to maintain.

## Proposal

Render the LCA agent stream in an LCA-owned surface, not the vendored
LobeHub chat. Concretely:

1. **New consumer package.** Add `apps/lca-web` (or repurpose an
   existing app slot) that hosts a chat surface wired exclusively
   against `lca/contracts/transport/agent_stream_event.py`. It
   consumes the WS frames directly, writes to its own message store,
   and renders skill activations, plan nodes, and journal traces as
   first-class components. No LobeHub component imports.

3. **Sink the `uiMessages` snapshot on `agent_runtime_end`.**
   `EventTranslator._spine_kernel_run_stop` should include a
   `uiMessages` envelope (canonical run-final chat snapshot, with
   assistant message `content`, `tools[].result.content`, `reasoning`,
   `pluginState` already filled). The new consumer treats this
   envelope as the SoT; the WS stream just drives the live
   accordion state until `agent_runtime_end.uiMessages` lands.

4. **LobeHub patch becomes a thin compatibility shim** (`fetchAndReplaceMessages(get, ctx)` after `agent_runtime_end` + one-time render of the terminal snapshot via `replaceMessages(uiMessages)`). Future deltas never touch LobeHub UI logic.

## Non-goals

- We do **not** fork LobeHub or carry a multi-megabyte fork long-term.
- We do **not** keep the LobeHub UI as a "second consumer" once the
  LCA-owned surface ships. The vendor tree remains for non-chat
  surfaces (settings, library, agent marketplace) where LCA has no
  content.
- We do **not** back-port hetero-side `dispatchOnAfterCall` parity
  inside the LobeHub vendor tree; that work belongs in the new
  consumer, where the renderer and the stream share an owner.

## Trade-offs

- **Effort:** ~1 quarter for an MVP that handles the three flows
  tested today (search / activateSkill / completion). Not small;
  not open-ended either, because the wire contract is already locked
  by ADR-0194 / ADR-0195 / ADR-0200 and `agent_stream_event.py`.
- **Lost surface:** until the new consumer ships, the LobeHub UI
  keeps its current fidelity. We accept that and do not patch the
  vendor tree any further to chase fidelity. Every fix that crosses
  into LobeHub UI rendering from this point on is a regression in
  this proposal.
- **Reverse direction:** if someone chooses to repair the vendor
  rendering path instead of building the LCA consumer, the wire
  contract stays the same, no rollback needed.

## Delete-when

This note is implemented by the `lca-stream-align` plan (commits
`6a6ef13fc..abdf9976e` on `feat/lca-stream-align`), which took the
**thin compatibility shim** path of the proposal rather than building
`apps/lca-web`. Landed changes:

- `lcaGateway/event_handler.ts` is now a 5-line factory that calls
  `createGatewayEventHandler` with the LCA in-memory reader
  (`createLcaInMemoryMessagesReader`) and `runtimeType: 'lca-gateway'`.
  The LCA transport reuses the native handler instead of carrying
  a parallel codegen-injected implementation.
- `lcaGateway/messageService.ts` + test: the in-memory reader reads
  from `dbMessagesMap` directly (the same surface
  `dbMessageSelectors.getDbMessageById` walks), so any non-skipped
  mid-run refetch reconciles against the live store snapshot.
- `lcaGateway/executeGatewayRun.ts`: removed the dead
  `preserveStreamedContentOnTerminal: true` flag from the
  `createLcaGatewayEventHandler` call site (task 3).
- `lca_runtime_agent_gateway.py`: 582 lines deleted — the four
  `_patch_gateway_event_handler_lca_*` codegen functions that
  injected `mergeToolsCallingChunks`,
  `shouldSkipMidStreamMessageFetch`, and
  `preserveStreamedContentOnTerminal` are gone. Their apply()
  entries are gone. The file count in `meta` drops from 24 to 23.
- `preserveToolResultMessageIds` was changed to merge by id (task 3
  fix), so the LCA wire's per-chunk-single tools accumulate instead
  of being replaced.
- The live `gatewayEventHandler.ts` (gitignored, regenerated by the
  patch engine): the optimistic `tmp_*` shell-insert on `stream_start`
  is deleted; the `hasStreamedContent` skip is restored but gated
  on `runtimeType !== 'lca-gateway'` (the LCA path falls through to
  the refetch, which against the in-memory reader no-ops via
  `isEqual`).
- New regression test (`lcaGateway/lcaGatewayEventHandler.test.ts`)
  covers both branches: with-`uiMessages` and without-`uiMessages`
  on `agent_runtime_end`, multi-run / multi-LLM scenarios.

The `apps/lca-web` track (a fully LCA-owned chat surface) is still
not built. The shim approach above is the implemented state. If a
later effort takes the new-consumer path, this note's Delete-when
reverts to:

> When `apps/lca-web` ships to production and replaces
> `http://10.36.6.252:3010/agent/...` as the LCA chat surface.
>
> Before that, retire the four `dispatchOnAfterCall` /
> `executeGatewayRun` LobeHub-patch shims that exist solely to make
> the vendor tree consume the LCA stream.

Until `apps/lca-web` ships, this note stays as the durable record
of why the LCA gateway path was realigned with the native LobeHub
gateway rather than carrying a parallel codegen patch.

## Alternatives considered

- *Patch the LobeHub handler to write `data.result.content` to the
  tool message row.* Rejected — see Problem §1 and §2. Also leaves
  the hetero/gateway parity debt in place.
- *Switch LobeHub renderer to `replaceMessages` on every
  `agent_runtime_end` and rely on the WS server to push the final
  snapshot.* Viable but only buys the terminal state, not the
  live-render gap. New consumer still needed for the accordion +
  journal trace UX.