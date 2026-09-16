# Resume + ask-user-question WS flow — 审计与缺口清单

> **状态**：plans（只读审计 + 缺口登记，非 note lifecycle）
> **日期**：2026-09-16

## Problem

The user reports the LCA front-end ↔ back-end "resume / ask user question"
(HIL: human-in-the-loop approval) interaction has gaps. The lobehub
native flow uses `agent_intervention_request` /
`agent_intervention_response` events (see
[lca/contracts/transport/agent_stream_event.py:194-227](../../../lca/contracts/transport/agent_stream_event.py))
plus a `tool_execute` event for client-side tool execution
(lines 188-193). The task is to audit whether LCA implements this
round-trip end-to-end, list concrete gaps with file:line, and order
recommended fixes.

This note captures the investigation; the user explicitly asked for a
written report before any code change. The `investigating/` directory
is intentionally outside the lifecycle four-state set (the formal
Agent Note lifecycle is `proposed | implemented | rejected`); see
[docs/notes/README.md](../README.md) §2.1.

## What exists (LCA pieces that DO support the flow)

### Back-end wire contract
- **Wire union types** mirror lobehub — all 17 `AgentStreamEvent`
  members including `ToolExecute`, `AgentInterventionRequest`,
  `AgentInterventionResponse` are present in the Pydantic discriminated
  union [lca/contracts/transport/agent_stream_event.py:307-309].
- **Client message union** — `AuthMessage`, `ResumeMessage`,
  `HeartbeatMessage`, `InterruptMessage`, `ToolResultMessage` all
  byte-compat with lobehub's `AgentStreamClient`
  [lca/contracts/transport/gateway_messages.py:63-68, 117].
- **`ResumeMessage.wantStatus`** field present in the schema and
  flowed through [lca/contracts/transport/gateway_messages.py:43-46].

### Back-end WS handler
- **WS handshake** — auth → optional resume → live loop
  [lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py:109-191].
- **Resume replay** — `lastEventId`-bounded XREAD replay, history
  reversed to delivery order, every event emitted as `agent_event`
  envelope [agent_gateway.py:159-173].
- **`want_status` → `resume_complete { status }`** — terminal
  history → `resume_complete` + `session_complete` + close; live →
  `resume_complete` then continue live loop
  [agent_gateway.py:174-180].
- **Live loop race** — XREAD BLOCK 500 vs `ws.receive_text` with
  FIRST_COMPLETED; queued frames drain ahead of control frames
  [agent_gateway.py:202-302].
- **Control frame handling** — `heartbeat`, `interrupt`, `tool_result`
  [agent_gateway.py:308-339].
- **`run_port.resume_approval`** — the actual resume dispatch
  (approval lifecycle, idempotency, durable-resume validation,
  re-bound session) is implemented in the RunPort adapter
  [lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py:138-273].
- **HIL journal entry** — `_commit_approval_requested` records the
  HIL pause via the `approval_requested_receipt` lifecycle fact before
  any world-effect; preserves the approval-lifecycle semantics
  [lca/cognition/body/executor/safe_executor.py:296-301, 217-222].

### Front-end client (LCA-owned transport)
- **LCA-owned WS client** —
  `LcaAgentStreamClient` with the lobehub-parity surface (`connect`,
  `disconnect`, `sendInterrupt`, `sendToolResult`, `updateToken`,
  `on`, `off`) [lobehub-ui/src/store/chat/agents/transports/lcaGateway/LcaAgentStreamClient.ts].
- **Auth + resume-after-auth** — `auth_success` triggers
  `{type:'resume', lastEventId, wantStatus: true}` immediately
  [LcaAgentStreamClient.ts:319-329].
- **`sendToolResult`** — present and wires a `ClientToolResultMessage`
  [LcaAgentStreamClient.ts:71-79, 225-227].
- **Heartbeat** — 30s interval, 3 missed → reconnect with
  `lastEventId` resume [LcaAgentStreamClient.ts:387-403].
- **`isOwnTerminal` guard** — sibling-op terminals do not tear down
  this socket [LcaAgentStreamClient.ts:355-368].

### Front-end handler (reused from native gateway path)
- **`tool_execute` → `internal_executeClientTool`** — wired in the
  shared gateway handler
  [lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts:985-1001].
