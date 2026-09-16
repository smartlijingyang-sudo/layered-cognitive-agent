# Gap A — LCA HIL approval：HTTP /answer 桥接 vs WS intervention

> **状态**：plans（只读范围界定，本分支不含实现）
> **日期**：2026-09-16

## Problem

The LCA HIL (human-in-the-loop) approval flow has two candidate round-trip
paths:

1. **HTTP** — `POST /lca-api/runs/{runId}/answer` body
   `{approval_id, idempotency_key, payload}`. Bridged by the lobehub
   runtime patch
   [`deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py:323-336`](../../../deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py)
   for `askUserQuestion` and the `conversationControl` skip path
   [`:453-468`](../../../deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py).
2. **WS** — `agent_intervention_request` / `agent_intervention_response`
   events on the LCA gateway socket, mirroring lobehub's native flow.

The parent audit
[`resume-askuser-flow-2026-09-16.md`](./resume-askuser-flow-2026-09-16.md)
listed Gap B (no producer for `AgentInterventionRequest`) and Gap E (no
front-end handler for `agent_intervention_*`). The HTTP bridge is the
real, working round-trip today. This sub-investigation asks whether the
HTTP bridge is **structurally equivalent** to the WS path for the
multi-tab / multi-device use case — specifically, does it correctly
serialize concurrent approvals?

This is a scoping note (READ-ONLY). The `investigating/` directory is
intentionally outside the lifecycle four-state set; see
[`docs/notes/README.md`](../README.md) §2.1.

## What works today (HTTP path)

- **Idempotency-key dedup is implemented at the back-end port layer.**
  `RegistryRunCommands.resume_approval` short-circuits a replay before any
  state transition:
  [`lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py:169-176`](../../../lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py).
  The set lives on `RunSession.accepted_answer_keys`
  [`session/session/session.py:96`](../../../lca/plugins/transport/webserver/handlers/runs/session/session/session.py)
  and is recorded as a 200 with `status: "resumed"` (no second resume
  task). Regression locked in
  [`tests/transport/test_resume_idempotency.py:55-89`](../../../tests/transport/test_resume_idempotency.py).
- **HTTP route wired and required-fields validated.**
  `POST /runs/{run_id}/answer` mounted in
  [`routes_2/routes_runs_sessions.py:57`](../../../lca/plugins/transport/webserver/routes_2/routes_runs_sessions.py)
  → handler [`command_endpoints.py:364-399`](../../../lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py).
  Missing `idempotency_key` returns 400 before reaching the port
  (line 375-380). Successful accept also records into
  `running_operation_store.record_answer_key` (line 393-395) so a
  crashed-and-restarted gateway can replay dedup across process
  restarts.
- **HTTP client side always sets a stable idempotency key.**
  `handleLcaAskUserSubmit` derives `idempotency_key =
  "${runId}:${messageId}"` (lca_runtime_agent_gateway.py:328), and the
  skip branch uses `${runId}:${toolMessageId}:skip` (line 456). Same
  `messageId` across reconnects because lobehub keeps it in
  `pluginState` / DB.
- **Cross-tab replay is end-to-end covered at the WS layer.**
  `tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py` (`test_hil_idempotency_key_replay`,
  lines 35-153) connects two WS sockets in series, sends identical
  `tool_result` frames with the same `idempotencyKey`, and asserts both
  reach the port. The HTTP layer shares the exact same port, so the
  HTTP path inherits the same dedup.
- **Front-end intervention card flows through the same HTTP route.**
  `presentAskUserCard`
  [`deploy/lobehub/patches/runtime/lcaRunHil.ts:40-72`](../../../deploy/lobehub/patches/runtime/lcaRunHil.ts)
  materialises a tool-call row; the lobehub `customInteractionSubmit`
  patch forwards the answer via `fetch(/lca-api/runs/.../answer, ...)`.
- **No native WS path exists for `agent_intervention_response` today.**
  Both back-end (`EventTranslator` has the `_agent_intervention_request`
  handler but no producer fires it
  [`event_translator.py:277-284, 433-457`](../../../lca/application/runtime/coordinator/event_translator.py))
  and front-end (`gatewayEventHandler.ts` has no `case` for either
  intervention event) are dead on the LCA gateway. So WS path is not
  available regardless of HTTP behaviour.

