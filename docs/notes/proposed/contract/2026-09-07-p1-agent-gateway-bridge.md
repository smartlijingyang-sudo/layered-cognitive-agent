# Agent Note: Agent Gateway Bridge wire contract (PR-1..PR-4)

Status: proposed

## Problem

LCA's run-time event surface (Session log + LiveRunProjection fold) is
consumed today through a hand-rolled SSE endpoint (`stream_run_live`) plus
four legacy event types that don't match the native LobeHub front-end's
expectations. Three concrete failures:

1. Front-end reconnect can't resume from a known `lastEventId` (no Redis
   Stream backing).
2. Tool state changes are dropped on reconnect — the WS event payload
   omits `projected_state`, and the server never persists it to the
   tool message row before publishing `tool_end`.
3. A parent run that reaches a terminal state without emitting
   `SpineClose` (kernel restart, GC, scheduler stop) leaves the WS open
   forever — there is no watchdog.

The native AgentGateway client (`@lobechat/agent-gateway-client`) expects
an 18-event `AgentStreamEvent` union + 5 ClientMessage + 7 ServerMessage
shapes plus a Redis Stream layout (`agent_runtime_stream:` prefix, 2 h
TTL, ~1000 MAXLEN). Re-implementing that surface in LCA restores the
front-end's reconnect, resume, and projected-state semantics.

## Proposal

Add four Python modules under existing layer boundaries; let the front-end
patch modules under `deploy/lobehub/patches/runtime/` carry the TS-side
surface, and retire the legacy SSE / `lcaRunObserve` / `lcaRunHil` /
`lcaRunCommand` / `LcaRunDriver` paths in PR-4.

| Module | Layer | Role |
|---|---|---|
| `lca/contracts/transport/{agent_stream_event,gateway_messages,stream_keys}.py` | contracts | Pure pydantic mirror of `agent-gateway-client/src/types.ts`; 18 + 5 + 7 wire types, Redis key constants. Zero infra/cognition/runtime/agent imports (AST-verified). |
| `lca/infrastructure/observability/stream/stream_event_manager.py` | infrastructure | `LcaStreamEventManager` — `xadd/xread/xrange/xlen/expire` wrapper, SSE-frame `AsyncIterator`. Same field set + TTL + MAXLEN as native. |
| `lca/infrastructure/observability/stream/redis_client.py` | infrastructure | URL-precedence factory (`REDIS_URL` > `LCA_REDIS_URL` > dev default). |
| `lca/application/runtime/coordinator/{event_translator,terminal_hints,runtime_coordinator}.py` | application | StampedEvent → AgentStreamEvent fold; `RunSession.status` → 6-value wire enum; `LcaAgentRuntimeCoordinator` (start, fold, watchdog, persist projected_state before `tool_end`). |
| `plugins/transport/webserver/handlers/runs/terminal/streaming/{agent_gateway,auth,resume}.py` | plugins | `LcaAgentGateway` Starlette `WebSocketRoute`; RS256 JWT mint + verify; history replay + `resume_complete`. |
| `plugins/transport/webserver/handlers/runs/api/{command_endpoints,query_endpoints}.py` (modify) | plugins | `create_run` adds `ws_token`; `get_running_operation` reads `lca_running_operations` jsonb. |
| `application/runtime/default_facade.py` (modify) | application | `dispatch_run` switches from `LegacyRunDispatcher` to `LcaAgentRuntimeCoordinator`. |

`LiveRunProjection.tail` stays the single source of truth for live
state; the Coordinator is a **fold** from `LiveRunProjection.tail` to
`LcaStreamEventManager.publish`. It does NOT replace the projection —
it observes it. No SSOT change.

## Wire contract (PR-1)

- 18 `AgentStreamEvent` types + 5 `ClientMessage` + 7 `ServerMessage`
  (see `lca/contracts/transport/`).
- Redis key: `agent_runtime_stream:<operation_id>`; TTL 2 h; MAXLEN `~1000`.
- JWT: RS256, 5 min expiry, `purpose: "cli-sandbox"`, `sub: <user_id>`.
- WS heartbeat: 30 s client interval, 3 missed → force reconnect,
  1 s → 30 s exponential backoff.

## Topology