- **`step_start {phase:'human_approval'}` → desktop notification +
  `waitingForHuman` topic status**
  [gatewayEventHandler.ts:962-984].
- **HIL SSE path (LCA-specific)** — the lobehub intervention card
  → LCA HTTP `POST /lca-api/runs/{runId}/answer` patch closes the
  askUserQuestion round-trip via plain HTTP, NOT the WS
  `tool_result` frame
  [deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py:323-336].
- **`clientToolExecution` action** — full local-tool execution with
  `executionTimeoutMs` race, MCP fallback, idempotent `sendToolResult`
  on the resolved WS
  [lobehub-ui/src/store/chat/slices/agentRun/actions/transports/client/clientToolExecution.ts:69-350].
- **`resume_approval` / `resume_tool_result` bodies** in the LCA
  `POST /lca-api/runs` execute path — the entry point for resuming an
  HIL-paused run from a fresh client
  [lobehub-ui/src/store/chat/agents/transports/lcaGateway/execute.ts:25-74].

### Resume replay tests
- **L2-2 resume replays history and emits `resume_complete`** — covers
  the happy path of the WS handler resume
  [tests/integration/p1/test_lca_p1_node_02_resume.py:56-95].
- **L2-5 `tool_result` → `RunPort.resume_approval` forwarding** — covers
  the WS `tool_result` → port dispatch (this is the path that the
  askUserQuestion HTTP route is supposed to parallel)
  [tests/integration/p1/test_lca_p1_node_05_tool_result.py].
- **L3-5 HIL cross-tab idempotency** (skipped without
  `LCA_E2E_KERNEL=1`)
  [tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py].
- **Wire parity smoke** — asserts every Python `AgentStreamEvent`
  member is defined; does NOT assert back-end actually produces them
  [tests/e2e/p1/test_lca_p1_01_user_books_flight.py:37-90].

### Existing parity gap tracker
- **[docs/notes/proposed/contract/2026-09-07-p1-facade-ws-token-todo.md](../proposed/contract/2026-09-07-p1-facade-ws-token-todo.md)**
  — tracks the deferred `create_run` `ws_token` +
  `lca_running_operations` writer; orthogonal to this audit (it's
  about WS auth bootstrapping, not the HIL flow).

## What is missing (gaps with file:line + reason)

### Gap A — `ToolExecute` is defined but never produced by LCA

The Pydantic class is wired into the union, but no event translator
exists in `EventTranslator._HANDLERS` or `_SPINE_HANDLERS`, and no
producer in the runtime calls it. The spine has
`body.tool.execute.start` / `body.tool.execute.end` EPs
[lca/infrastructure/session/emit/cognitive_emit.py:595-625,
lca/loop/commit/tool_journal.py:133-180], but they translate to
`tool_start` / `tool_end`, NOT `tool_execute`
[lca/application/runtime/coordinator/event_translator.py:349-401].

**Effect**: the front-end `case 'tool_execute'` handler
[gatewayEventHandler.ts:985-1001] is dead code for the LCA
back-end — it can only fire against an upstream lobehub gateway,
which the LCA transport does not call.

### Gap B — `AgentInterventionRequest` translator exists but no producer

`EventTranslator._HANDLERS` registers the type
["AgentInterventionRequest" →
`_agent_intervention_request` at
event_translator.py:266-278, 433], but no StampedEvent ever fires
`kind="AgentInterventionRequest"`. The HIL pause emits
`approval.persisted.v1` + `waiting_input` checkpoint via the durable
journal ([lca/infrastructure/session/emit/lifecycle_emit.py:145-168])
— not through the WS event stream.

**Effect**: front-end's `case 'agent_intervention_request'` handler
does not exist in `gatewayEventHandler.ts` (only the hetero executor
has it [lobehub-ui/src/store/chat/slices/agentRun/actions/transports/hetero/heterogeneousAgentExecutor.ts:2009-2023]).
LCA back-end uses the HTTP `/lca-api/runs/{runId}/answer` route as
the only intervention round-trip, bridged by a lobehub-runtime patch
[deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py:323-336].

### Gap C — `AgentInterventionResponse` is defined but unused