## What is missing or broken

- **No lock around `resume_approval` to serialise concurrent
  approvals.** The method
  [`commands.py:138-273`](../../../lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py)
  reads `session.status`, mutates `session.status = RUNNING` (line 233),
  and adds to `session.accepted_answer_keys` (line 235) without an
  `asyncio.Lock` per session. Two concurrent invocations (Tab A and
  Tab B both POSTing `/answer` with **different** `idempotency_key`s
  for the same `waiting_input` pause) can both observe
  `status is WAITING_INPUT`, both flip to `RUNNING`, and both schedule
  `asyncio.create_task(resume_run(...))` (line 273). Two concurrent
  `agent_intervention_response` WS frames with different keys have
  the same hazard.
- **WS path bypasses the resume outcome.** `_handle_control_frame` for
  `tool_result`
  [`agent_gateway.py:327-338`](../../../lca/plugins/transport/webserver/handlers/runs/terminal/streaming/agent_gateway.py)
  `await run_port.resume_approval(...)` and returns `"ok"` without
  surfacing the resume's outcome to the client. The client has no
  per-tab "did my answer win" signal — it only sees the next
  `agent_event` on the WS. The HTTP path also returns
  `{"status": "resumed"}` with no per-tab winner indicator.
- **HTTP bridge is sole SSOT for cross-tab HIL today; no fallback if
  the gateway pod restarts mid-resume.** `running_operation_store` is
  in-memory by default (per
  [`command_endpoints.py:393-395`](../../../lca/plugins/transport/webserver/handlers/runs/api/command_endpoints.py));
  if the pod dies between record_answer_key and the resume landing,
  the dedup key may be lost. The session-level
  `accepted_answer_keys` set is also in-memory (RunSession attribute).
- **`approval_id` is not validated end-to-end.** The front-end posts
  the tool name (`"askUserQuestion"`) as `approval_id`, while the
  pending approval carries the derived `<plan_ref>:<node>:<visit>` id.
  Mismatch is logged at line 247-251 but accepted
  (regression locked in
  [`tests/transport/test_resume_idempotency.py:122-139`](../../../tests/transport/test_resume_idempotency.py)).
  This is fine for the askUserQuestion round-trip but means the
  cross-tab test's `toolCallId="tc1"` (the unit harness) is not
  representative of real production ids.
- **The cross-tab e2e test only covers sequential replay, not
  concurrent approvals.**
  [`tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py:115-140`](../../../tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py)
  reconnects Tab 2 only **after** Tab 1's first `tool_result` has
  landed (`len(port.calls) >= 1`). It does NOT exercise the "two
  tabs both POST simultaneously with different payloads" race that
  the lock-free `resume_approval` would expose. The WS-layer unit
  coverage is `test_hil_idempotency_key_replay` only.

## Decision matrix — HTTP /answer vs WS agent_intervention_*

| Scenario | HTTP `/answer` works? | WS `agent_intervention_*` works? | Notes |
|---|---|---|---|
| Single device, single tab | Yes (lca_runtime_agent_gateway.py:323-336) | No producer (Gap B); no front-end case (Gap E) | HTTP is the only working path today |
| Single device, multiple tabs | Yes (idempotency_key per `runId:messageId`); replay after Tab A wins is dedup'd (commands.py:169-176) | Same dead path | Concurrent same-key dedup works; concurrent **different**-key races the lock-free port |
| Multiple devices | Yes (same code path; auth is bearer JWT, no per-device check) | Same dead path | Each device has its own `messageId` per lobehub DB row; no special cross-device wiring |
| Concurrent approvals from multiple tabs (different `idempotency_key`s) | **Behaviour unclear**: both observe WAITING_INPUT, both flip status, both schedule resume_run — last write to `accepted_answer_keys` wins, but two `agent_runtime` cycles may interleave | Same dead path | No test; no lock; user has no clear "which tab won" indicator |
| Replay dedup (same `idempotency_key`) after Tab A wins | Yes: HTTP returns 200 replay; WS path same via shared port | Same dead path | Locked in `tests/transport/test_resume_idempotency.py:55-89` (HTTP) and `tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py` (WS) |

