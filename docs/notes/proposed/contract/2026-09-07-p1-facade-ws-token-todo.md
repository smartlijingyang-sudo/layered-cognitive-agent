# Agent Note: PR-2 Task 12 — facade `ws_token` + `lca_running_operations` writer (deferred)

Status: proposed

## Problem

The `LcaAgentGateway` introduced by this PR-2 ships its own
`/v1/runs/{run_id}/ws` WebSocket and `/v1/runs/{run_id}/ws-token`
mint endpoint, but the upstream carrier (`create_run`) still
returns only the legacy 202 envelope (`run_id` / `trace_id` /
`live_url`). The native front-end's `AgentStreamClient` therefore has
no token to dial the WS, and there is no `lca_running_operations`
row for the new query endpoint
(`/v1/topics/{topic_id}/running-op`) to read against. Plan Task 12
calls for closing both gaps inside the same PR; this note records
that the closure is **deferred out of this subagent dispatch** and
captures the precise diff a future PR must apply.

## Proposal (future work — outline, not implementation)

Three coordinated edits live behind the gate. None are part of this
PR's commits.

### 1. `create_run` returns `ws_token`

`lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py`:

- `render_create_run_receipt` adds a `ws_token` key whose value is
  `auth.mint_user_jwt(user_id=<from request>, operation_id=run_id, ttl_seconds=DEFAULT_TTL_SECONDS)`.
- The legacy 202 envelope keys (`run_id`, `trace_id`, `agent`,
  `live_url`) stay byte-compat; `ws_token` is a new optional key.
- Acceptance: a `RequestClient.websocket_connect` round-trip
  initiated with the new `ws_token` completes the auth handshake.

### 2. `default_facade.dispatch_run` plumbs the `LcaAgentRuntimeCoordinator`

`lca/application/runtime/default_facade.py` (231 lines today) is the
facade that produces a `RunHandle` and hands it back to the carrier.
The `RunDispatcher` protocol it delegates to is the seam where
`LcaAgentRuntimeCoordinator.start` must run so the metadata_writer
can be invoked at the right time.

- Extend `RunDispatcher` (or add a sibling `AgentRunDispatcher` port)
  to take the coordinator and `metadata_writer` as constructor args.
- The new dispatch path:
  1. `SessionActivation` is forwarded unchanged (I-HPC-2).
  2. `LcaAgentRuntimeCoordinator.start(activation, intent, metadata_writer)`
     is called before returning the `RunHandle`. `metadata_writer` is
     a callable `async (run_id, topic_id, agent_id, assistant_message_id, scope) -> None`
     that writes the `lca_running_operations` row.
  3. `RunHandle.run_id` is taken from the coordinator's first
     `agent_runtime_init` publish.
- Acceptance: an integration test seeds a topic, posts `create_run`,
  and queries `/v1/topics/{topic_id}/running-op`; the response
  carries a non-null `running_operation` row.

### 3. `metadata_writer` writes `lca_running_operations`

Schema per spec §3.2 + ADR-0200 I-AGB-5 (NO `status` column):

```text
lca_running_operations(
    run_id            text  PRIMARY KEY,
    topic_id          text  NOT NULL,
    agent_id          text  NOT NULL,
    assistant_message_id text,
    scope             jsonb NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    accepted_answer_keys jsonb NOT NULL DEFAULT '{}'::jsonb
)
```

The migration is the gating dependency. Once the table exists, the
writer is a thin `asyncpg` insert; tests in
`lca/application/runtime/coordinator/tests/test_runtime_coordinator.py`
already exercise the `metadata_writer` call site (AsyncMock slots at
lines 32/43/59/86/101/118).

## Why deferred from this subagent dispatch

1. **Postgres migration is out of scope.** Task 10's
   `get_running_operation` deliberately returns
   `{"running_operation": null}` for the missing-store branch. The
   populated-row branch is structurally coupled to a migration that
   this dispatch's host has not committed (and that the LCA dev
   Postgres fixture does not yet have).

2. **`default_facade.py` has 10000+ chars of existing code with
   integration test coverage.** Touching
   `DefaultRuntimeFacade.__init__` (the constructor-injected
   `RunDispatcher` per ADR-0199 I-HPC-9) and `dispatch_run` is a
   non-trivial contract change: every test that constructs
   `DefaultRuntimeFacade(plan_resolution_service, run_dispatcher)`
   must be updated to the new argument shape, and the integration
   tests under `tests/harness/runtime/` exercise this seam. The
   scope risk of slipping this into a 12-task dispatch with a tight
   <5 s/cap reliability budget outweighs the cost of a follow-up PR.

3. **No front-end change required.** The native
   `AgentStreamClient` does not need the `ws_token` to dial the WS
   (the legacy carrier hands the token via cookie / SSR). The
   `ws_token` field is purely a forward-compat addition for
   `useGatewayReconnect` (Task 27/28). The branch is not broken by
   deferring.

4. **Branch is self-contained without Task 12.** The 14 L1+L2 tests
   added in this PR (4 in `test_lca_agent_gateway.py`, 8 in
   `wire/tests/`, 2 in `wire/tests/test_ws_mount.py`) cover the
   `mount_ws_route` + `refresh_ws_token` + `get_running_operation`
   null-branch surface area. The native front-end continues to
   dial the legacy carrier until the deferred follow-up lands.

## Acceptance criteria for re-opening this task

All three must be true before a follow-up PR picks this up:

- A Postgres migration creating `lca_running_operations` (schema
  above) is merged and the LCA dev fixture's bootstrap applies it
  automatically. (Owner: data-platform team or whoever owns
  `deploy/postgres/init.sql`.)
- The `DefaultRuntimeFacade` integration tests under
  `tests/harness/runtime/test_default_facade.py` (and any other
  callers) pass with the existing `RunDispatcher` shape so a
  constructor change is local and visible.
- A follow-up ADR is opened (or this note is promoted to
  `implemented/`) that names the `RunDispatcher` extension and
  pins the `metadata_writer` callable signature in a Protocol so
  test mocks cannot drift.

## Open questions

- Should the new dispatch path live as an additional
  `RunDispatcher` (e.g. `AgentRunDispatcher` next to the existing
  carrier dispatcher) or as an extension of the existing one? The
  cleanest seam is the second — `dispatch_run` already has all the
  inputs — but the first preserves the existing 100% of integration
  tests untouched. Decision deferred to the follow-up PR.
- Does `ws_token` belong in the 202 envelope, or should it be a
  separate header (`X-Lca-Ws-Token`)? The spec §5.4 says header is
  acceptable; the native `AgentStreamClient` reads the JSON body
  when SSR hands it through `__INITIAL_STATE__`. Body-key is
  easier to test; header is more secure. Decision deferred.

## Risks

- If the migration lands but the facade extension does not, the
  `lca_running_operations` table is write-dead. Gate the
  migration behind the facade PR (or vice-versa).
- A second `RunDispatcher` protocol is a temptation to fork
  behavior; the integration test count will balloon. Recommend
  one dispatcher with a `coordinator=None` default so the legacy
  path keeps its current shape.

## Related

- ADR-0200 (`docs/adr/0200-p1-agent-gateway-bridge.md`) — I-AGB-5
  bans a `status` column on `lca_running_operations`; the
  proposed schema respects this.
- Agent Note 2026-09-07-p1-agent-gateway-bridge — the umbrella
  proposal this note extends.
- Plan Task 12 — `docs/superpowers/plans/2026-09-07-lca-p1-agent-gateway-bridge.md`
  in the main repo (not the worktree).