Same shape problem as Gap B: Pydantic class present in the union
[agent_stream_event.py:221-228], but no translator, no producer, no
front-end consumer. The hetero executor handles it for CC/Codex
flows [heterogeneousAgentExecutor.ts:2033-2073]; the LCA gateway
handler has no case for it.

### Gap D — `ToolResultMessage.idempotencyKey` is not in the wire schema

`agent_gateway.py:334` reads `msg.get("idempotencyKey", "")` from the
client `tool_result` frame, but:

- `ToolResultMessage` (Python) has no `idempotencyKey` field
  [lca/contracts/transport/gateway_messages.py:56-62].
- The lobehub TS `ToolResultMessage` also has no `idempotencyKey`
  field [lobehub-ui/packages/agent-gateway-client/src/types.ts:286-307].
- The front-end `LcaAgentStreamClient.sendToolResult` only sends
  `content`, `error`, `state`, `success`, `toolCallId` (via the TS
  shape) [LcaAgentStreamClient.ts:71-79, 225-227].
- Tests assert the `idempotencyKey` field IS sent
  [tests/integration/p1/test_lca_p1_node_05_tool_result.py:69,
  tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py:109-130], so the
  tests diverge from real wire shape.

**Effect**: in production traffic, `idempotencyKey` is always `""` —
so the back-end idempotency check
[commands.py:169-176] never dedupes real WS `tool_result` traffic.
The schema gap either needs (1) adding `idempotencyKey` to both
shapes + the client send, or (2) relaxing the back-end to use
`{toolCallId, payload}` as the idempotency key. Without one or the
other, cross-tab resume replay is not actually idempotent on the WS
path.

### Gap E — Front-end handler has no `agent_intervention_request` / `agent_intervention_response` cases

Even if the back-end eventually emits them, the LCA gateway handler
[gatewayEventHandler.ts] — which is what the LCA transport wires —
has no `case` for either. The hetero executor handles them, but the
LCA runtime does NOT route through the hetero executor.

**Effect**: the `lca-gateway` runtime type
[gatewayEventHandler.ts:454-461] would silently drop the event
(no-op default case at the end of the switch).

### Gap F — Dead-code risk in front-end `tool_execute` handler

`gatewayEventHandler.ts:985-1001` calls
`internal_executeClientTool` for `tool_execute` events, but the LCA
back-end never produces `tool_execute`. The handler tests
[tests/.../gatewayEventHandler.test.ts:724-790] exercise the path
in isolation against a mocked store, so the dead path is "tested"
but never exercised in production.

**Effect**: client-side tool execution is wired for a back-end that
does not exist. Real LCA runs will never trigger
`internal_executeClientTool`.

### Gap G — `_commit_approval_requested` does not surface to WS

`SafeExecutor.execute` for `tool.name == "askUserQuestion"` calls
`_commit_approval_requested`
[safe_executor.py:296-301, 217-222], which only writes a journal
receipt. The front-end HIL card is presented via the **live SSE**
path (`done.status=awaiting_human`), bridged by
`deploy/lobehub/patches/runtime/lcaRunHil.ts` — the WS `resume_complete
{ status: 'waiting_input' }` path is independently useful but is
_not_ what the current askUserQuestion implementation uses.

**Effect**: the WS `resume_complete { status: 'waiting_input' }` is
correct for cross-tab reconnect, but the WS does not emit
`agent_intervention_request` to drive the intervention card. The
front-end's intervention UI is presented by the SSE path, then
replies via HTTP `/lca-api/runs/{runId}/answer`. This is a working
hybrid, but it relies on the lobehub SSE path which is *not* what
the user-facing WS lifecycle advertises.

## Wire parity table