```
SpineEvent → Session.append → LiveRunProjection.tail
                                    │
                                    ▼
              EventTranslator (PR-2 / Task 4)
                                    │
                                    ▼
              LcaAgentRuntimeCoordinator (PR-2 / Task 6)
                ├── metadata_writer    →  lca_running_operations row
                ├── tool_state_writer  →  messages[].pluginState DB column
                └── LcaStreamEventManager.publish (PR-1)
                                          │
                                          ▼
                              agent_runtime_stream:<run_id>  (Redis)
                                          │
                                          ▼
              LcaAgentGateway (PR-2 / Task 7) — Starlette WebSocketRoute
                                          │
                                          ▼
                              @lobechat/agent-gateway-client (native, zero mods)
```

## Alternatives considered

### Why not keep the SSE endpoint and add Redis-backed resume only?

The legacy SSE serializer emits 4 `LCA-Run-*` events whose JSON shape
doesn't match the native `AgentStreamEvent` union. Adding Redis to a
mismatched serializer would still require either (a) a parallel
TS-side decoder in `lca_runtime_use_sse_compat.ts`, or (b) a converter
in Python. Both grow the surface area without retiring legacy code.
Byte-compat with native lets us delete both sides in PR-4.

### Why not place `LcaStreamEventManager` next to the existing
`lca/infrastructure/observability/stream/` files (channel.py,
response_text_stream.py, etc.)?

They are placed there as siblings. The existing files cover LLM output
channel classification (decision vs answer text) — different concern
from the agent runtime event bus. The dir is flat, so the addition is
a sibling, not a sub-module. Per-directory README is updated to
disambiguate.

### Why not write `agent_runtime_init` and `agent_runtime_end` as
`Session.append` events instead of `LcaStreamEventManager.publish`?

`agent_runtime_init` must be in Redis BEFORE the front-end can
`EXISTS` check (useGatewayReconnect) and BEFORE the WebSocket can
subscribe. `Session.append` is the durable fact plane (ADR-0186/0194),
but the Redis stream is a transient transport channel — different
lifecycle (2 h vs durable). Mixing the two planes would either leak
transient state into the durable journal or delay init past the
front-end's EXISTS check.

### Why a Coordinator instead of folding inside `LiveRunProjection`?

`LiveRunProjection` is a pure fold over Session facts — no side
effects, no I/O (ADR-0198 I-OCG-6). The Coordinator needs to persist
`projected_state` to a DB row before publishing `tool_end` (a
control-plane side effect, AGENTS.md §2.3). Splitting fold from
side effects keeps `LiveRunProjection` pure.

## Acceptance criteria

- `lca.contracts.transport` has zero imports from
  `lca.infrastructure / cognition / runtime / agent / application /
  plugins / harness` (AST-verified).
- `LcaStreamEventManager.publish(run_id, ...)` produces an XADD row
  whose field set, key prefix, TTL, and MAXLEN are byte-identical to
  the native TS `streamKey` + `addEvent` calls.
- `LcaAgentRuntimeCoordinator.handle_stamped` writes
  `tool_state_writer(run_id, tool_call_id, projected_state)` **before**
  publishing `tool_end` (visible via `AsyncMock` call ordering in L1).
- `lca_running_operations` table gains NO `status` column
  (spec §3.2); audit script (`scripts/audit_lca_legacy_path.py`) exits
  0 in CI after PR-4.
- The 7 forbidden patterns (`LegacyRunDispatcher`, `LCA_RUNTIME_FACADE`,
  `RunUiEncoder`, `stream_run_live` route, `lcaRunObserve`, `lcaRunHil`,
  `lcaJournal`, `LcaRunDriver`, `lcaRunCommand`) appear zero times in
  the repo after PR-4.

## Source-of-truth links

- Spec: [docs/specs/2026-09-07-lca-p1-agent-gateway-bridge.md](../../../specs/2026-09-07-lca-p1-agent-gateway-bridge.md)
- Plan: [docs/superpowers/plans/2026-09-07-lca-p1-agent-gateway-bridge.md](../../../superpowers/plans/2026-09-07-lca-p1-agent-gateway-bridge.md)
- ADR: [docs/adr/0200-p1-agent-gateway-bridge.md](../../../adr/0200-p1-agent-gateway-bridge.md)

## Supersede check

Searched `docs/notes/proposed/` and `docs/notes/implemented/` for prior
records on `AgentGateway`, `WebSocket route`, `Redis Stream agent`,
`live_run_projection`. No active record found. This note is the first.