## Recommended fix (ranked)

### A1 — Document the multi-tab semantics in the handler docstring (low risk)

Add a paragraph to
`answer_run` (command_endpoints.py:364) and to `resume_approval`
(commands.py:138) stating:

- The HTTP path is the SSOT for HIL approval today.
- A `POST /runs/{id}/answer` with a previously-accepted
  `idempotency_key` is a replay and returns 200 with
  `status: "resumed"` (no second resume).
- Concurrent POSTs from different tabs with **different**
  `idempotency_key`s are not serialised today; the back-end will
  accept the first to land and run only one resume task per
  idempotency_key. Operators should treat the per-tab "did I win"
  signal as the next observed `agent_event` on the WS.

No code change to behaviour. Owner: webserver handler author. Cost:
half an hour + docstring review.

### A2 — Add an `asyncio.Lock` per session + reject concurrent
different-key POSTs (medium risk, mirrors Gap D pattern)

Mirror the Gap D dedup pattern at the port layer. Concretely:

- Add `session.approval_lock: asyncio.Lock | None` (lazy-init in
  `RegistryRunCommands.resume_approval`); acquire before the
  status-read + status-flip + idempotency-set sequence
  (commands.py:159-235).
- If a concurrent different-key POST is already in-flight, return
  `RunCommandReceipt(accepted=False, error="approval_in_progress",
  error_status=409)`.
- Wire it through the WS path the same way (both call the same
  `resume_approval`, no separate surface).
- Add a regression test that drives two `asyncio.gather(...)` calls
  to `resume_approval` with different keys and asserts exactly one
  resume task ran.

This closes the only real race in the matrix and gives operators a
clear "second tab got 409" signal. Owner: webserver port author.
Cost: ~2 hours + concurrency tests. Reversible (one method body).

### A3 — Implement the WS `agent_intervention_request` /
`agent_intervention_response` producer + consumer (highest impact,
**not recommended**)

Implies:

- New `_commit_approval_requested` WS emission via a new
  `_SPINE_HANDLERS` entry
  (event_translator.py:459+).
- Front-end `case 'agent_intervention_request'` and
  `case 'agent_intervention_response'` in
  `gatewayEventHandler.ts` (mirroring
  `heterogeneousAgentExecutor.ts:2009-2073`).
- Cross-tab refactor of the lobehub `customInteractionSubmit` to
  dial LCA's WS instead of `fetch(/answer)`.

Per AGENTS.md §1 ("接任务前 7 问"), this changes a Protocol and a
closed-set wire event — it is **contract work**, not a single-line
fix. Belongs in its own ADR + proposed Note, not in the Gap A
investigation branch.

## Recommendation

**A1 now** (cheap, explicit), **A2 as a follow-up** if a real user
report arrives about cross-tab races, **A3 only with an ADR**.

The HTTP bridge is correct for the single-tab and the replay case
(Gap D regression already landed in commit 66c563cd). The only
outstanding gap is the same-tab-race case, which the cross-tab test
already implicitly assumes does not happen (sequential reconnect).
Until a real user reports two tabs submitting different answers at
once, A1 documents the limit without changing semantics.

## Related

- Parent audit —
  [`resume-askuser-flow-2026-09-16.md`](./resume-askuser-flow-2026-09-16.md)
  Gaps A, B, C, D, E, F, G.
- Gap D fix commit — `66c563cd9 fix(transport): declare
  ToolResultMessage.idempotencyKey on the wire`.
- WS resume replay test —
  [`tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py`](../../../tests/e2e/p1/test_lca_p1_05_hil_cross_tab.py).
- HTTP port dedup test —
  [`tests/transport/test_resume_idempotency.py`](../../../tests/transport/test_resume_idempotency.py).
- Wire schema —
  [`lca/contracts/transport/gateway_messages.py:56-68`](../../../lca/contracts/transport/gateway_messages.py)
  + [`lca/contracts/transport/agent_stream_event.py:194-228`](../../../lca/contracts/transport/agent_stream_event.py).