| Event type (lobehub upstream) | LCA produces? | LCA front-end consumes? | Notes |
|---|---|---|---|
| `agent_runtime_init` / `agent_runtime_end` / `stream_start` / `stream_chunk` / `stream_end` / `visible_output_end` / `stream_retry` / `tool_start` / `tool_end` / `step_start` / `step_complete` / `notify_update` / `error` / `heartbeat` | Yes (translators exist) | Yes (cases exist) | Round-trip OK |
| `tool_execute` | **No** (Gap A) | Yes (case exists, Gap F) | Dead front-end path |
| `agent_intervention_request` | **No** (Gap B) | **No** (Gap E) | Replaced by HTTP `/runs/{id}/answer` bridge |
| `agent_intervention_response` | **No** (Gap C) | **No** (Gap E) | Never produced; only hetero executor handles it |
| `ToolResultMessage.idempotencyKey` (client→server field) | (back-end reads it; Gap D) | **No** (front-end does not send it; Gap D) | Tests expect it; production never sends it |

| Client→Server frame | LCA back-end handles? | LCA front-end sends? | Notes |
|---|---|---|---|
| `auth` | Yes | Yes | OK |
| `resume` (`lastEventId`, `wantStatus`) | Yes | Yes | OK |
| `heartbeat` | Yes | Yes | OK |
| `interrupt` | Yes | Yes | OK |
| `tool_result` | Yes (calls `resume_approval`) | Yes (via `internal_executeClientTool`) | Schema drift on `idempotencyKey` (Gap D); back-end always receives `""` |

| Server→Client frame | LCA back-end emits? | LCA front-end handles? | Notes |
|---|---|---|---|
| `auth_success` / `auth_failed` / `auth_expired` / `heartbeat_ack` | Yes | Yes | OK |
| `agent_event` | Yes | Yes | OK |
| `session_complete` | Yes (after `agent_runtime_end`) | Yes | OK |
| `resume_complete { status }` | Yes | Yes | OK |
| `wantStatus` round-trip | Yes | Yes | OK |

## Recommended fix order

