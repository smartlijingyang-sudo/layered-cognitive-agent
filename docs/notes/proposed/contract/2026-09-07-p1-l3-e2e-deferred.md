# Agent Note: PR-3 Task 20 — L3-1 e2e + tool_result wire drift (deferred)

Status: proposed

## Problem

PR-3 Task 20 lands two artefacts whose full assertion needs a running
LCA kernel + dev stack that the PR-3 dispatch budget does not support:

1. **L3-1 kernel subprocess fixture** —
   ``tests/e2e/p1/conftest.py::kernel_process`` starts
   ``python -m lca_kernel serve --profile test-p1`` on a free port
   and waits for ``/health`` to return 200/204. The fixture is gated
   by ``LCA_E2E_KERNEL=1``; without it, every L3-1 test is
   ``pytest.mark.skip``-ed with the deferral reason in the test
   output. Running it in CI requires the LCA dev stack
   (``lca-ops infra start`` + Postgres + Redis + an LLM provider)
   which the PR-3 host does not have.

2. **Tool-result wire-shape drift** — the TS
   ``AgentStreamEvent`` union
   (lobehub-ui/packages/agent-gateway-client/src/types.ts:18-22)
   declares ``'tool_result'`` as a wire event type. The Python
   counterpart
   (``lca/contracts/transport/agent_stream_event.py``) does NOT
   declare a ``ToolResult`` event class — the producer emits
   ``tool_end`` with ``result`` populated. The parity test
   (``tests/e2e/p1/test_lca_p1_01_user_books_flight.py::
   test_event_envelope_shapes_match_python_wire_types``) records
   this drift but does not block CI.

## Proposal (future work — outline, not implementation)

### A. L3-1 fixture

When the LCA dev stack is available locally:

1. Set ``LCA_E2E_KERNEL=1`` and run ``uv run pytest tests/e2e/p1/ -v``.
2. The fixture starts the kernel subprocess, waits for ``/health``,
   yields ``{"base_url": ..., "port": ...}``, and tears down on
   teardown.
3. The full HIL scenario
   (``test_user_books_flight_full_hil_flow``) drives
   ``POST /lca-api/runs`` → WS auth → resume → publish a
   ``step_start{phase:human_approval, requiresApproval:true,
   pendingToolsCalling:[...]}` event → submit tool_result →
   assert ``agent_runtime_end{reason:completed}``.

### B. tool_result wire parity

Two acceptable shapes for the future PR:

1. **Add ``ToolResult(_WireBase)`` to
   ``lca/contracts/transport/agent_stream_event.py``** with
   ``type: Literal["tool_result"]`` and a typed ``data`` payload.
   Update the union, then update the producer in
   ``lca/application/runtime/coordinator/`` to emit it.
2. **Remove ``'tool_result'`` from the TS union** if the Python
   producer is canonical and the TS side never needs to receive a
   separate ``tool_result`` frame. Coordinate with
   ``packages/agent-gateway-client`` consumers.

Both must include a regression test in
``tests/integration/p1/test_lca_p1_node_05_tool_result.py`` (the
WS control-frame path) and a parity test that walks the Pydantic
union + the TS union side by side.

## Why deferred from this PR-3 dispatch

1. **Kernel subprocess needs the full dev stack.** Per ruling 5 in
   the PR-3 dispatch, e2e tests that take longer than the
   <5 s/test budget must be marked ``pytest.mark.skip`` with an
   Agent Note pointing to the hand-back path. Running the kernel
   from this host would require Postgres + Redis + LLM provider
   wiring — three independent platform concerns.

2. **Wire-shape drift is a Protocol concern.** AGENTS.md §1
   question 4 ("改变哪个边界?") says boundary changes need an
   ADR/Note first. The Python TS-vs-Python wire-types drift
   belongs in a future PR's ADR, not in a Task-20 dispatch that
   is already running long.

3. **Branch is self-contained without Task 20's runtime assertions.**
   The 19 L2 integration tests in
   ``tests/integration/p1/`` cover the gateway contract surface
   (auth, resume, heartbeat, interrupt, tool_result routing, redis
   shape, running-op null, ws-token refresh). The Python wire
   harness
   (``tests/e2e/p1/_lca_gateway_client.py``) is import-clean and
   exercised by L2 WS tests via the in-process
   ``build_agent_gateway_app`` factory. The kernel-subprocess
   surface area is structurally the same; running it adds a real
   producer but does not change the protocol contract.

## Acceptance criteria for re-opening this task

- The LCA dev stack is reachable from CI (``lca-ops infra status``
  returns ``healthy`` in <30 s).
- A Postgres migration creating ``lca_running_operations`` (per the
  earlier deferred note) has landed so the populated-row branch
  of L2-7 can be exercised end-to-end.
- An ADR is opened (or this note is promoted to ``implemented/``)
  that names either the new ``ToolResult`` wire event OR the
  TS-side removal of ``'tool_result'`` from the union.

## Open questions

- Should the L3-1 fixture be module-scoped (shared kernel) or
  function-scoped (per-test fresh kernel)? Module-scoped is faster
  but couples tests; function-scoped is slower but isolates. PR-4
  should pick one based on the agent-loop integration tests that
  follow.

## Related

- Agent Note ``docs/notes/proposed/contract/
  2026-09-07-p1-facade-ws-token-todo.md`` — companion deferral for
  the ``ws_token`` minting and the ``lca_running_operations``
  Postgres migration.
- ADR-0200 (`docs/adr/0200-p1-agent-gateway-bridge.md`) — umbrella
  decision for the P1 transport switchover.
- Plan Task 17 / Task 20 — ``docs/superpowers/plans/
  2026-09-07-lca-p1-agent-gateway-bridge.md`` (in the main repo, not
  the worktree).