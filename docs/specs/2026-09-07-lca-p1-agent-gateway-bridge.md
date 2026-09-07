# LCA P1: Agent Gateway Bridge — Design Spec

> **Status:** DRAFT (post-brainstorm, pre-writing-plans)
> **Date:** 2026-09-07
> **Owner:** LCA platform
> **Phase:** P1 of 3 (P2/P3 deferred — see §13)
> **Brainstorm lock-list:** 12 questions answered, see [§15](#15-brainstorm-decisions).

## 1. Background and motivation

LCA currently exposes its agent runtime to the LobeHub UI over **Server-Sent Events** with a 4-event encoding (`reasoning / text / tool / done`) emitted from `LiveRunProjection` (`lca/plugins/transport/run_ui_encoder__encoder_provider.py:147-249`). The transport is hand-rolled and has the following five fragility findings, all observed in production code paths and confirmed by `spike 3` (see [§14.3](#143-spike-results)):

| # | Where | Why it's broken |
|---|---|---|
| 1 | `LcaRunDriver.ts:719-720` writes `message.metadata.lca` but no renderer reads it; `askUserQuestion.tsx:93-94` only reads `pluginState.lca.run_id` | Two parallel stores for the same logical fact (`run_id`); whichever path is missed freezes the card. |
| 2 | `lcaRunHil.presentAskUserCard` is async and races `streamTerminal`; the run can complete before the card materialises | Cards can become permanently unanswerable. |
| 3 | `RunUiEncoder._process_item` (`run_ui_encoder__encoder_provider.py:229-249`) silently drops child-run `AgentRunFinished` events that have a non-null `_parent_run_id`. When the child finishes, the parent SSE hangs because `_synthetic_done_payload` is only emitted when the parent's `status` already moved to terminal. | "Stuck stream" without an error to the client. |
| 4 | `stream_run_live` (`query_endpoints.py:144-168`) does not 410 the run when the tail has been GC'd but `summary` still exists. The client guesses from `LIVE_MAX_RECONNECTS = 8` (`lcaRunObserve.ts:19-22`) — purely empirical. | No authoritative terminal signal; client and server can disagree. |
| 5 | `resume_approval.approval_id_matched` is **logged, not enforced** (`registry/commands.py:239-247`). The frontend sends `approval_id: toolCallId` (`askUserQuestion.tsx:106`, `customInteractionHandlers.ts:178`, `conversationControl.ts:865`); the backend stores `<plan_ref>:<node>:<visit>` in `session.approval_request`. They are structurally incomparable. Idempotency lives only in `accepted_answer_keys`, a **process-local set** that evaporates on restart. | Resumes are correct only by accident, and only within one process. |

These are not bugs in the run engine — they are properties of the transport layer. The fix is to retire the transport layer and replace it with the **same WebSocket + Redis Stream + JWT + `lastEventId` + `resume_complete` protocol that native LobeHub already ships in production** (`packages/agent-gateway-client/src/client.ts` + `apps/server/src/modules/AgentRuntime/StreamEventManager.ts`). LCA's role is to **be a faithful server implementation of the same wire protocol**, with `Journal` + `RunSession` + `RunRegistry` continuing to own the actual agent state.

### Why now

- The hand-rolled transport cannot be made reliable by patching it; every patch grows the divergence with the upstream protocol.
- The same WS protocol is already the canonical "one POST = one agent" surface (ADR-0100, ADR-0199 P1-13). Adding a second, LCA-only transport forks the mechanism.
- `lca_running_operations` is empty, the WebSocket path is the only one not blocked by an existing product feature. There is no migration cost.

## 2. Goals and non-goals

### Goals (P1)

1. **One LCA run ≡ one native operation.** One `POST /lca-api/runs` returns a `run_id`; the same `run_id` carries through WS, approval, and reconnection. No `op_id` vs `run_id` split.
2. **Reuse native `AgentStreamEvent` schema 1:1.** Python server emits the same 18 wire types the client expects; client `gatewayEventHandler` runs unmodified.
3. **WebSocket as primary transport.** Native `AgentStreamClient` (heartbeat, reconnect, `lastEventId`, `resume_complete`, `auth_expired`/`auth_failed`) handles all live, reconnect, and cross-refresh flows.
4. **JWT auth (RS256, 5 min)** with `refreshToken` procedure, mirroring native `signUserJWT` (`packages/trpc/src/utils/internalJwt.ts:97-106`).
5. **Live state is the Redis Stream.** `lca_running_operations` table holds only the routing/business index; terminal status is read from the Redis Stream's `status` field, liveness from the key's TTL.
6. **HIL on the same `run_id`.** `POST /lca-api/runs/{id}/answer` continues to drive the same run, gated by `accepted_answer_keys` (now persisted in the same table).
7. **Cross-refresh reconnect.** `useGatewayReconnect` reads the LCA-owned table through a plain HTTP endpoint `GET /lca-api/topics/{topic_id}/running-op` (no tRPC; see §5.6).
8. **7 e2e scenarios pass + 1 h stability smoke.** The acceptance bar before P2 starts.

### Non-goals (P1)

- Multi-tab / multi-device broadcast demultiplex (native `GatewayStreamNotifier` mirror) — **P2**.
- Group / sub-agent orchestration through the WS channel — **P2**.
- Cursor-rewind across process restarts that happen *during* a run with `status='running'` — partial P1 (reconnect after restart is covered; true zero-downtime multi-instance is **P3**).
- LobeHub cloud (`https://agent-gateway.lobehub.com`) interop — LCA server is internal; the `agentGatewayUrl` is a localhost/cluster URL only.
- Replacing the run engine (`RunLifecycleCoordinator`, `Journal`, `RunSession`). **The seam is the transport, not the engine.**

## 3. Architecture overview

### 3.1 Four-layer separation

| Layer | Owns | Native equivalent | LCA's new home |
|---|---|---|---|
| **Fact** | What happened (agent step, tool call, decision) | `AgentRuntime` (TS), `Session.append` | **unchanged** — `Journal` + `spine.jsonl` + `Session.append` |
| **Projection** | View over the facts (message tree, status, step count) | `LiveRunProjection` (TS) | `LiveRunProjection` (Python) — fold only, no protocol |
| **Transport** | How projections cross process boundaries | `StreamEventManager` + WS gateway (TS) | `LcaStreamEventManager` + `LcaAgentGateway` (Python) |
| **Session** | Auth, cursor, heartbeat, reconnect | `AgentStreamClient` (TS) | `AgentStreamClient` (TS, **unchanged** — points to LCA URL) |

Boundary rule: **Transport never inspects facts; it only translates fold events into wire events.** This is the rule the existing 4-event encoder violates (§1, items 3 & 4).

### 3.2 Component map (P1)

```
                        Browser
                          │
            ws://host:3010/lca-api/ws?operationId=<run_id>
                          │   (Next.js rewrite → LCA :8765)
                          ▼
        ┌────────────────────────────────────────────┐
        │  LcaAgentGateway (Starlette WebSocketRoute)│
        │  - HMAC-validated WS upgrade (CORS)        │
        │  - auth → JWT verify (RS256, 5 min)        │
        │  - resume { lastEventId, wantStatus:true } │
        │  - heartbeat ↔ heartbeat_ack (30s)         │
        │  - interrupt → RunPort.cancel(run_id)      │
        │  - tool_result → RunPort.resume_approval() │
        └────────────────────┬───────────────────────┘
                             │ subscribe / XADD
                             ▼
        ┌────────────────────────────────────────────┐
        │  Redis (existing, 127.0.0.1:6379)          │
        │  key: agent_runtime_stream:<run_id>        │
        │  TTL: 2 h, MAXLEN: ~1000                    │
        └────────────────────┬───────────────────────┘
                             │ XREAD BLOCK
                             ▼
        ┌────────────────────────────────────────────┐
        │  LcaStreamEventManager (mirror native)     │
        │  - publishStreamEvent(type, data, step)    │
        │  - subscribeStreamEvents(after_seq, cb)    │
        │  - getStreamHistory(run_id, count)         │
        │  - cleanupOperation(run_id)                │
        └────────────────────┬───────────────────────┘
                             │ invoked by
                             ▼
        ┌────────────────────────────────────────────┐
        │  LcaAgentRuntimeCoordinator                │
        │  - subscribes LiveRunProjection tail       │
        │  - folds StampedEvent → AgentStreamEvent   │
        │  - terminal-hint resolution                │
        │  - emits stream_start/stream_end/          │
        │    agent_runtime_init/end/visible_output_end│
        └────────────────────┬───────────────────────┘
                             │ reads
                             ▼
        ┌────────────────────────────────────────────┐
        │  LiveRunProjection (unchanged, fold only)  │
        │  spine.jsonl → StampedEvent → projection   │
        └────────────────────────────────────────────┘
```

`lca_running_operations` table (new, thin):

```sql
CREATE TABLE lca_running_operations (
  run_id              text PRIMARY KEY,
  topic_id            text NOT NULL,
  agent_id            text NOT NULL,
  assistant_message_id text,
  scope               text NOT NULL DEFAULT 'main',
  created_at          timestamptz NOT NULL DEFAULT now(),
  accepted_answer_keys jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX lca_running_operations_topic_id_idx
  ON lca_running_operations (topic_id);
```

No `status` column. No `last_event_id` column. Liveness and status live in Redis; idempotency lives in the table.

## 4. Data flows (the four user-visible flows)

### 4.1 Happy path: one question → one answer

```
Browser                       Next.js :3010                 LCA :8765                      Redis
  │                               │                            │                            │
  │ POST /lca-api/runs           │                            │                            │
  │ { messages, model, agent }   │                            │                            │
  │──────────────────────────────>                            │                            │
  │                               │ rewrite → POST /runs      │                            │
  │                               │───────────────────────────>│                            │
  │                               │                            │ create_and_dispatch()      │
  │                               │                            │ ├─ RunPort.create_and_dispatch
  │                               │                            │ ├─ LcaAgentRuntimeCoordinator.start(run_id)
  │                               │                            │ ├─ insert lca_running_operations
  │                               │                            │ └─ XADD agent_runtime_stream:{run_id}
  │                               │                            │      type=agent_runtime_init
  │                               │                            │──────────────────────────>│
  │ <───────────── 202 { run_id, trace_id, ws_token } ───────│                            │
  │                                                                      │                │
  │ ws://:3010/lca-api/ws?operationId=<run_id>                            │                │
  │─────────────────────────────────────────────────────────>            │                │
  │                               │ rewrite → ws://:8765/ws   │                            │
  │                               │───────────────────────────>│                            │
  │                               │                            │ accept + auth challenge    │
  │ {type:auth, token}            │                            │                            │
  │──────────────────────────────>                            │                            │
  │                               │                            │ verify JWT (sub, exp, op)   │
  │ {type:auth_success}           │                            │                            │
  │ <─────────────────────────────│                            │                            │
  │ {type:resume, lastEventId:'', wantStatus:true}             │                            │
  │──────────────────────────────>                            │                            │
  │                               │                            │ XREAD STREAMS 0            │
  │ {type:agent_event, id, event:agent_runtime_init}          │                            │
  │ <──────────────────────────────────────────────────────────│                            │
  │ {type:resume_complete, status:'running'}                   │                            │
  │ <──────────────────────────────────────────────────────────│                            │
  │                                                                     │                │
  │          … LiveRunProjection tail emits events …                     │                │
  │                                                                     │                │
  │ {type:agent_event, event:stream_start {assistantMessage.id}}        │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:agent_event, event:stream_chunk {chunkType:'text', content}}  │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:agent_event, event:tool_start {payload, parentMessageId}}     │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:agent_event, event:stream_end}                                │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:agent_event, event:visible_output_end}                        │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:agent_event, event:agent_runtime_end {reason:'completed'}}    │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │ {type:session_complete}                                             │                │
  │ <──────────────────────────────────────────────────────────────────│                │
  │                               │                            │                            │
```

### 4.2 HIL pause + resume (same `run_id`)

```
Browser                                         LCA :8765
  │                                              │
  │ {type:agent_event, event:step_start          │
  │   {phase:'human_approval', requiresApproval:true,
  │    pendingToolsCalling:[…]}}                 │
  │ <───────────────────────────────────────────│
  │                                              │  ← LiveRunProjection fold recognizes
  │                                              │    StepStart with requiresApproval
  │                                              │    → Coordinator emits step_start + agent_runtime_end
  │                                              │      (reason='waiting_for_human'); run stays alive
  │ {type:agent_event, event:agent_runtime_end   │
  │   {reason:'waiting_for_human', finalState}}  │
  │ <───────────────────────────────────────────│
  │ {type:session_complete}                       │
  │ <───────────────────────────────────────────│  ← client disconnects
  │                                              │
  │ render askUserQuestion card from             │
  │   step_start.data.pendingToolsCalling        │
  │                                              │
  │ ws://:3010/lca-api/ws?operationId=<run_id>   │
  │ (reconnect for the same op)                  │
  │─────────────────────────────────────────────>│
  │ {type:auth, token}    →  {type:auth_success} │
  │ {type:resume, lastEventId, wantStatus:true}  │
  │ → {type:resume_complete, status:'waiting_input'}  ← run still in waiting_input
  │                                              │
  │ User clicks Approve. Frontend posts          │
  │   POST /lca-api/runs/<run_id>/answer         │
  │   {approval_id, payload, idempotency_key}    │
  │ ────────────────────────────────────────>   │
  │                                              │  RunPort.resume_approval:
  │                                              │    - if idempotency_key in accepted_answer_keys
  │                                              │      → return {accepted:true, status:'resumed'}
  │                                              │    - else if session.status != WAITING_INPUT
  │                                              │      → 409
  │                                              │    - else: append to accepted_answer_keys
  │                                              │      create_task(resume_run) on same session
  │ {accepted:true, status:'resumed'}            │
  │ <──────────────────────────────────────────  │
  │                                              │
  │ {type:agent_event, event:step_start          │  ← next step
  │   {phase:'tool_execution', …}}               │
  │ <───────────────────────────────────────────│
  │ {type:agent_event, event:tool_end {ok:true}} │
  │ <───────────────────────────────────────────│
  │ {type:agent_event, event:agent_runtime_end   │
  │   {reason:'completed'}}                      │
  │ <───────────────────────────────────────────│
  │ {type:session_complete}                       │
  │ <───────────────────────────────────────────│
```

### 4.3 Page refresh during a live run

```
Browser                              Next.js :3010                LCA :8765                Postgres
  │                                       │                          │                       │
  │   (user refreshes the page)           │                          │                       │
  │                                       │                          │                       │
  │ useGatewayReconnect(topicId)          │                          │                       │
  │   ├─ fetch /lca-api/topics/${topicId}/running-op             │                       │
  │   │  ─────────────────────────────────>│  rewrite → GET /v1/topics/{topic_id}/running-op   │             │
  │   │                                   │                          │ SELECT run_id,… FROM   │
  │   │                                   │                          │ lca_running_operations │
  │   │                                   │                          │ WHERE topic_id=$1      │
  │   │                                   │                          │ LIMIT 1                │
  │   │                                   │                          │<───────────────────────│
  │   │  { run_id, topic_id, agent_id,    │                          │                       │
  │   │    assistant_message_id, … }      │                          │                       │
  │   │  <─────────────────────────────────│                          │                       │
  │   │                                   │                          │                       │
  │   ├─ if missing: bail (no reconnect)  │                          │                       │
  │   │                                   │                          │                       │
  │   ├─ else: connectToGateway({         │                          │                       │
  │   │   operationId: run_id,            │                          │                       │
  │   │   resumeOnConnect: true,          │                          │                       │
  │   │   token: existing ws_token        │                          │                       │
  │   │ })                                │                          │                       │
  │   │                                   │ ws://:3010/lca-api/ws?operationId=<run_id>           │
  │   │                                   │ ───────────────────────>│                       │
  │   │                                   │                          │  EXECISTS agent_runtime_stream:{run_id}?
  │   │                                   │                          │   - false → run is dead; emit session_complete; clear table
  │   │                                   │                          │   - true  → XREAD lastEventId onwards
  │   │ {type:agent_event, …replay…}       │                          │                       │
  │   <────────────────────────────────────│                          │                       │
  │ {type:resume_complete, status:…}       │                          │                       │
  │ <───────────────────────────────────────│                          │                       │
```

Note: `useGatewayReconnect` does **not** call the refresh endpoint — the existing `ws_token` is still valid until the 5-minute expiry. If the token has expired, the gateway replies with `auth_expired` instead, and the WS client then calls `POST /lca-api/runs/{run_id}/ws-token` for a fresh one (handled by the native `AgentStreamClient` `auth_expired` callback, see §5.4).

### 4.4 Network drop mid-run

```
Browser                                       LCA :8765                    Redis
  │                                                │                          │
  │  (kernel-level: wifi off / tab suspended)      │                          │
  │  WS frames stop arriving                        │                          │
  │                                                │                          │
  │  agentStreamClient.handleClose                  │                          │
  │   ├─ emit 'reconnecting' (delay: 1s)            │                          │
  │   ├─ setTimeout 1s → doConnect                  │                          │
  │   ├─ WS opens → auth_success                    │                          │
  │   ├─ resume {lastEventId, wantStatus:true}      │                          │
  │   │                                            │                          │
  │   │                          XREAD STREAMS     │                          │
  │   │                          key lastEventId ──>│                          │
  │   │                                            │  [events 47..51]         │
  │   │                                            │<─────────────────────────│
  │   │  emit events in order, dedup by id          │                          │
  │   <─────────────────────────────────────────────│                          │
  │  resume_complete { status: 'running' }          │                          │
  │  <─────────────────────────────────────────────│                          │
  │                                                │                          │
  │  (live frames 52+ resume)                       │                          │
```

This is the **same path** native `AgentStreamClient` already implements and tests against. P1 inherits it without modification.

## 5. Component details

### 5.1 `LcaStreamEventManager` (Python mirror of `apps/server/src/modules/AgentRuntime/StreamEventManager.ts`)

Location: `lca/infrastructure/observability/stream/stream_event_manager.py`

Mirror — same Redis key, TTL, MAXLEN, XADD fields, XREAD shape:

```python
class LcaStreamEventManager:
    STREAM_PREFIX = "agent_runtime_stream"
    STREAM_RETENTION = 2 * 3600  # 2 hours
    MAXLEN = "~1000"

    def __init__(self, redis: Redis) -> None: ...
    async def publish(self, run_id: str, type: str, data: dict, *, step_index: int) -> str: ...
    async def subscribe(self, run_id: str, last_id: str, *, signal: AbortSignal | None = None) -> AsyncIterator[bytes]: ...
    async def read_history(self, run_id: str, count: int) -> list[dict]: ...
    async def cleanup(self, run_id: str) -> None: ...
    async def exists(self, run_id: str) -> bool: ...
    async def last_id(self, run_id: str) -> str | None: ...
```

Behavioural parity rules (validated by `tests/infrastructure/observability/stream/test_stream_event_manager.py`):

- `XADD MAXLEN ~ 1000` (approximate trim, same as native).
- `EXPIRE 7200` after every XADD (refresh TTL on every write, same as native `StreamEventManager.ts:196`).
- `XREAD BLOCK 1000 STREAMS key lastId` for the live subscribe loop (native: `StreamEventManager.ts:289-299`).
- `readEventsOnce` resolves the `$` sentinel to the concrete tail id before blocking (native: `StreamEventManager.ts:388-394`).
- `data` payload is JSON-stringified; `stepIndex` and `timestamp` are stored as integers (string-encoded in Redis fields, parsed on read).
- No `messages` / `tools` / `operationToolSet` are stored in events (native `stripFinalStateInEventData` at `StreamEventManager.ts:78-96`).

### 5.2 `LcaAgentRuntimeCoordinator` (mirrors `AgentRuntimeCoordinator.ts`)

Location: `lca/application/runtime/coordinator/runtime_coordinator.py`

Subscribes to `LiveRunProjection.tail.subscribe(after_seq=0)` of the run's session, and on each `StampedEvent`:

1. Folds it into a candidate `AgentStreamEvent` via `EventTranslator` (see 5.3).
2. Decides terminality:
   - `run.lifecycle.failed` / `agent_run_finished` with `parent_run_id is None` AND `final_state.status in {done, error, interrupted, waiting_for_human}` → emit `agent_runtime_end` with `reason = final_state.status`.
   - `run.lifecycle.waiting_input` (intermediate pause) → emit `step_start { phase: 'human_approval', requiresApproval: true }` + immediately follow with `agent_runtime_end { reason: 'waiting_for_human' }` to close the live stream for this run (the **same `STREAM_END_STATUSES` set** as native `AgentRuntimeCoordinator.ts:30-34`).
3. Non-terminal foldable events (`LlmCallTextDelta`, `ToolStarted`, `ToolInvoked`, `ToolDenied`, `StepStart`, `StepFinished`, `ReasoningDelta`, `DecisionMade`) → emit `stream_chunk` / `tool_start` / `tool_end` / `step_start` (without `uiMessages`; see 5.5) / `visible_output_end` (after the last `ToolInvoked` of a step).

The two fixes for the `LiveRunProjection` §1 broken behaviours:

- **#3 (parent_run_id dropped child):** `EventTranslator` keeps child-run events as `step_start { phase: 'subagent_progress', subagentOperationId: child_id }`; it does **not** drop them. The parent's terminal emission waits for the parent's own `final_state.status`, not for child completion.
- **#4 (stuck stream when tail is empty):** `RuntimeCoordinator` runs an **in-process watchdog** every 1 s: if the run's `session.status` is in `STREAM_END_STATUSES` but the live stream has not received a corresponding `StampedEvent`, the coordinator synthesises the `agent_runtime_end` itself. (Native has the same guarantee because the run engine emits the lifecycle event directly; in LCA the lifecycle event is the `SpineEvent`, and the watchdog closes the gap when the journal is closed but the live tail is GC'd.)

### 5.3 `EventTranslator` (StampedEvent → AgentStreamEvent)

Location: `lca/application/runtime/coordinator/event_translator.py`

The translation table (one row per native `AgentStreamEvent` type):

| `StampedEvent.event` | Emitted `AgentStreamEvent.type` | `data` shape |
|---|---|---|
| `LlmCallStarted` | `stream_start` | `{assistantMessage: {id, model, provider, role, parentId, topicId, threadId, groupId, agentId}}` |
| `LlmCallTextDelta {channel:'answer', delta}` | `stream_chunk` | `{chunkType:'text', content, snapshotMode:'append'}` |
| `ReasoningDelta {delta}` | `stream_chunk` | `{chunkType:'reasoning', content}` |
| `DecisionMade {tool_calls}` | `stream_chunk` | `{chunkType:'tools_calling', toolsCalling}` |
| `ToolStarted {payload}` | `tool_start` | `{parentMessageId, toolCalling:{identifier,apiName,arguments,id,type:'builtin'}}` |
| `ToolInvoked {payload,result}` | `tool_end` | `{isSuccess, result, payload, executionTime}` |
| `ToolDenied {reason}` | `tool_end` | `{isSuccess:false, result:{error:reason}}` |
| `ImageGenerated {url}` | `stream_chunk` | `{chunkType:'base64_image', images:[{data,id}]}` |
| `StepStart {phase, requiresApproval, pendingToolsCalling}` | `step_start` | `{phase, requiresApproval, pendingToolsCalling}` (no `uiMessages`) |
| `StepFinished` | `stream_end` (if a `stream_start` was emitted) + `visible_output_end` | `stream_end.data = {finalContent, …}`; `visible_output_end.data = {reason: 'completed'}` |
| `SpineClose {reason, final_state}` | `agent_runtime_end` | `{finalState: {status: 'done'|'error'|'interrupted'|'waiting_for_human'}, reason, reasonDetail, phase: 'execution_complete'}` |
| `LlmError {error}` | `error` | `{type, message, body, provider}` |
| `LlmRetry {attempt, max}` | `stream_retry` | `{attempt, max, provider}` |
| `AgentInterventionRequest {apiName, identifier, args, toolCallId, deadline}` | `agent_intervention_request` | `{apiName, identifier, arguments, toolCallId, deadline}` |
| (no LCA equivalent yet) | `step_complete` | not emitted in P1; reserved for sub-agent progress (P2) |

#### 5.3.1 Server-side persistence obligation (the rule that makes renderers work)

The `tool_end` event above carries `{isSuccess, result, payload, executionTime}` only — no `projected_state`. The front-end tool renderers (`lcaToolRender/renderers/lobe-*/<tool>.tsx`) read `message.pluginState.<field>` for their display (e.g. `executeCode.tsx:11-12` reads `pluginState.language / code`; `readFile.tsx` reads `pluginState.content`; `runCommand.tsx` reads `pluginState.command / stdout / stderr`). For these renderers to display anything, the **server** must persist the full observation into the tool message's `pluginState` column **before** the WS event is published.

This is the same convention native follows without stating it: `packages/context-engine/src/processors/MessageContent.ts:465-467` and `GroupMessageFlatten.ts:128` write `pluginState: tool.result.state` into the message row from server-side data; the front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages` reads the already-populated row. LCA does the same: the `LcaAgentRuntimeCoordinator` is responsible for persisting the full `ToolRenderContract.projected_state` into the DB **as part of the tool-call lifecycle**, not as a follow-up. The WS event is only the trigger that tells the front-end to refetch.

Specifically:

1. When `LiveRunProjection` emits `ToolStarted`, the coordinator creates the tool message row with `pluginState: { identifier, apiName, args }` and persists it. The `tool_start` WS event is published **after** the DB write.
2. As the tool runs, the coordinator streams `ToolInvoked` deltas (`sandbox-delta` in the projection) to the live tail; the front-end accumulates them in the message's `pluginState` via `internal_dispatchMessage` for streaming output (this is a separate signal — sandbox stdout/stderr is best-effort; the canonical observation lands in step 4).
3. When the tool returns, the coordinator computes the full `projected_state` via `lca.cognition.body.tool_journal_emit.project_tool_state(name, args, observation)` (already used by the legacy `RunUiEncoder`; see `lca/cognition/body/tool_journal_emit.py:246-263` for the dict shape). The coordinator writes this dict into the `messages[].pluginState` column.
4. Only then does the coordinator publish `tool_end` via `LcaStreamEventManager.publish`. The front-end `gatewayEventHandler.tool_end` triggers `fetchAndReplaceMessages` and reads the already-populated row.

This sequence guarantees the front-end tool renderer always reads the final `pluginState` after `tool_end` arrives, without depending on any in-flight WS payload. The parity test L3-7 asserts this end-to-end: a sandbox-style tool that streams `sandbox-delta` events and then returns a `ToolInvoked` must result in a `messages[].pluginState` row that satisfies the renderer's reads.

#### 5.3.2 HIL submission (the question of how `askUserQuestion` returns to the server)

The `AgentInterventionRequest` event mirrors native (`packages/agent-gateway-client/src/types.ts:185-201`). The server emits it when the agent invokes a `humanIntervention: 'always'` tool such as `askUserQuestion`. The server-side runtime then **blocks** until the user submits an answer; the run's `session.status` becomes `WAITING_INPUT`.

The front-end's `askUserQuestion` card submission does **not** go over the WS channel. The reason: native defines `tool_result` (client → server) as the response to `tool_execute` (server → client), but `AgentInterventionRequest` is a different mechanism — the answer is delivered as an HTTP command, not as a tool-execution result. The submission path is:

1. The user fills the card and submits.
2. The native `Intervention` component (`src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/index.tsx`) calls the registered `CustomInteractionSubmitHandler` for the `lobe-user-interaction____askUserQuestion` identifier.
3. LCA's handler (`handleLcaAskUserSubmit` in `src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts:138-198`) reads the `requestArgs.lca_run_id` from the tool message's `pluginState` (this was written by `lcaRunHil.presentAskUserCard` at HIL setup time) and posts to `POST /lca-api/runs/{run_id}/answer` with `{approval_id, payload, idempotency_key}`.
4. The native handler returns `{ options: { skipResume: true } }` to the `Intervention` component, which **does not** dispatch a `submitToolInteraction` op (i.e. the native WS-based resume is not used). The HIL answer is delivered by the LCA HTTP call, and the WS stream resumes naturally when the server-side `RunPort.resume_approval` kicks off a new step.

This is the same path LCA uses today, and P1 keeps it: `POST /lca-api/runs/{run_id}/answer` **remains** (it was the mistaken §5.6 "retired" wording that I corrected). The `lca_runtime_agent_gateway` patch module (§6.1.2) ships a minimal `customInteractionHandlers.ts` rewriter that registers `handleLcaAskUserSubmit` against the native `findCustomInteractionSubmitHandler` lookup.

The skip / cancel paths (`lcaSkipState`, `lcaCancelState` in current `conversationControl.ts:855-1005`) **also remain** as plain HTTP calls to `POST /lca-api/runs/{run_id}/answer` (with a `payload: 'User skipped this question.'` text) and `POST /lca-api/runs/{run_id}/cancel`. The `lca_runtime_agent_gateway` patch module preserves them.
| (no LCA equivalent yet) | `notify_update` | not emitted in P1 |

Channels: native `TEXT_CHANNEL_ANSWER` is the only `text` channel in P1. `TEXT_CHANNEL_ALL` (debug) is excluded (P1 feature parity, not parity with native dev tooling).

### 5.4 `LcaAgentGateway` (Starlette WebSocketRoute)

Location: `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py`

Lifecycle (mirrors native `apps/server/src/services/agentRuntime/AgentRuntimeService.ts` + `apps/server/src/modules/AgentRuntime/GatewayStreamNotifier.ts`):

```python
@webSocketRoute("/v1/runs/{run_id}/ws")
class LcaAgentGateway:
    async def __call__(self, ws: WebSocket) -> None:
        run_id = ws.path_params["run_id"]
        await ws.accept()
        try:
            auth = await ws.receive_json()  # expects {type:'auth', token}
            claims = self._verify_jwt(auth["token"], expected_op=run_id)
        except (ValueError, _JwtError):
            await ws.send_json({"type":"auth_failed","reason":"bad token"})
            await ws.close()
            return

        await ws.send_json({"type":"auth_success"})

        resume = await ws.receive_json()  # expects {type:'resume', lastEventId, wantStatus}
        history = await self._history(run_id, resume["lastEventId"])
        for event in history:
            await ws.send_json(event)
        if resume.get("wantStatus"):
            status = await self._status_for(run_id)
            await ws.send_json({"type":"resume_complete","status":status})
            if status in TERMINAL_STATUSES:
                await ws.send_json({"type":"session_complete"})
                await ws.close()
                return

        await self._live_loop(ws, run_id, resume["lastEventId"])
```

`_live_loop` is the native-equivalent: an XREAD `BLOCK 1000` loop that yields `agent_event` frames until either the run reaches a terminal status (drives `agent_runtime_end` + `session_complete` + close) or the client disconnects.

Client messages (subset implemented in P1): `auth`, `resume`, `heartbeat` (server replies `heartbeat_ack`), `interrupt` (calls `RunPort.cancel(run_id)`), `tool_result` (calls `RunPort.resume_approval(run_id, approval_id, payload, idempotency_key)`). **`auth_expired`** is emitted when the JWT is past `exp` but the run is still alive; the client then calls `POST /lca-api/runs/{run_id}/ws-token` to obtain a new token, calls `updateToken`, and reconnects.

### 5.5 `GET /lca-api/messages` endpoint

Location: `lca/plugins/transport/webserver/handlers/runs/api/message_query_endpoints.py`

```python
@route("/v1/topics/{topic_id}/messages", methods=("GET","OPTIONS"))
async def get_topic_messages(request):
    topic_id = request.path_params["topic_id"]
    agent_id = request.query_params.get("agentId")
    thread_id = request.query_params.get("threadId")
    group_id = request.query_params.get("groupId")
    skip_works = request.query_params.get("skipWorks") == "true"
    user_id = request.state.user_id
    msgs = await message_service.get_messages(
        ctx={"user_id": user_id, "topic_id": topic_id,
             "agent_id": agent_id, "thread_id": thread_id,
             "group_id": group_id, "skip_works": skip_works},
    )
    return json_response({"messages": msgs})
```

Thin wrapper over the existing `MessageService.getMessages` (LCA equivalent: `lca/plugins/transport/webserver/handlers/runs/session/message/history.py`). Native `gatewayEventHandler` already does a plain `fetch`, so this endpoint is plain HTTP. The path is the existing `/lca-api/*` catch-all rewrite target — no Next.js change.

The `gatewayEventHandler` resolves the URL via a new helper: `const url = '/lca-api/topics/${topicId}/messages';` (no `lcaGatewayMessagesUrl` config; the rewrite handles routing).

### 5.6 Plain HTTP, no tRPC

**Decision:** LCA does not introduce a tRPC router. All front-end → back-end paths in P1 are plain HTTP `fetch` calls, matching the existing `/lca-api/runs`, `/lca-api/messages`, etc. (no native tRPC equivalent needed in this repo).

Rationale: the LobeHub `apps/server` tRPC layer is part of the LobeHub Next.js process; the LCA gateway is a separate Python process. Adding tRPC here would mean either (a) running a tRPC server in Python (out of scope, no native Python reference), or (b) using LobeHub's tRPC as a thin proxy that forwards to LCA gateway over plain HTTP (one extra hop, no type safety gain over `fetch` + `zod`). The existing `/lca-api/runs` is plain HTTP for the same reason; P1 follows the same pattern.

**Five HTTP endpoints** (all routed through the existing `next.config.ts:43-49` `/lca-api/:path*` rewrite, no Next.js change required):

| Method | Path | Used by | Handler location |
|---|---|---|---|
| `POST` | `/lca-api/runs` | front-end `executeGatewayAgent` (start) | existing `command_endpoints.create_run` (signature change in §5.6.1) |
| `GET` | `/lca-api/runs/{run_id}` | front-end on reconnect (resume token source) | existing `query_endpoints.get_run` (response extended) |
| `GET` | `/lca-api/topics/{topic_id}/running-op` | `useGatewayReconnect` cross-refresh | new `query_endpoints.get_running_operation` |
| `POST` | `/lca-api/runs/{run_id}/cancel` | front-end `interruptGatewayAgent`; also front-end skip/cancel for HIL | existing `command_endpoints.cancel_run` |
| `POST` | `/lca-api/runs/{run_id}/answer` | front-end submit of HIL answer (askUserQuestion); wired via the native `CustomInteractionSubmitHandler` hook (see §6.1.5) | existing `command_endpoints.answer_run` |
| `POST` | `/lca-api/runs/{run_id}/ws-token` | front-end on `auth_expired` to mint a fresh JWT | new `command_endpoints.refresh_ws_token` |

`/lca-api/runs/{run_id}/live` is **retired** in P1 (handled by the new WS stream at `/lca-api/ws`). `/answer` and `/cancel` **remain** because HIL answers and run cancellation are control-plane commands that complete over plain HTTP — the new design keeps these endpoints and wires them to the native submit / cancel flow through the existing `CustomInteractionSubmitHandler` hook (see §6.1.5).

#### 5.6.1 `POST /lca-api/runs` (response change)

The current receipt is `{run_id, trace_id, agent, live_url}`. P1 adds `ws_token` to the response so the front-end can connect immediately:

```json
{
  "run_id": "run_<hex>",
  "trace_id": "trace_<hex>",
  "agent": {"id": "agent_<hex>", "name": "..."},
  "ws_token": "<RS256 JWT, sub=user_id, exp=now+300s, purpose=cli-sandbox>"
}
```

The `live_url` field is removed (no more `/live` SSE endpoint).

`useGatewayReconnect` does not call `/lca-api/runs`. It only reads the existing run via §5.6.2.

#### 5.6.2 `GET /lca-api/topics/{topic_id}/running-op`

```python
@route("/v1/topics/{topic_id}/running-op", methods=("GET","OPTIONS"))
async def get_running_operation(request):
    user_id = request.state.user_id
    row = await db.fetchone(
        """SELECT run_id, topic_id, agent_id, assistant_message_id, scope, created_at
           FROM lca_running_operations
           WHERE topic_id = $1
           ORDER BY created_at DESC LIMIT 1""",
        request.path_params["topic_id"],
    )
    if row is None:
        return json_response({"running_operation": None})
    return json_response({"running_operation": dict(row)})
```

Front-end `useGatewayReconnect` (§6.5) uses `useSWR` keyed on `topicId`, the fetcher is `fetch('/lca-api/topics/${topicId}/running-op')`. No tRPC; same `useSWR + fetch` pattern as `useFetchTopics`, `useFetchSessions`, etc.

#### 5.6.3 `POST /lca-api/runs/{run_id}/ws-token`

```python
@route("/v1/runs/{run_id}/ws-token", methods=("POST","OPTIONS"))
async def refresh_ws_token(request):
    user_id = request.state.user_id
    run_id = request.path_params["run_id"]
    # Verify the run is still owned by the user and the Redis stream exists.
    stream_exists = await redis.exists(f"agent_runtime_stream:{run_id}")
    if not stream_exists:
        return json_response({"error": "run not found or expired"}, status=404)
    token = sign_user_jwt(user_id=user_id, op=run_id, exp=now()+300)
    return json_response({"token": token})
```

The endpoint is `POST` (not `GET`) to avoid the JWT being cached by intermediate proxies. The front-end calls this when the WS receives `auth_expired`. The native `AgentStreamClient` already has a `refreshToken`-like callback; the new front-end wrapper calls it from there.

#### 5.6.4 Rejected: tRPC router

A tRPC router for these three new procedures (execAgent / refreshToken / getRunningOperation) was considered and rejected. The LobeHub-native `apps/server` tRPC layer is not available in the LCA gateway (Python), so a tRPC router would have to be either:

1. **A Python tRPC server** — no native reference, significant work, type safety gain limited.
2. **A LobeHub-side tRPC router proxying to the LCA gateway** — adds one round trip per call (browser → Next.js → LCA gateway), zero type safety over plain HTTP + `zod` at the call site, complicates auth (Next.js must mint its own JWT to call the LCA gateway).

The plain HTTP path is half the round trips, half the code, and matches the existing `/lca-api/runs` precedent. A future re-evaluation may revisit this, but it must be motivated by a real need (e.g. cross-server type safety), not a stylistic preference.

### 5.7 `lca_running_operations` table

DDL above (§3.2). Writes:

- `LcaAgentRuntimeCoordinator.start(run_id, ctx)` inserts a row with `run_id, topic_id, agent_id, scope, created_at, accepted_answer_keys=[]`.
- `LcaAgentRuntimeCoordinator.terminal(run_id)` deletes the row.
- `RunPort.resume_approval` appends the `idempotency_key` to `accepted_answer_keys` (single UPDATE; `jsonb` set union, atomic via SQL `||` operator).

Reads:

- `GET /lca-api/topics/{topic_id}/running-op` (`useGatewayReconnect` cross-refresh read source).
- `LcaAgentGateway._status_for(run_id)` indirectly via Redis key existence, **not** via the table.

The table is **not** a liveness source. A row exists only for runs that should be reconnectable. If a row exists but the Redis stream is gone, the row is stale; the next `useGatewayReconnect` deletes it.

## 6. Front-end changes (via the LCA patch mechanism)

**Hard constraint:** no direct edits under `lobehub-ui/`. All front-end changes are delivered as Python patch modules under `deploy/lobehub/patches/runtime/`, applied by `python3 deploy/lobehub/patch_lobehub.py apply`. The engine's `reconcile()` (see `deploy/lobehub/engine.py:21-37`) automatically restores any lobehub-ui file that was written by a now-deleted patch module — this is the deletion primitive P1 uses to retire the 4 broken-path TS files.

The current `lca_run_driver.py` patch module writes 17 files (5 new, 6 LCA-specific helpers, 1 generated `lcaWire.ts`, 1 `lcaToolRender/`, 4 lobehub-ui source modifications). P1 splits this into 3 modules with single responsibilities, deletes the 4 broken-path source modifications, and lets `reconcile()` restore the upstream sources.

### 6.1 Patch module split (one module per concern)

| New patch module | Category | Risk | Files | Notes |
|---|---|---|---|---|
| `lca_runtime_chat_persistence` | runtime | medium | 6 new + 1 generated | Replaces the persistence half of the current `lca_run_driver`. |
| `lca_runtime_agent_gateway` | runtime | high | 7 new + 3 modified | P1's main front-end delivery. |
| `lca_runtime_use_gateway_reconnect` | runtime | low | 1 modified | Cross-refresh reconnect hook. |
| **`lca_run_driver`** (existing) | runtime | high | (deleted) | The whole module is removed. `reconcile()` restores the 4 lobehub-ui source modifications, and the 5 LCA-only TS files (`LcaRunDriver.ts`, `lcaRunObserve.ts`, `lcaRunHil.ts`, `lcaJournal.ts`, `lcaRunCommand.ts`) disappear from `lobehub-ui/` because they were never in upstream. |

#### 6.1.1 `lca_runtime_chat_persistence`

Path: `deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py`

Files written (new in `lobehub-ui/`, copied from sibling `.ts` source files in the same directory):

```
src/store/chat/agents/transports/lcaChatRow.ts
src/store/chat/agents/transports/lcaPersist.ts
src/store/chat/agents/transports/lcaFinishChat.ts
src/store/chat/agents/transports/lcaError.ts
src/store/chat/agents/transports/lcaArtifacts.ts
src/store/chat/agents/transports/lcaWire.ts   (generated from WIRE table)
src/store/chat/agents/transports/lcaToolRender/contracts.generated.ts
```

`lcaWire.ts` is still generated by `render_wire_ts()` from `lca.plugins.transport.webserver.handlers.runs.wire.WIRE` (same as today; the generator function moves from `lca_run_driver.py` into this module). The generator runs at patch apply time so `lcaWire.ts` is always a build-time artefact of the LCA Python process; it is committed to `deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py`-generated output but never edited by hand.

No `verify_marker` is needed: this module only **creates** new files, never modifies lobehub-ui source.

#### 6.1.2 `lca_runtime_agent_gateway`

Path: `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py`

New files (copied from sibling `.ts` source files in the same directory):

```
src/store/chat/agents/transports/lcaGateway/connect.ts
src/store/chat/agents/transports/lcaGateway/execute.ts
src/store/chat/agents/transports/lcaGateway/reconnect.ts
src/store/chat/agents/transports/lcaGateway/event_handler.ts
src/store/chat/agents/transports/lcaGateway/event_router.ts
src/store/chat/agents/transports/lcaGateway/client.ts
src/store/chat/agents/transports/lcaGateway/interrupt.ts
src/store/chat/agents/transports/lcaGateway/types.ts
```

Each new file is a thin wrapper over its native `gateway/` counterpart; see §6.2 for the per-file mapping.

lobehub-ui source modifications (3 files, all using `replace_once` with explicit `verify_marker`):

| File | Anchor / marker | What changes |
|---|---|---|
| `src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts` | `/* LCA-P1: lcaGateway runtime mode */` | `selectRuntimeType` extended to return `'lcaGateway'` when `isLcaGatewayMode` is true. The marker is appended to the file in the same patch (one anchor per file). |
| `src/store/chat/slices/agentRun/actions/entries/conversationControl.ts` | `/* LCA-P1: skip-via-http */` and `/* LCA-P1: cancel-via-http */` | The current `lcaSkipState` / `lcaCancelState` `fetch /lca-api/runs/${runId}/answer` / `/cancel` code is **kept** (Q-Verify.1: HIL submission is plain HTTP, not WS — see §5.3.2). The marker is appended; the existing LCA fetch blocks are now both kept and recognized by the same marker. No code change in this file beyond the marker; the LCA patch re-affirms that the LCA HTTP submission path is the canonical one. |
| `src/store/chat/slices/agentRun/actions/entries/conversationLifecycle.ts` | `/* LCA-P1: lcaGateway send path */` | `sendMessage`'s `lcaGateway` branch added: `await this.#get().executeGatewayAgent(...)` (the same function `gateway.ts:executeGatewayAgent` defines, but bound to `lcaGatewayUrl`). |
| `src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts` | `/* LCA-P1: askUserQuestion handler */` | The current `handleLcaAskUserSubmit` (lines 138-198) is **kept verbatim** — this is the HIL submission path (Q-Verify.1). The patch module marks it with the marker; no code change. The native `findCustomInteractionSubmitHandler` lookup continues to find this handler for `lobe-user-interaction____askUserQuestion`. |
| `src/store/chat/agents/transports/lcaToolRender/renderers/lobe-user-interaction/askUserQuestion.tsx` | `/* LCA-P1: native askUserQuestion render */` | The current LCA renderer (lines 91-94 read `pluginState.lca.run_id`) is **kept** — `requestArgs.lca_run_id` continues to be written at HIL setup. The patch module marks the file; no code change. |

Each marker is a unique string `/* LCA-P1: <purpose> */` added by the same patch module; the marker is part of the inserted text, not a pre-existing anchor in the upstream source. This avoids the brittleness of "match against the upstream LobeHub source" anchors (which break on every upstream release).

#### 6.1.3 `lca_runtime_use_gateway_reconnect`

Path: `deploy/lobehub/patches/runtime/lca_runtime_use_gateway_reconnect.py`

lobehub-ui source modification (1 file):

| File | Anchor / marker | What changes |
|---|---|---|
| `src/hooks/useGatewayReconnect.ts` | `/* LCA-P1: read from lca_running_operations via plain HTTP */` | Replaces the `useSWR` fetcher with `fetch('/lca-api/topics/${topicId}/running-op')`. The fetcher's return shape is `{ run_id, topic_id, agent_id, assistant_message_id, scope, created_at }` (matches §5.6.2). |

#### 6.1.4 Deletion of `lca_run_driver`

Path: `deploy/lobehub/patches/runtime/lca_run_driver.py` is **deleted from disk**. The engine's `reconcile()` will:

- Notice the manifest entry for `lca_run_driver` no longer has a backing module.
- Restore every file the old `lca_run_driver` had written to its git HEAD content.
- The 5 LCA-only files (`LcaRunDriver.ts`, `lcaRunObserve.ts`, `lcaRunHil.ts`, `lcaJournal.ts`, `lcaRunCommand.ts`) had never been in upstream git, so they are simply **removed** from the working tree (the engine's restore path is a `git checkout -- <file>` for tracked files; for untracked files it is a `rm` — both are part of the engine's `orphan_restored` path).
- The 4 modified lobehub-ui sources (`streamingExecutor.ts`, `customInteractionHandlers.ts`, `intervention/index.tsx`, `conversationControl.ts`) are restored to their upstream content. `conversationControl.ts` is **re-modified by `lca_runtime_agent_gateway`** with a different `verify_marker` (`/* LCA-P1: skip-via-ws */`), so the final content of that file is the upstream content with LCA-P1's three inserted markers, **not** the pre-P1 LCA content.

`drift` must report zero unregistered edits in `lobehub-ui/` after `reconcile()`.

### 6.2 New `lcaGateway/` directory (deployed via `lca_runtime_agent_gateway`)

| File | Mirrors | Responsibility |
|---|---|---|
| `client.ts` | (no native equiv — wraps `AgentStreamClient`) | Sets `gatewayUrl` to LCA URL. |
| `connect.ts` | `gateway/connect.ts` | `connectToGateway({operationId, resumeOnConnect, token})` — direct re-export of native `connectToGateway` with a `agentGatewayUrl` sourced from `window.global_serverConfigStore.serverConfig.lcaGatewayUrl`. |
| `execute.ts` | `gateway/execute.ts` | `executeGatewayAgent` — calls `fetch('/lca-api/runs', POST)` to obtain `run_id` and `ws_token`, then `connectToGateway`. |
| `reconnect.ts` | `gateway/reconnect.ts` | `reconnectToGatewayOperation` — calls `fetch('/lca-api/topics/${topicId}/running-op')` to find the run, then `connectToGateway({ resumeOnConnect: true })`. |
| `event_handler.ts` | `gateway/gatewayEventHandler.ts` | Re-export of native `createGatewayEventHandler` with the `messageService.getMessages` URL pointed at the LCA `/v1/topics/.../messages` endpoint. |
| `event_router.ts` | `gateway/gatewayEventRouter.ts` | Direct re-export. |
| `interrupt.ts` | (small) | Re-export of native `interruptGatewayAgent` with the LCA operation id. |

### 6.3 `dispatch/agentDispatcher.ts` — new runtime mode

Add `lcaGateway` to the `AgentRuntimeType` union (currently `'client' | 'gateway' | 'hetero'`). Selection rule:

```ts
if (ctx.parentRuntime) return ctx.parentRuntime;
if (heterogeneousProvider) {
  // unchanged: 'hetero' or 'gateway' per executionTarget
}
if (isLcaGatewayMode) return 'lcaGateway';   // <-- NEW
if (isGatewayMode) return 'gateway';
return 'client';
```

`isLcaGatewayMode` is `true` when:
- the current process is LCA (booted with the LCA gateway URL configured), and
- the agent config does not set `disableGatewayMode: true`.

It wins over `gateway` because LCA users should not silently fall through to LobeHub cloud.

### 6.4 `serverConfigStore` — new field

`serverConfig.lcaGatewayUrl: string` and `serverConfig.lcaGatewayMessagesUrl: string`. Both populated at boot from `LCA_GATEWAY_PUBLIC_URL`. The messages URL is `lcaGatewayUrl` (same origin via Next.js rewrite).

### 6.5 Retirement (delete-when zero prod references)

The retirement is **mechanical**, not logical: when `lca_run_driver.py` is deleted from `deploy/lobehub/patches/runtime/`, the engine's `reconcile()` removes the 5 LCA-only TS files and restores the 4 lobehub-ui source modifications. The audit script (§10.3) enforces that no other patch module reintroduces the retired symbols.

| Symbol | Where it lived | What retires it |
|---|---|---|
| `lcaRunObserve.ts` | `deploy/lobehub/patches/runtime/lca_run_driver.py:30` | `reconcile()` deletes the file (never in upstream). |
| `lcaRunHil.ts` | `deploy/lobehub/patches/runtime/lca_run_driver.py:32` | same |
| `lcaJournal.ts` | `deploy/lobehub/patches/runtime/lca_run_driver.py:28` | same |
| `LcaRunDriver.ts` | `deploy/lobehub/patches/runtime/lca_run_driver.py:27` | same |
| `lcaRunCommand.ts` | `deploy/lobehub/patches/runtime/lca_run_driver.py:31` | same (the helper functions `lcaAuthHeaders`, `planeFieldsFromAgent`, `toWireMessages` are inlined into the new `lcaGateway/execute.ts` and `lcaChatRow.ts`; they were the only non-path parts of `lcaRunCommand.ts`). |
| `streamingExecutor.ts` (modification) | `deploy/lobehub/patches/runtime/lca_run_driver.py:35` | `reconcile()` restores upstream. The `LcaRunDriver` shortcut in `streamingExecutor.ts` is gone. |
| `customInteractionHandlers.ts` (modification) | `deploy/lobehub/patches/runtime/lca_run_driver.py:36` | **Kept in P1 by `lca_runtime_agent_gateway`** (§6.1.2). The LCA `handleLcaAskUserSubmit` is the HIL submission path; it is preserved under a new `/* LCA-P1: askUserQuestion handler */` marker. `reconcile()` would otherwise restore upstream and the HIL submit would have no handler. |
| `intervention/index.tsx` (modification) | `deploy/lobehub/patches/runtime/lca_run_driver.py:37` | same — restored to upstream. The `lca_runtime_agent_gateway` patch does not modify this file (the native component already routes HIL submission through the `findCustomInteractionSubmitHandler` lookup that `customInteractionHandlers.ts` registers against). |
| `askUserQuestion.tsx` (renderer) | not a lobehub-ui source — lives in `lcaToolRender/renderers/lobe-user-interaction/`. Currently a sibling `.ts` under `deploy/lobehub/patches/runtime/`. | **Kept in P1.** `lca_runtime_chat_persistence` ships the file unchanged. The `pluginState.lca.run_id` reader continues to work because `lcaRunHil.presentAskUserCard` continues to write the same pluginState shape. |
| `conversationControl.ts` (modification) | `deploy/lobehub/patches/runtime/lca_run_driver.py:38` | `reconcile()` restores upstream **then** `lca_runtime_agent_gateway` re-modifies it (P1's `/* LCA-P1: skip-via-ws */` etc. are different markers). |
| `LegacyRunDispatcher` | `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py` | full delete (`git rm`); the adapter is no longer wired. |
| `LCA_RUNTIME_FACADE` env flag | `lca/plugins/transport/webserver/...` references | the flag is removed; the new path is unconditional. |

The deletion gate is `scripts/audit_lca_legacy_path.py` (new, see [§10.3](#103-audit-script)): zero references anywhere in `apps/`, `lobehub-ui/src/`, `lobehub-ui/packages/`, `lca/`, or any non-archived test. The audit script also runs after every PR and on the nightly CI.

## 7. Wire protocol (Python mirror of native)

`lca/contracts/transport/gateway_messages.py`:

```python
from typing import Annotated, Literal, Union
from datetime import datetime

# ── Client → Server ───────────────────────────────────────────
class AuthMessage(BaseModel):
    type: Literal["auth"]
    token: str
    serverUrl: str | None = None
    tokenType: Literal["jwt", "apiKey"] | None = None

class ResumeMessage(BaseModel):
    type: Literal["resume"]
    lastEventId: str
    wantStatus: bool | None = None

class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"]

class InterruptMessage(BaseModel):
    type: Literal["interrupt"]

class ToolResultMessage(BaseModel):
    type: Literal["tool_result"]
    toolCallId: str
    success: bool
    content: str
    state: dict | None = None
    error: str | None = None

ClientMessage = Annotated[
    Union[AuthMessage, ResumeMessage, HeartbeatMessage,
          InterruptMessage, ToolResultMessage],
    Field(discriminator="type"),
]

# ── Server → Client ───────────────────────────────────────────
class AuthSuccess(BaseModel):
    type: Literal["auth_success"]
class AuthFailed(BaseModel):
    type: Literal["auth_failed"]
    reason: str
class AuthExpired(BaseModel):
    type: Literal["auth_expired"]
class HeartbeatAck(BaseModel):
    type: Literal["heartbeat_ack"]
class SessionComplete(BaseModel):
    type: Literal["session_complete"]
class ResumeComplete(BaseModel):
    type: Literal["resume_complete"]
    status: Literal["running","waiting_input","waiting_confirmation",
                    "completed","error","interrupted"]

class AgentEvent(BaseModel):
    type: Literal["agent_event"]
    id: str | None = None
    event: dict  # AgentStreamEvent — see 5.3

ServerMessage = Annotated[
    Union[AuthSuccess, AuthFailed, AuthExpired, HeartbeatAck,
          AgentEvent, SessionComplete, ResumeComplete],
    Field(discriminator="type"),
]
```

The 18 `AgentStreamEvent` types (mirror of `@lobechat/agent-gateway-client/src/types.ts:1-54`) live in `lca/contracts/transport/agent_stream_event.py`. The mirror is **byte-compatible with the client**; the same JSON serialised by Python deserialises into the TS union without coercion.

The `importlinter` contract layer purity rule already excludes `lca.infrastructure`, `lca.plugins`, `lca.cognition` from `lca.contracts` (`pyproject.toml`). The new `lca/contracts/transport/` module obeys the same rule — it imports only `pydantic` + standard library.

## 8. Failure / retry / recovery

| Scenario | How it's handled | Why it works |
|---|---|---|
| Network drop mid-run | Native `AgentStreamClient` auto-reconnect, exponential backoff 1 s → 30 s, 3 missed heartbeats force reconnect, then `resume` with `lastEventId` (test 2). | Unchanged; the protocol is identical. |
| LCA gateway process kill | Redis Stream survives (TTL 2 h); on restart, the same `LcaStreamEventManager` instance reads from the same key (test 4). | Single Redis instance, native `LcaStreamEventManager` keys. |
| Gateway restart during an active reconnect | `useGatewayReconnect` reads the table, calls `connectToGateway` with `resumeOnConnect: true`; the WS path's `resume_complete` returns `running` or terminal, and the client renders accordingly (test 3). | `resume_complete` is the authoritative status; the client never guesses. |
| Approval / HIL cross-refresh | `step_start { requiresApproval: true }` is durable in the stream. On reconnect, `useGatewayReconnect` reads the table, replays the stream, `resume_complete { status: 'waiting_input' }` triggers the client to re-render the card from the latest `step_start.data.pendingToolsCalling`. User clicks Approve → `POST /answer` → `accepted_answer_keys` persists, the WS resumes on the same connection (test 5). | Stream is the source of truth; idempotency is in the table. |
| Idempotent resume replay | `accepted_answer_keys` is now persisted (jsonb) and survives restart. The `RunPort.resume_approval` no longer needs to consult in-process state (test 5b). | Single UPDATE per call, atomic. |
| Stale `runningOperation` row | `useGatewayReconnect` checks Redis `EXISTS agent_runtime_stream:{run_id}`. If absent, the row is deleted and no reconnect is attempted. | Redis is the liveness source. |
| `auth_expired` during a long run | Client calls `POST /lca-api/runs/{run_id}/ws-token` (plain HTTP). The new JWT rides back in the response. Client then `updateToken()` + `reconnect()`. | Mirror of native `auth_expired` path. |
| `auth_failed` (op no longer exists) | LCA's WS handler returns `auth_failed` once; the client treats it as terminal (no auto-reconnect); the `lca_running_operations` row is deleted on the next `useGatewayReconnect` if present. | Same as native. |
| 7 broken paths from §1 | Each maps to a fix in 5.2 / 5.3 / 5.4 / 5.7; see comments inline. | Native-equivalent guarantees. |

## 9. Acceptance

The acceptance suite has three layers — L1 (unit) is the existing test corpus; L2 (in-process node contract) and L3 (real-kernel end-to-end flow) are **new and hard-required for P1**. L4 (1 h stability smoke) is the final gate. The browser is **not** used: the front-end TS code paths are exercised through a Python harness that drives the same HTTP + WebSocket wire the browser would, against a real LCA kernel.

### 9.1 L2 — In-process node contract (8 cases, fast)

Run in-process via `starlette.testclient.TestClient` + a real Redis (the dev `127.0.0.1:6379` from `lca-ops.yaml:42`). Each test exercises a single wire node; the LCA kernel is loaded in-process via the same fixtures that `tests/lca_plugins/transport/webserver/test_runs_sessions.py` uses today.

| # | Wire node | Pass criteria | Test file |
|---|---|---|---|
| L2-1 | WebSocket upgrade + auth | `101 Switching Protocols`; `auth_success` on a valid JWT; `auth_failed` on a malformed one; `auth_expired` on an expired token. | `tests/integration/p1/test_lca_p1_node_01_ws_handshake.py` |
| L2-2 | Resume replay | After `auth_success`, send `resume { lastEventId: '0', wantStatus: true }`; assert all prior events arrive in order; `resume_complete.status` matches the run's actual status. | `tests/integration/p1/test_lca_p1_node_02_resume.py` |
| L2-3 | Heartbeat | Send 5 `heartbeat` frames at 30 s intervals (or 1 s intervals in test); assert 5 `heartbeat_ack` frames arrive. | `tests/integration/p1/test_lca_p1_node_03_heartbeat.py` |
| L2-4 | Interrupt | Send `interrupt`; assert the run's `session.status` becomes `CANCELED` and `agent_runtime_end { reason: 'interrupted' }` is published. | `tests/integration/p1/test_lca_p1_node_04_interrupt.py` |
| L2-5 | `tool_result` → `resume_approval` | Send `tool_result` after `step_start { requiresApproval: true }`; assert `RunPort.resume_approval` is called with the same `(approval_id, payload, idempotency_key)`; replay with the same `idempotency_key` returns 200 without re-running. | `tests/integration/p1/test_lca_p1_node_05_tool_result.py` |
| L2-6 | Redis Stream key shape | After publishing 1 event, `XLEN agent_runtime_stream:<run_id> == 1`; `TTL > 7100`; `XADD MAXLEN ~ 1000` triggers trim. | `tests/integration/p1/test_lca_p1_node_06_redis_shape.py` |
| L2-7 | `GET /lca-api/topics/{topic_id}/running-op` | Insert a row in `lca_running_operations`; assert the endpoint returns it; assert missing-topic returns `{running_operation: null}`. | `tests/integration/p1/test_lca_p1_node_07_running_op.py` |
| L2-8 | `POST /lca-api/runs/{run_id}/ws-token` | After a `auth_expired`, the endpoint mints a new JWT; the new token is accepted by the next WS connect. | `tests/integration/p1/test_lca_p1_node_08_ws_token.py` |

L2-1 through L2-8 are gate-checks for the wire protocol. They are fast (each < 1 s) and run in CI on every PR.

### 9.2 L3 — Real-kernel end-to-end flow (7 cases, real LCA kernel)

Run against a **real LCA kernel** started by the test fixture (subprocess: `uv run python -m lca_kernel serve --profile test-p1 --port 9876`). The front-end TS code paths are exercised through `tests/e2e/p1/_lca_gateway_client.py` — a Python harness that **implements the same HTTP + WebSocket wire** the patched `lcaGateway/*` TS would issue. The harness is byte-compat with the wire (verified by L2-7 / L2-8 + 9.3 below) and is the source of truth for what the front-end is allowed to assume.

The harness models the **flowing real scenario**, not the wire node: each test simulates a user, drives the LCA gateway end-to-end through HTTP and WebSocket, and asserts the events that should arrive and the side effects that should land in the DB. No mocks; no `monkeypatch`; no `MagicMock`; the kernel is a real Python process.

| # | Real scenario | Flowing path (LCA-gateway perspective) | Pass criteria | Test file |
|---|---|---|---|---|
| L3-1 | User asks "订明天去北京的机票,选国航" — single round with tool + HIL | POST /lca-api/runs → WS connect → auth_success → resume_complete{running} → events: agent_runtime_init → stream_start → stream_chunk{reasoning} → stream_chunk{tools_calling} → tool_start → step_start{requiresApproval: true, pendingToolsCalling:[…]} → agent_runtime_end{waiting_for_human} → session_complete (client side closes); POST /lca-api/runs/{id}/answer → WS reconnect → events: step_start → tool_end → stream_chunk{text} → agent_runtime_end{completed} → session_complete. | All events arrive in order, no duplicates; `run_id` and `tool_call_id` stable across reconnects; assistant message lands in DB. | `tests/e2e/p1/test_lca_p1_01_user_books_flight.py` |
| L3-2 | User asks "查询 X" while wifi flickers (30 s drop) | POST /lca-api/runs → WS open → 5 events arrive → kernel-level `iptables -A INPUT -p tcp --dport 9876 -j DROP` for 30 s (or, in dev, `kill -STOP <pid>` of the kernel); resume drops; kernel SIGCONT; the LCA `AgentStreamClient` Python harness auto-reconnects, sends `resume { lastEventId, wantStatus: true }`; the events emitted during the stop period arrive in order. | The `lastEventId` after reconnect is **strictly greater** than the last seen `lastEventId` before the drop; no event from the drop period is duplicated. | `tests/e2e/p1/test_lca_p1_02_wifi_drop.py` |
| L3-3 | User hits F5 during a long run (kernel survives) | POST /lca-api/runs → 10 events stream → harness simulates a page refresh: drop the WS, `fetch GET /lca-api/topics/{topic_id}/running-op` → returns the run; `connectToGateway({ resumeOnConnect: true })` → events 11..20 arrive; `resume_complete { status: 'running' }`. | No event loss; the new WS sees every event from the original WS, deduped by `id`. | `tests/e2e/p1/test_lca_p1_03_page_refresh.py` |
| L3-4 | User kills the LCA kernel mid-run, kernel restarts (Redis survives) | POST /lca-api/runs → 5 events stream → `kill -9` the kernel; restart; new kernel's `LcaStreamEventManager` reads the same Redis key; the harness reconnects (with `resumeOnConnect: true`); events 6..N arrive from the surviving Redis Stream. | All events present after restart; `lca_running_operations` row remains (kernel restart does not clear it). | `tests/e2e/p1/test_lca_p1_04_kernel_restart.py` |
| L3-5 | User closes the browser tab while in HIL, reopens, submits answer | Trigger L3-1 up to `agent_runtime_end{waiting_for_human}`; harness simulates tab close: drop WS; `fetch GET /lca-api/topics/{topic_id}/running-op` → returns the run; `connectToGateway` reconnects → `resume_complete { status: 'waiting_input' }` (the L3-1 waiting_human state is preserved); `POST /lca-api/runs/{id}/answer` with the same `idempotency_key` twice in a row → second call returns 200 (replayed) without re-executing. | `accepted_answer_keys` table reflects the key; `agent_runtime_end` after resume has `reason='completed'`. | `tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py` |
| L3-6 | User leaves the agent running for 6 minutes (token expiry boundary) | POST /lca-api/runs → events stream for 5 min; the WS receives `auth_expired` (token TTL = 5 min); harness calls `POST /lca-api/runs/{id}/ws-token` → new token; harness calls `updateToken(new) + reconnect()`; the rest of the events arrive. | `auth_expired` fires within 30 s of token expiry; reconnect succeeds; events 6..N are not duplicated. | `tests/e2e/p1/test_lca_p1_06_token_expiry.py` |
| L3-7 | LLM provider returns 500 mid-step | POST /lca-api/runs with a stub LLM provider that returns 500 on the first 2 calls and 200 on the 3rd; assert the client sees `stream_retry` events (≥ 1) and ultimately `agent_runtime_end{completed}`. | `stream_retry` events emitted; final `agent_runtime_end{completed}` (not `error`); assistant text matches the 3rd-attempt LLM response. | `tests/e2e/p1/test_lca_p1_07_llm_retry.py` |

L3-1 through L3-7 are the **flowing end-to-end acceptance** for P1. They run against a real kernel + real Redis + real front-end wire; they are slow (each 5–60 s) and run on the `e2e` CI job before merge.

### 9.3 Front-end wire harness — the bridge between Python tests and TS code

`tests/e2e/p1/_lca_gateway_client.py` is a **Python implementation of the same wire that `lcaGateway/*` (TS) drives**. The two implementations must stay byte-compat; this is enforced by:

- L2-1 / L2-2 / L2-3 / L2-4 / L2-5 — these exercise the LCA side; the Python harness is the consumer and the assertions are the same as the TS client would make.
- A separate `tests/e2e/p1/test_lca_p1_wire_harness_parity.py` runs both the Python harness **and** a Node script that `require`s the actual `lcaGateway/connect.ts` + `lcaGateway/execute.ts` from the patched `lobehub-ui/` and drives the same scenario; both must produce the same event stream. This test runs on CI **only after** the patch has been applied (`python3 deploy/lobehub/patch_lobehub.py apply`) — the cost is bounded by the harness's < 10 s runtime.

This is the closest we get to "the actual TS code runs" without booting a headless browser. It catches the 90% of TS bugs that are wire-shape errors (wrong field name, wrong order, wrong message type) and keeps the suite fast and deterministic.

### 9.4 L4 — 1 h stability smoke

| # | Scenario | Pass criteria | Test file |
|---|---|---|---|
| L4-1 | 1 h flowing run with periodic HIL, cross-refresh, token refresh | A 1 h run that completes N tool calls, hits HIL twice, refreshes the page once, crosses the token boundary once. Assert at the end: every `agent_runtime_end` has a matching `step_start`; `lca_running_operations` is empty (the run is `done`); no `agent_runtime_stream:*` key has unexpected size; no events duplicated. | `tests/e2e/p1/test_lca_p1_99_stability.py` (1 h) |

L4 runs nightly, not on every PR. It is the final gate before P1 ships.

### 9.5 Manual gate

One real end-to-end human session, single round + HIL, on the LCA boot path, with a real LLM provider. This is not in the suite; the operator runs it manually as the last step.

## 10. Deletion / migration

### 10.1 Files deleted at PR-merge

**Back-end (full delete, `git rm`):**

- `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py:144-168` — `stream_run_live` removed.
- `lca/plugins/transport/run_ui_encoder__encoder_provider.py` — full delete; the 4-event encoder has no equivalent in the new design.
- `lca/plugins/transport/run_live_observe__seam.py` — full delete; superseded by the `LcaAgentRuntimeCoordinator` / `LcaAgentGateway` pair.
- `lca/plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py` — full delete; `RegistryRunAdapter` no longer wraps the live stream (commands and queries split explicitly).
- `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py` — full delete; `LegacyRunDispatcher` is replaced by the new `LcaAgentRuntimeCoordinator`.

**Front-end (delete via patch engine `reconcile()`):**

- `lobehub-ui/src/store/chat/agents/transports/lcaRunObserve.ts`, `lcaRunHil.ts`, `lcaJournal.ts`, `LcaRunDriver.ts`, `lcaRunCommand.ts` — these are **never in upstream git**; when `lca_run_driver.py` is removed and `reconcile()` runs, the engine restores the working tree to upstream HEAD, which **removes** these files (they were only present as orphan writes).
- `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/client/streamingExecutor.ts` — the LCA shortcut `LcaRunDriver.runLcaJournal` is removed; `reconcile()` restores upstream. The new path goes through `lcaGateway/connect.ts`.
- `lobehub-ui/src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/customInteractionHandlers.ts` — LCA `fetch /lca-api/runs/.../answer` / `.../cancel` branches are removed; `reconcile()` restores upstream. The new path goes through `lcaGateway/interrupt.ts` and `lcaGateway/reconnect.ts`'s `sendToolResult`.
- `lobehub-ui/src/features/Conversation/Messages/AssistantGroup/Tool/Detail/Intervention/index.tsx` — restored to upstream.
- `lobehub-ui/src/store/chat/slices/agentRun/actions/entries/conversationControl.ts` — `reconcile()` first restores to upstream, **then** `lca_runtime_agent_gateway` re-modifies it (P1's `/* LCA-P1: skip-via-ws */` and `/* LCA-P1: cancel-via-ws */` markers).

**Patch source (delete from disk):**

- `deploy/lobehub/patches/runtime/lca_run_driver.py` — full delete.

### 10.2 Files changed

- `lca/application/runtime/default_facade.py` — `DefaultRuntimeFacade.dispatch_run` rewritten to call `RunPort.create_and_dispatch` + `LcaAgentRuntimeCoordinator.start(run_id)` + `lca_running_operations` insert. The `LCA_RUNTIME_FACADE` env flag is removed; the new path is unconditional.
- `lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py` — `RouteSpec("/runs/{run_id}/live", stream_run_live, …)` removed; replaced by `RouteSpec("/v1/runs/{run_id}/ws", LcaAgentGateway, ("GET",))`, `RouteSpec("/v1/runs/{run_id}/ws-token", refresh_ws_token, ("POST",))`, and `RouteSpec("/v1/topics/{topic_id}/running-op", get_running_operation, ("GET","OPTIONS"))`.
- `lobehub-ui/next.config.ts` — unchanged (the existing `/lca-api/:path*` catch-all already covers `/lca-api/v1/...`; spike 1 confirmed).
- `lobehub-ui/src/store/chat/slices/agentRun/actions/dispatch/agentDispatcher.ts` — `selectRuntimeType` extended with `lcaGateway` mode (modified by `lca_runtime_agent_gateway` patch).
- `lobehub-ui/src/store/chat/slices/agentRun/actions/entries/conversationLifecycle.ts` — `sendMessage` gets a `lcaGateway` branch (modified by `lca_runtime_agent_gateway` patch).
- `lobehub-ui/src/store/chat/slices/agentRun/actions/entries/conversationControl.ts` — `lcaSkipState` / `lcaCancelState` deleted; `lcaGateway.interruptGateway(...)` and `lcaGateway.sendToolResult(...)` substituted (modified by `lca_runtime_agent_gateway` patch).
- `lobehub-ui/src/hooks/useGatewayReconnect.ts` — replaced to read `lca_running_operations` via plain HTTP (modified by `lca_runtime_use_gateway_reconnect` patch).

### 10.3 Audit script

`scripts/audit_lca_legacy_path.py`:

- Args: `--paths lca/plugins lca/application lca/infrastructure lca/contracts lobehub-ui/src lobehub-ui/apps`.
- For each legacy symbol (`stream_run_live`, `RunUiEncoder`, `LiveRunProjection._process_item`, `LIVE_MAX_RECONNECTS`, `legacy_dispatcher_adapter.LegacyRunDispatcher`, `lcaRunObserve`, `lcaRunHil`, `lcaJournal`, `LCA_RUNTIME_FACADE`), search for its name in the source.
- Exit non-zero if any non-archived test file or production path references it.
- The legacy symbols are listed in `scripts/audit_lca_legacy_path.json` (a flat list; reviewed each release).
- Wired into CI as `audit-lca-legacy-path` step.

### 10.4 Migration

- No on-the-wire backward compatibility. The 4-event SSE endpoint and `/lca-api/runs/{id}/live` both return 410 Gone with a clear message starting at the cutover tag. The PR is the cutover tag.
- The 4-event SSE endpoint and `/lca-api/runs/{id}/live` are kept behind a 410-only path for one minor version, then removed.

## 11. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | `EventTranslator` mis-folds a `StampedEvent` and emits a malformed `AgentStreamEvent`; client crashes on parse. | Medium | High (every step) | 5.3 + 5.7 enforce **byte-compat with native**; one protocol-parity e2e (#7) runs the full 18-type matrix; a unit test for every foldable event. |
| 2 | `LcaStreamEventManager` writes 10 MB+ in a single XADD (native has the same risk; documented in `StreamEventManager.ts:48-70`). | Low | High (single XADD rejects) | Mirror native `stripFinalStateInEventData` (don't store `messages` / `tools` in events); cap `data` size at 1 MB per event with a synthetic truncation marker. |
| 3 | JWT private key leakage | Low | High | Env var, not file; rotate via `LCA_JWT_SECRET`; old tokens remain valid until `exp` (≤ 5 min). |
| 4 | Redis OOM from `agent_runtime_stream:*` | Low | Medium | `EXPIRE 7200` on every XADD + `MAXLEN ~1000` is exactly what native uses; load-test shows ~50 MB / 100 runs. |
| 5 | Coordinator watchdog §5.2 fires prematurely | Low | Medium (false terminal) | Watchdog is gated on `session.status in STREAM_END_STATUSES` AND journal fold; double-emit protection: if a real `SpineClose` arrives within 100 ms after the synthetic `agent_runtime_end`, the synthetic is dropped (it is the loser's responsibility to drop). |
| 6 | `useGatewayReconnect` reads the table during a hot topic and triggers a reconnect while the live WS is still healthy. | Low | Medium (UI flicker) | The native hook already guards on `status === 'disconnected'` (`useGatewayReconnect.ts:50-55`); same guard is reused. |
| 7 | LCA `accepted_answer_keys` jsonb becomes a 10 MB array over a long run. | Low | Low | One row per run; jsonb is indexed for the idempotency check; if a single run's keys exceed 1 MB, the table write becomes a perf concern (mitigation: cap to 1000 most-recent keys, drop older). |
| 8 | `LcaAgentGateway` WS server leaks connections under load. | Low | High | Starlette's WebSocketRoute is bounded by `uvicorn --workers * --backlog`; LcaAgentGateway uses a `ConnectionTracker` that caps at 1024 open WS per gateway process; over-cap → 503 reject. |

## 12. Implementation order (sequenced PRs)

The five PRs are **strictly sequential** (each requires the previous one green). Each PR is independently revertable; the engine's `reconcile()` is the rollback primitive — to revert a PR, `git revert` the patch module's commits and re-run `reconcile()`.

1. **PR-1: contract + manager** (no observable change, dev only)
   - Add `lca/contracts/transport/{gateway_messages,agent_stream_event,stream_keys}.py`.
   - Add `lca/infrastructure/observability/stream/stream_event_manager.py`.
   - **Tests added in this PR:**
     - `lca/infrastructure/observability/stream/tests/test_stream_event_manager.py` (unit, L1).
     - `tests/contracts/transport/test_protocol_parity.py` (Python types ↔ native TS types roundtrip, L1).
   - Migration: none. Front-end: none.
2. **PR-2: back-end WS server + broadcaster** (dev only, `/runs/{id}/live` still works in parallel)
   - Add `LcaAgentRuntimeCoordinator`, `EventTranslator`, `LcaAgentGateway`.
   - Add `routes_2/routes_runs_sessions.py` WS route (mounted at `/v1/runs/{run_id}/ws`); keep `/runs/{run_id}/live` SSE in parallel so the legacy front-end still works during PR-2 / PR-3.
   - Add `lca_running_operations` migration.
   - **Tests added in this PR:**
     - `lca/application/runtime/coordinator/tests/test_event_translator.py` (one test per foldable event, L1).
     - `lca/plugins/transport/webserver/handlers/runs/terminal/streaming/tests/test_lca_agent_gateway.py` (L2 single-node).
     - **L2-1** `tests/integration/p1/test_lca_p1_node_01_ws_handshake.py` (auth_success / auth_failed / auth_expired).
     - **L2-3** `tests/integration/p1/test_lca_p1_node_03_heartbeat.py`.
     - **L2-4** `tests/integration/p1/test_lca_p1_node_04_interrupt.py`.
     - **L2-6** `tests/integration/p1/test_lca_p1_node_06_redis_shape.py`.
   - Migration: `/v1/runs/{run_id}/ws` is now a parallel path; `/runs/{id}/live` SSE still works.
3. **PR-3: front-end switchover via new patch modules**
   - Add `deploy/lobehub/patches/runtime/lca_runtime_chat_persistence.py` (replaces the persistence half of `lca_run_driver`).
   - Add `deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py` (8 new TS files + 3 source modifications).
   - Add `deploy/lobehub/patches/runtime/lca_runtime_use_gateway_reconnect.py` (1 source modification).
   - Add the three plain-HTTP endpoints (`POST /lca-api/runs`, `GET /lca-api/topics/{id}/running-op`, `POST /lca-api/runs/{id}/ws-token`); add `lcaGatewayUrl` to `serverConfigStore`.
   - **Tests added in this PR:**
     - `tests/e2e/p1/_lca_gateway_client.py` (the Python wire harness — the bridge between tests and TS).
     - **L2-2** `tests/integration/p1/test_lca_p1_node_02_resume.py`.
     - **L2-5** `tests/integration/p1/test_lca_p1_node_05_tool_result.py`.
     - **L2-7** `tests/integration/p1/test_lca_p1_node_07_running_op.py`.
     - **L2-8** `tests/integration/p1/test_lca_p1_node_08_ws_token.py`.
     - **L3-1** through **L3-7** the 7 real-kernel flowing scenarios in `tests/e2e/p1/`.
     - `tests/e2e/p1/test_lca_p1_wire_harness_parity.py` (the Node-vs-Python harness parity check, runs only after `python3 deploy/lobehub/patch_lobehub.py apply`).
4. **PR-4: retirement** (delete-when verified, uses the patch engine as the deletion primitive)
   - `git rm` `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py:144-168` (`stream_run_live`).
   - `git rm` `lca/plugins/transport/run_ui_encoder__encoder_provider.py`.
   - `git rm` `lca/plugins/transport/run_live_observe__seam.py`.
   - `git rm` `lca/plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py`.
   - `git rm` `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py`.
   - `git rm` `deploy/lobehub/patches/runtime/lca_run_driver.py`.
   - Run `python3 deploy/lobehub/patch_lobehub.py apply` once; `reconcile()` restores the 4 lobehub-ui source modifications and removes the 5 LCA-only TS files.
   - `routes_2/routes_runs_sessions.py` returns 410 for `/runs/{run_id}/live`.
   - **Tests added in this PR:**
     - `scripts/audit_lca_legacy_path.py` — exits 0 in CI.
     - All L2 + L3 tests must remain green after retirement (proves the new path is fully standalone).
5. **PR-5: stability smoke + protocol parity** (last gate)
   - **Tests added in this PR:**
     - **L4-1** `tests/e2e/p1/test_lca_p1_99_stability.py` (1 h nightly).
   - Run the 1 h smoke; record artefacts in `traces/lca-p1-smoke/`.

## 13. Out of scope (P2 / P3)

P1 is the "transmit and recover" layer. P2 / P3 are deliberately excluded from this spec and tracked separately:

- **P2 — multi-tab / multi-device demultiplex.** Mirror native `GatewayStreamNotifier`: a single op's events are fanned out across all WS connections for the same `topic_id`. Multiple browser tabs share a single live view. Group / sub-agent orchestration across the WS channel. Cursor-rewind on a hibernated run. Tracked under a future ADR.
- **P3 — multi-instance, zero-downtime.** `LcaStreamEventManager` already supports multi-instance (Redis-shared), but the in-process watchdog §5.2 needs a Redis-backed distributed lock to be safe across >1 gateway process. The current single-instance deployment is sufficient for P1.
- **Native `StreamEventManager` upstream changes.** When lobehub adds a new `AgentStreamEvent` type, we mirror it in `lca/contracts/transport/agent_stream_event.py`; the parity test #7 catches drift.

## 14. References

### 14.1 Native sources (read while writing this spec)

- `lobehub-ui/packages/agent-gateway-client/src/types.ts` — wire types (18 `AgentStreamEvent`s, 5 `ClientMessage`s, 7 `ServerMessage`s).
- `lobehub-ui/packages/agent-gateway-client/src/client.ts` — client lifecycle, heartbeat, reconnect, resume-mode buffering.
- `lobehub-ui/apps/server/src/modules/AgentRuntime/StreamEventManager.ts` — Redis XADD/EXPIRE/XREAD semantics.
- `lobehub-ui/apps/server/src/modules/AgentRuntime/AgentRuntimeCoordinator.ts` — `STREAM_END_STATUSES`, terminal-hint resolution, `stripFinalStateInEventData`.
- `lobehub-ui/apps/server/src/services/agentRuntime/AgentRuntimeService.ts` — `step_start` publication (L870), `agent_runtime_end` reason (L2359), `executeStep` lock.
- `lobehub-ui/apps/server/src/services/agentRuntime/HumanInterventionHandler.ts` — approve / reject / reject-continue / halt semantics.
- `lobehub-ui/packages/trpc/src/utils/internalJwt.ts` — `signUserJWT` (RS256, 5 min).
- `lobehub-ui/apps/server/src/routers/lambda/aiAgent.ts:1947-1962` — `refreshGatewayToken` procedure.
- `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gateway.ts` — `connectToGateway`, `executeGatewayAgent`, `reconnectToGatewayOperation`.
- `lobehub-ui/src/store/chat/slices/agentRun/actions/transports/gateway/gatewayEventHandler.ts` — 18 `agent_event` dispatch sites.
- `lobehub-ui/src/hooks/useGatewayReconnect.ts` — page-refresh reconnect.

### 14.2 LCA sources (read while writing this spec)

- `lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py` — `create_run`, `answer_run`.
- `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` — `stream_run_live`, `_parse_after`.
- `lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py` — `create_and_dispatch`, `resume_approval`, `cancel`.
- `lca/plugins/transport/webserver/handlers/runs/terminal/legacy/adapter.py` — `RegistryRunAdapter`.
- `lca/plugins/transport/webserver/handlers/runs/api/legacy_dispatcher_adapter.py` — `LegacyRunDispatcher`.
- `lca/plugins/transport/run_ui_encoder__encoder_provider.py` — 4-event encoder (deleted in P1).
- `lca/plugins/transport/run_live_observe__seam.py` — observer seam (deleted in P1).
- `lca/plugins/transport/webserver/handlers/runs/terminal/status/status.py` — terminal-hint resolution.
- `lca/infrastructure/observability/journal/stream/live_tail.py` — `LiveTail` ring buffer.
- `lca/infrastructure/observability/spine/derivers/live/tail.py` — `LiveTailDeriver._to_stamped`.
- `lca/application/runtime/default_facade.py` — `DefaultRuntimeFacade` (changed in P1).
- `lca/contracts/runtime/facade.py` — `RuntimeFacade` Protocol.
- `lca/plugins/observability/run/ledger_seam.py` — `LiveTail()` construction.
- `lobehub-ui/src/store/chat/agents/transports/{LcaRunDriver,lcaRunCommand,lcaRunObserve,lcaRunHil,lcaJournal}.ts` — front-end (deleted in P1).
- `lobehub-ui/src/store/chat/slices/agentRun/actions/entries/conversationControl.ts` — `lcaSkipState` / `lcaCancelState` (changed in P1).
- `lobehub-ui/src/store/chat/agents/transports/lcaToolRender/renderers/lobe-user-interaction/askUserQuestion.tsx` — `approval_id: toolCallId` (changed in P1).
- `lobehub-ui/next.config.ts:43-49` — `/lca-api/:path*` rewrite (unchanged in P1; spike 1 confirmed).
- `lca/infrastructure/cli/guide/guide.py:114-136` — `/lca-api/runs` rewrite documentation.

### 14.3 Spike results

- **Spike 1 — Next.js 16 `rewrites()` WebSocket upgrade**: `HTTP/1.1 101 Switching Protocols` confirmed on `ws://127.0.0.1:3011/lca-api/ws → ws://127.0.0.1:8766/ws` (echo). Backend headers (Python `websockets/15.0.1`) preserved. **Conclusion:** existing `rewrites()` rule is sufficient; no Next.js config change required.
- **Spike 2 — Native WS protocol**: 5 `ClientMessage` + 7 `ServerMessage` + 18 `AgentStreamEvent` types, all defined at `packages/agent-gateway-client/src/types.ts`. JWT auth (RS256, 5 min) is the canonical pattern; `auth_expired` is recoverable, `auth_failed` is terminal. Redis Stream uses key `agent_runtime_stream:<operationId>`, `MAXLEN ~ 1000`, `EXPIRE 7200`. Heartbeat 30 s, 3 missed → reconnect, backoff 1 s → 30 s. **Conclusion:** Python mirror is byte-compatible.
- **Spike 3 — LCA current call chain**: 5 broken paths documented (4 of them in this spec's §1). All map to fixes in §5.2-5.4. **`approved_answer_keys` is process-local** — main blocker for HIL correctness across restarts; this spec persists it in `lca_running_operations` jsonb.

## 15. Brainstorm decisions

| Q | Answer | Why |
|---|---|---|
| Q1 | 4-layer separation (fact / projection / transport / session) | The current 4-event encoder blurs projection and transport; the §1 broken paths are direct consequences. |
| Q2 | 11 (actually 18) `AgentStreamEvent` types, 1:1 mirror | Reusing native `gatewayEventHandler` requires byte-compat. |
| Q3.A | WebSocket | Native `AgentStreamClient` is the most-tested transport; SSE cannot carry `sendToolResult`. |
| Q3.B | Native JWT (RS256, 5 min) + `auth_expired` + `refreshToken` | The only option that gives "perfect alignment with native". |
| Q-Spec.1 | Plain HTTP, no tRPC | LCA's gateway is a Python process; tRPC in Next.js would be one extra hop with no type-safety gain over `fetch` + `zod`. |
| Q-Spec.2 | Use the engine's `reconcile()` as the deletion primitive | The manifest already tracks which files each patch wrote; deleting a patch module restores the working tree to upstream HEAD. This is the canonical long-term-maintainable way to delete lobehub-ui modifications — no "empty-import" tricks, no "delete_file" engine extension. |
| Q-Spec.3 | All new TS sources live under `deploy/lobehub/patches/runtime/` as sibling `.ts` files; the `.py` patch module copies them via `ctx.write()` | Matches the existing LCA pattern (`lcaChatRow.ts` is already written this way); zero new mechanism. |
| Q-Spec.4 | 4-layer acceptance: L1 unit (existing) → L2 in-process node contract → L3 real-kernel flowing e2e → L4 1 h stability smoke. Front-end wire exercised by a Python harness that mirrors the patched `lcaGateway/*` TS, plus a Node-side wire-harness parity test that runs the actual TS after `patch_lobehub.py apply`. **No headless browser**: too slow, too flaky, can be replaced by the Python + Node harness at 1/10 the runtime. | The user-stated requirement "前端 ts 真的发起 + 后端真的接收 + 真实场景" is satisfied: the Python harness is wire-byte-compat with the TS; the parity test catches any drift; L3 covers the flowing user scenarios (订机票 / wifi drop / F5 / kernel kill / cross-tab HIL / token expiry / LLM retry). |
| Q-Verify.1 | HIL submission stays on plain HTTP (`POST /lca-api/runs/{run_id}/answer`), wired through the native `CustomInteractionSubmitHandler` hook in `customInteractionHandlers.ts`. WS `sendToolResult` is **only** for client-execute tools (e.g. local-device control). | Native itself does the same: `HumanInterventionHandler` accepts HIL answers through the run's resume path (plain HTTP), not the WS. Mirroring native means we keep `/answer` and `/cancel`, not invent a new WS message. The LCA `lca_runtime_agent_gateway` patch keeps `handleLcaAskUserSubmit` and `lcaSkipState` / `lcaCancelState` as-is, with new markers. |
| Q-Verify.2 | The `tool_end` WS event does **not** carry `projected_state`. The server-side `LcaAgentRuntimeCoordinator` writes the `projected_state` into the tool message's `pluginState` DB column **before** publishing `tool_end`. The front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages` reads the already-populated row, and LCA's `lcaToolRender/*` renderers read the populated `pluginState`. | This is exactly what native does (`packages/context-engine/src/processors/MessageContent.ts:465-467`); the spec was missing the explicit LCA-side rule, which was the source of the apparent "pluginState 数据源缺失" risk. §5.3.1 codifies the rule. |
| Q4.A | 1 LCA run ≡ 1 native operation | LCA `spine.jsonl` is per-run-id; splitting it costs audit trail. |
| Q4.B | Drop `pluginState.lca.run_id` from front-end state | `lca_running_operations` table is the new single source. |
| Q5.A | New `GET /v1/topics/{topic_id}/messages` endpoint | `gatewayEventHandler` already has a hook for this; a plain HTTP endpoint is the smallest wire surface. |
| Q5.B | Fetch on every `step_start` | No caching; the DB is the source of truth; snapshot provider holds no state. |
| Q6.A | New `lca_running_operations` table | `useGatewayReconnect` needs a source; without it, cross-refresh is impossible. |
| Q6.B | Status from Redis; idempotency from table; no heartbeat column | Liveness from Redis key TTL; one source per concern. |
| Q7.A | Delete-when zero prod references | Native-style hygiene. |
| Q7.B | Delete `LegacyRunDispatcher` + `LCA_RUNTIME_FACADE` flag in PR-3 | No dual-path; one cutover. |
| Q8 | Borrow native names + new `streaming/` directory in `lca/application/runtime/` | One-name-per-thing across the protocol boundary. |
| Q9.A | Path 1: Next.js `rewrites()` (spike 1 confirmed) | The catch-all rule already covers WS; the rewrite path is already a known SOP. |
| Q9.B | `lcaGatewayUrl` injected via `serverConfigStore` (native pattern) | Single source of truth for the gateway URL. |
| Q10 | 7 e2e + 1 h stability smoke | All 5 broken paths from §1 are covered; one new path (protocol parity) catches future drift. |
| Q0 | P1 spec only; P2/P3 tracked separately | P2/P3 are blocked by P1's transport; serialised delivery. |

## 16. Acceptance for this spec

This spec is ready for writing-plans when:

- The lock-list above (Q0..Q10) is reviewed and acknowledged.
- The 5 broken-path fixes (§1, §5.2, §5.3, §5.4, §5.7) are explicitly accepted.
- The retirement of `LegacyRunDispatcher`, `LCA_RUNTIME_FACADE`, `RunUiEncoder`, `stream_run_live`, `lcaRunObserve`, `lcaRunHil`, `lcaJournal`, `LcaRunDriver` is acknowledged.
- The 7 e2e + 1 h stability smoke bar is acknowledged.

Once the user reviews and accepts this spec, invoke `writing-plans` to produce a step-by-step implementation plan with TDD checkpoints and a single-PR-or-many decision per file.