The user asked for a report, not implementation. Each item below
identifies a single, scoped change. Per the AGENTS.md §1 ("接任务前
7 问"), any fix that changes a Protocol, ADG or enum is contract
work and must precede the corresponding implementation; Gap A, B, C,
E all touch the wire contract.

1. **Resolve Gap D first** — add `idempotencyKey: str | None = None`
   to `ToolResultMessage`
   [lca/contracts/transport/gateway_messages.py:56-62], to the
   upstream `ToolResultMessage` shape (or to a documented LCA
   extension), AND update `LcaAgentStreamClient.sendToolResult`
   [LcaAgentStreamClient.ts:225-227] to forward the field. Lowest
   risk; closes a real idempotency hole without inventing a new wire
   event. (Tests already expect it.) This is the only gap that is a
   single missing line.

2. **Decide Gap A vs Gap F** — does LCA actually want client-side
   tool execution over WS? If yes, wire the spine
   `body.tool.execute.start`/`end` to a new `tool_execute` translator
   [event_translator.py:421-434] (with a new `_tool_execute` static
   method that emits the args/identifier/apiName). If no, delete the
   dead front-end `case 'tool_execute'` branch
   [gatewayEventHandler.ts:985-1001] and the supporting tests
   [tests/.../gatewayEventHandler.test.ts:724-790] to remove the
   "tested but never exercised" lie. Same-PT delete per AGENTS.md §4
   "no delete-when = 红灯".

3. **Decide Gap B+C vs Gap E** — is the WS `agent_intervention_*`
   round-trip the user-facing contract, or is the HTTP
   `/lca-api/runs/{runId}/answer` route the SSOT? If the WS pair is
   the contract, emit them from
   `SafeExecutor._commit_approval_requested`
   [safe_executor.py:217-222] and add the front-end cases
   [gatewayEventHandler.ts:998] (mirroring
   [heterogeneousAgentExecutor.ts:2009-2073]). The HTTP bridge is the
   SSOT, so this audit stays in `docs/notes/plans/` and the dead
   `_agent_intervention_request` translator row is deleted
   [event_translator.py:266-278, 433]. The
   `AgentInterventionRequest`/`Response` schema classes
   [agent_stream_event.py:197-228, 312-316] are KEPT — the
   `AgentStreamEvent` union is byte-compat with native, and removing
   members would break the wire contract for hetero consumers.

4. **Wire parity test gap** —
   `tests/e2e/p1/test_lca_p1_01_user_books_flight.py:37-90` asserts
   Python types exist; it does NOT assert that the back-end
   produces them. Add a producer-side check: walk every registered
   `_HANDLERS` and `_SPINE_HANDLERS` key in
   `event_translator.py` and assert the corresponding EP / event
   type is reachable from a known runtime path
   (`runtime_loop.publish_terminal`, `safe_executor.execute`,
   `approval_requested_receipt`). This converts the current "every
   type defined" smoke into a real "every type producible" guard.

5. **Cross-tab idempotency on the real wire** — once Gap D is
   resolved, promote `tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py`
   to a non-skipped integration test (drop the
   `LCA_E2E_KERNEL=1` gate) by replacing the kernel dependency with
   the wire harness `tests/e2e/p1/_lca_gateway_client.py` — the
   idempotency check at
   [commands.py:169-176] is the actual safety boundary the user
   needs, and the wire harness already supports two-tab replay.

## Why not implement now

Per the task brief, the default is READ-ONLY and only proceed if the
gap is "a single missing line in an existing flow". Gap D meets that
bar (one field added to two schemas + one front-end send site).
Gaps A, B, C, E touch the wire contract; per AGENTS.md §1 they
require an ADR / Note first. Gap F is a delete-or-implement
decision. Implementing any of them in this branch would require
opening new tasks; the user explicitly asked for the report first.

## Alternatives considered

### Why not wire `tool_execute` via the spine EP today?

The `body.tool.execute.start` / `body.tool.execute.end` spine facts
already exist
[lca/infrastructure/session/emit/cognitive_emit.py:595-625] and are
translated to `tool_start` / `tool_end` for the WS path
[event_translator.py:349-401]. Reusing the SPINE facts to ALSO
emit a `tool_execute` (and keep the `tool_start` for the server-side
case) would let `internal_executeClientTool` fire when the runtime
chooses to delegate to the renderer. But it changes the
producer-vs-translator contract (the spine fact would now carry a
"who runs this tool" bit), which is a protocol change. Defer to a
follow-up ADR.

### Why not add `agent_intervention_request` to `_commit_approval_requested`?

`_commit_approval_requested` is the durable journal entry, not the
WS stream. The WS stream is folded by `EventTranslator.translate`
from `StampedEvent`s — the approval journal produces
`approval.persisted.v1` + `waiting_input` checkpoint
[lca/infrastructure/session/emit/lifecycle_emit.py:145-168], and
neither event currently flows through the EventTranslator.
Bridging means either (a) add `_approval_pause` /
`_approval_resolved` spine events and route them through
`_SPINE_HANDLERS` to emit `agent_intervention_request` /
`_response`, or (b) translate the journal facts directly in
`EventTranslator`. Either is a closed-set change (ADR §C11 territory).

### Why not collapse the HTTP `/runs/{id}/answer` into the WS?

The HTTP bridge exists because the lobehub `customInteractionSubmit`
handler in the upstream code path doesn't have access to the LCA
WS socket; the patch is a thin adapter. Collapsing into WS would
mean teaching the lobehub `customInteractionSubmit` to dial LCA's
WS — exactly the kind of cross-PR architectural change the user
asked us to identify, not silently absorb.

## Acceptance criteria for re-opening

This audit closes; the gaps become tracked work when:

- Gap D resolution lands a one-field schema extension + a front-end
  send update + tests pass on both sides
  (`tests/integration/p1/test_lca_p1_node_05_tool_result.py`,
  `tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py`).
- Gaps A/B/C/E/F are each promoted to a single proposed Note (this
  audit's owner = whoever closes the gap), with the chosen
  delete-or-implement decision.
- The parity test (item 4 above) lands with the same pytest
  collection as `test_lca_p1_01_user_books_flight.py`.

## Related

- [docs/adr/0201-tool-result-prompt-closure.md](../../adr/0201-tool-result-prompt-closure.md) —
  tool-result closure decision; does not yet cover the WS path.
- [docs/notes/proposed/contract/2026-09-07-p1-facade-ws-token-todo.md](../proposed/contract/2026-09-07-p1-facade-ws-token-todo.md) —
  deferred `ws_token` + `lca_running_operations` writer; orthogonal.
- [lobehub-ui/packages/agent-gateway-client/src/types.ts:286-307] —
  upstream TS `ToolResultMessage` (no `idempotencyKey`).
