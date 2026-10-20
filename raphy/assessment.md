# Raphy Assessment — 2026-10-20 night (07:45 round)

Branch: `raphy/arch-20261020-0745` (from main `22c7552d0`).
Scope rule: YAGNI over the last ~40 commits. Hot spots: run lifecycle /
resume / recovery (HITL pause, PR #47/#48, RA-159/160/161), tool defer
session (RA-160, RA-164, RA-167), run session writer (RA-162..170 — already
converged three rounds in a row, skipped this round), browser tools
(RA-147..153, RA-156 — converged, re-scanned, nothing new).

## Phase 1 — Explore

Read end-to-end (not grep):
- `lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py` (486) — full read.
- `lca/plugins/transport/webserver/carrier/runs/recovery.py` (429) — full read.
- `lca/plugins/session/runtime/resume/point.py` (207) — full read.
- `lca/plugins/transport/webserver/handlers/runs/terminal/lifecycle.py` (265) — full read.
- `lca/infrastructure/tool_defer/session.py` (403) — full read.
- `lca/infrastructure/session/emit/lifecycle_emit.py` (`emit_approval_pause_from_result`) — read.
- `lca/runtime/loop/runtime_loop.py` (`_paused_seconds_since`, `resume()`) — read.
- `lca/plugins/transport/webserver/carrier/runs/execute/loop_drivers.py` (`CognitiveRunDriver`) — read.
- `lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py` (`build`, restore path) — read.

禁区 respected: ralph Round 2 领地 / lca-1000 迁移 / `gate_chain_strategy.py` /
`computer/guest/preamble.py` untouched. `contracts/event.py` PILOT, ADRs not
re-litigated (ADR-0195 P4-S04, ADR-0292 §10 P3, ADR-0256 B2 noted where they
constrain candidates).

### Area A: run lifecycle / resume / recovery (HITL pause-resume)

- Q1 (bounce): the "paused run" concept spans lifecycle.py (execute/resume/
  _finish_or_pause), recovery.py (write/load/restore), terminal/lifecycle.py
  (outcome apply, `_capture_loaded_namespaces`), point.py (resume-point
  serde), session.py (RunSession fields). Each module owns a different seam
  (carrier lifecycle vs durable bundle vs resume point vs defer session), so
  the bounce is layered, not sprawl. No candidate from Q1 alone.
- Q2 (shallow): `task_cancelled` / `current_task_cancelled` in
  terminal/lifecycle.py are 2-line predicates; `apply_driver` /
  `apply_resume` and the `RunTerminalizer` / `RunOutcomeApplier` class aliases
  are backward-compat shims. Deletion test moves a one-liner inline —
  concentrates nothing. Not worth a story (hygiene, not architecture).
- Q3 (pure functions / locality): **`_pending_tools_calling` in recovery.py
  vs the `pending` derivation inside `emit_approval_pause_from_result` in
  lifecycle_emit.py — two hand-written derivations of the same concept
  ("the pending tool calls shown on the waiting_input checkpoint") from the
  same `approval_request["tool_calls"]` shape, in two modules.** The
  derivations have already drifted in three ways (details in RA-171). No
  locality: "what the UI card shows for a paused run" is decided in two
  places that cannot see each other. → candidate RA-171 (Strong).
- Q4 (leaky seams): **`execute()` and `resume()` in carrier lifecycle.py
  hand-duplicate the same ~15-line TrustEnvelope ritual** (deferred imports of
  `get_current_trust_envelope` / `trust_envelope_scope` /
  `assistant_trust_envelope`, "envelope or assistant default", enter scope;
  lifecycle.py:185–193 vs 327–335). ADR-0292 §10 P3 policy edits must land in
  two places. Two = real seam, currently un-owned. → candidate RA-172.
  (Also noted: recovery's `_assemble_runnable` hand-resolves
  `RUN_MODE_REGISTRY` + `llm_resolver` and constructs
  `CognitiveRunnableAssembler` inline, while the execute path gets the
  assembler injected by the composition root via `CognitiveRunDriver`.
  Deliberate per the module docstring — recovery runs outside the
  composition root — but it means the assembly seam has two construction
  paths. Strength: Speculative; not written as a story this round — the
  deliberate-reason (outside composition root) is load-bearing and the
  failure mode is hypothetical.)
- Q5 (testability): `validate_bundle`'s docstring claims the load seam
  rejects bundles "instead of degrading into a zombie session with silent
  `str(... or "")` defaults downstream" — but only 4 of the ~24 bundle
  fields are fail-closed; the other ~20 still get silent `""` defaults on the
  read side. The bundle field inventory is hand-mirrored between
  `write_resume_bundle` and `_restore_from_bundle`. → candidate RA-173.

### Area B: tool defer session

- Q1/Q2: `ToolDeferSession` is deep — loaded set, per-turn view, wire
  rendering owned in one module; `new_defer_session` (RA-160) is the single
  home of the vocal-mode → defer-session derivation shared by create-run and
  `bind_resume_capabilities`; `namespace_of_tool` owns the only
  tool→namespace traversal ("two = real"). Deletion test on any of these
  moves complexity back into hand-synced call sites.
- Q3/Q4: `update_turn` fail-soft ("unknown" pseudo-namespace) vs `_describe`
  fail-fast (ValueError on undescribed namespace) is a deliberate two-level
  seam already covered by ADR-0256 B2. `_tool_to_spec` twin of
  `think.history.assemble._tool_to_spec` is deliberate layer hygiene (docstring
  says so; converging would leak L2 into infrastructure).
- No candidate in this area (agrees with the 04:45 round's read).

### Area C: runtime loop resume + reducer pause budget (PR #47)

- `_paused_seconds_since` (runtime_loop.py:81) is the single derivation of
  paused duration from `snapshot.paused_at` (RA-159's explicit field);
  `Reducer.apply_resume(..., paused_seconds=...)` documents the wall-clock
  shift in the protocol. One seam, one direction. No candidate.
- Minor: `resume()` constructs a second inline `RunSessionWriter` for the
  human-answer append 10 lines after binding `run_writer` for the same
  session — a local micro-duplication, not a real seam (same method, no
  leverage). Not written as a story.

### Runtime verification (mandatory)

- This round (mock LLM, MockLLMAdapter, clean worktree at main tip):
  `agent.run("smoke")` x2 on one Agent → RUN1: completed | RUN2: completed.
  (a) and (c) pass.
- 01:45 round's `raphy-runtime-verify-20261020.py` (scripted LLM) covered (b)
  tool-call flow and (d) non-converging run → `Result(status=failed)`, no
  exception (RA-023 regression pinned). No new crash/hang/silent-failure in
  the core flows.
- The RA-171 drift (pending_tools_calling) is a code-level silent divergence,
  not a runtime crash — verified by reading both derivations end-to-end, not
  by execution.

### Duplication scan (secondary)

After the friction walk: the twin TrustEnvelope rituals (RA-172) and the
twin bundle-field mirrors (RA-173). The `_tool_to_spec` twin is deliberate
layer hygiene (not a candidate). The second `RunSessionWriter` construction
in `resume()` is a same-method micro-dup (not a candidate). No other
mechanical duplication worth a story.

## Phase 2 — Self-grilling

### RA-171: Converge the twin pending_tools_calling derivations (fresh pause vs recovery)
- **Constraints**: ADR-0195 P4-S04 — the recovery journal is deliberately
  minimal (approval.persisted.v1 + waiting_input only; the original
  pause-time journal.json is never overwritten). So the recovery path must
  NOT blindly re-emit `step.tool_call.record` facts (they already exist in
  the pause-time journal); the story must decide explicitly whether recovery
  records them, reuses the pause-time ones, or documents the difference.
  The `lca_run_id` injection needs the *frontend-facing* run id — in
  recovery that is the bundle's `run_id`, not `get_current_run_id()`.
  `emit_approval_pause_from_result` is also called from the facade path;
  the seam must stay importable from infrastructure without pulling in
  webserver carrier code (layering: carrier → infrastructure, never the
  reverse).
- **Dependencies**: `emit_approval_pause_from_result` callers (carrier pause
  path, facade path), `recovery._seed_recovery_facts`, gateway wire
  consumers of `pending_tools_calling` (`event_translator.py`,
  `session_catalog_map.py`).
- **Shape of deepened module**: one function owns the derivation, e.g.
  `pending_tools_calling_from(approval_request, *, run_id=None)` living in
  the infrastructure/session emit seam (or a shared helper both modules
  already import); `run_id` present → inject `lca_run_id` into
  askUserQuestion args; the `record_step_tool_call` side effect stays at
  the fresh call site (or moves in behind an explicit flag). Recovery calls
  it with the bundle run_id.
- **Test survival**: existing recovery + approval-pause tests green; new
  test feeds the SAME approval_request to both paths and asserts identical
  pending lists (the current drift fails this test — good, it pins the fix).
- **Deletion test verdict**: deleting the shared derivation moves the logic
  back into two hand-synced copies that have ALREADY drifted in three ways
  — concentrates. Earns existence. **Strength: Strong.** Priority P1
  (restart-recovered runs render the ask card without `lca_run_id` — the
  frontend submit handler cannot resume the run: a silent failure on a
  production path).

### RA-172: Converge the twin TrustEnvelope bind rituals in RunLifecycleCoordinator
- **Constraints**: the ritual's imports are deferred (function-local) today —
  the seam must keep the same lazy-import discipline (likely import-cycle
  avoidance between carrier and `infrastructure.assistant.io`); ADR-0292 §10
  P3 is the policy owner — the seam's docstring must cite it.
- **Dependencies**: only `execute()` and `resume()` in
  carrier/runs/lifecycle/lifecycle.py.
- **Shape of deepened module**: one context manager, e.g.
  `bind_carrier_trust_envelope(session)` in the carrier lifecycle module (or
  a private `_trust_envelope_scope` helper), wrapping the body in both
  methods: `with bind_carrier_trust_envelope(session): ...`.
- **Test survival**: behavior-neutral by construction; lifecycle tests
  green, `ruff check` clean.
- **Deletion test verdict**: deleting the shared CM moves the ritual back
  into two hand-synced copies — concentrates. Earns existence.
  **Strength: Worth exploring.** Priority P2. ("One adapter = hypothetical
  seam, two = real" — here two occurrences already exist, so the seam is
  real and should be owned.)

### RA-173: Own the resume-bundle field inventory in one place
- **Constraints**: pre-2026-10-19 bundles without `loaded_namespaces` must
  keep loading (RA-161 backward-compat); the write side is best-effort
  (never raise on the pause path); `validate_bundle`'s fail-closed
  contract is the load seam (RA-121) — extend it, don't bypass it.
- **Dependencies**: `write_resume_bundle`, `_restore_from_bundle`,
  `validate_bundle`, `load_resume_bundle` callers (answer handler).
- **Shape of deepened module**: one field inventory owned by the recovery
  seam — e.g. a `_BUNDLE_FIELDS` spec (name + session-attr extractor +
  read default + required flag) that write and read both walk; required
  fields missing from a bundle → `validate_bundle` rejects (documenting
  which defaults are intentional for the optional ones).
- **Test survival**: `test_run_restart_recovery.py` green; new test asserts
  write→read round-trips every inventoried field and that a bundle missing
  a required field is rejected (fails today for e.g. missing `question`).
- **Deletion test verdict**: deleting the shared inventory moves the field
  lists back into two hand-synced mirrors that only partially agree today
  — concentrates. Earns existence. **Strength: Worth exploring.**
  Priority P2.

## Phase 3 — Candidate table

| ID | Files | Problem | Solution | Benefits | Strength |
|---|---|---|---|---|---|
| RA-171 | `lca/infrastructure/session/emit/lifecycle_emit.py` (`emit_approval_pause_from_result`), `lca/plugins/transport/webserver/carrier/runs/recovery.py` (`_pending_tools_calling`, `_seed_recovery_facts`) | "Pending tool calls for the waiting_input checkpoint" is derived twice from the same `approval_request["tool_calls"]` shape with three silent drifts: fresh path skips empty tool_name/call_id (recovery keeps `""` entries), fresh path injects `lca_run_id` into askUserQuestion args (recovery drops it — frontend submit cannot resume a recovered run), fresh path records `step.tool_call.record`/pending_approval facts (recovery skips). No locality: the concept lives in two modules that cannot see each other. | One seam owns the derivation (e.g. `pending_tools_calling_from(approval_request, *, run_id=None)` in the infrastructure emit seam); recovery calls it with the bundle run_id; the step-record side effect stays explicitly at the fresh call site per ADR-0195 P4-S04. | locality: "what the UI card shows for a paused run" decided once. leverage: future checkpoint consumers read one contract; one test pins both paths. | Strong |
| RA-172 | `lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py` (:185–193, :327–335) | `execute()` and `resume()` hand-duplicate the same ~15-line TrustEnvelope ritual (deferred imports, "envelope or assistant default", enter scope). ADR-0292 §10 P3 policy edits must land twice. | One context manager, e.g. `bind_carrier_trust_envelope(session)`, wrapping the body in both methods; keep the deferred-import discipline. | locality: the P3 policy in one place. leverage: a third call site gets it for free. | Worth exploring |
| RA-173 | `lca/plugins/transport/webserver/carrier/runs/recovery.py` (`write_resume_bundle`, `_restore_from_bundle`, `validate_bundle`) | The bundle's ~24-field inventory is hand-mirrored: write enumerates session attrs, read re-lists the same keys with `or ""` defaults. Only 4 keys are fail-closed; the other ~20 drift silently (a field added on write but not mirrored on read degrades to `""` — the zombie session `validate_bundle`'s docstring claims to prevent but doesn't cover). | One field inventory owned by the recovery seam (`_BUNDLE_FIELDS` spec walked by both write and read); required fields missing → `validate_bundle` rejects; intentional defaults documented. | locality: the bundle contract in one list. leverage: future bundle fields get validation for free; kills the docstring/behavior mismatch. | Worth exploring |

**Top recommendation**: RA-171 first. It is the only candidate with a
measurable silent behavioral divergence on a production path (a
restart-recovered run's ask card loses `lca_run_id`, so the frontend submit
handler cannot resume the run), the concept has zero locality today, and the
drift is already three concrete differences — the seam is real and already
hurting. RA-172 and RA-173 are safe same-area follow-ups.

**Diversity quota**: satisfied — RA-171 is a friction-walk leaky-seam /
no-locality finding (Strong), RA-172/RA-173 are the secondary duplication
findings. Not all-duplication. Files read with no finding recorded above
(tool defer session, runtime_loop resume, reducer pause budget, builder —
deep, no candidate, with reasons).

Assessment complete: 3 stories written, top is RA-171.
