# Raphy Assessment — 2026-10-20 night (04:45 round)

Branch: `raphy/arch-20261020-0445` (from main `88c83a37b`).
Scope rule: YAGNI over the last ~40 commits. Hot spots: run-session writer /
message derivation (RA-162..166, RA-159), tool defer + approval (RA-164, RA-165,
RA-167), browser tools + resilient mode (RA-147..153).

## Phase 1 — Explore

Read end-to-end (not grep):
- `lca/runtime/session/run_session_writer.py` (725 lines) — full read.
- `lca/infrastructure/tool_defer/session.py` (403) — full read.
- `lca/infrastructure/runtime_plane/access/approval_engine.py` (294) — full read.
- `lca/runtime/loop/runtime_loop.py` (lines 1–220), `lca/plugins/session/runtime/messages/messages.py`
  (`derive_event_message`), `lca_kernel/events/fold/inputs.py` (`_surface_op_of`,
  `isSurfaceEligibleType`) — read.
- `lca/infrastructure/tools/browser/tools.py` — structure scan (class list).

### Area A: run session writer / message derivation

- Q1 (bounce): one concept — "what text the model sees for a journal event" —
  is spread across THREE modules that do not agree: `RunSessionWriter.derive_messages`
  (the LLM wire, `think.history.assemble`), `derive_event_message` in
  `lca/plugins/session/runtime/messages/messages.py` (shared SSOT with the
  `model_visible` projection and `token_usage`), and the kernel `foldSurface`
  (`_surface_op_of`).
- Q2 (shallow): `extract_pending_intents_from_events` /
  `ensure_intent_widget_in_assistant_message` (connector_auth) and
  `extract_pending_browser_widgets_from_events` /
  `ensure_browser_widget_in_assistant_message` (browser_preview) are ~200 lines
  of near-verbatim twin pipeline: scan surface events for unmounted widget tags,
  append `[widget:kind?...]` tags to assistant content. Same algorithm, regex
  and field names swapped. Deletion test: deleting the *shared* shape would just
  move complexity back into two hand-synced twins — the seam is real, the
  modules are the duplication. (Duplication is the weakest class; kept as
  secondary.)
- Q3 (pure functions / locality): `_tool_result_content` joins `content`+`error`
  into model-visible text. Bugs are in how it's called (write-time `message`
  field vs derive-time `_tool_result_content`), documented in docstrings — the
  convergence (RA-166) already put the decision at write time. No new finding.
- Q4 (leaky seams): **`surface/developer_message` leaks across all three
  derive seams.** The writer appends it with `surface_op="developer_message"`
  (`append_developer_message`, ADR-0268 §6 cron handoff). Then:
  (a) `derive_messages` passes it through as `Message(role="developer")`;
  (b) the shared SSOT `derive_event_message` silently returns `None` (dropped
  from `model_visible` projection and token_usage);
  (c) the kernel fold `_surface_op_of` raises
  `ValueError: "surface/developer_message" is not surface-eligible and cannot
  carry surfaceOp` (verified by running `_parse_event` + `_surface_op_of` on a
  real developer row envelope — reproduces the raise).
  So one production journal row (cron handoff injects it every handoff turn,
  `runtime_loop.py:275`) is passthrough / silently-dropped / fail-loud depending
  on which path reads the journal. RA-163's `derive_messages` docstring says
  this "was deferred to its own story per the RA-163 residual notes" — **no such
  story exists in `raphy/prd.json`** (grepped all 167 stories). The marker is
  also a type-suffixed string, the same mistake class RA-163 fixed for
  `"tool_result"` (SurfaceOp contract only allows `"append" | replace).
- Q5 (testability): pinned by `tests/observability/session/test_known_types_fail_closed.py`
  (fail-closed for *unknown* types) — but `developer_message` is a *known* DSH
  type (`DSH_SURFACE_EVENT_TYPES` in `lca/session/surface_types.py`), so the
  fold raising on it is a seam bug, not the intended fail-closed. No test pins
  the agreed projection of a developer row across the three paths.
- No-op stub: `_drop_reasoning_after_dropped_calls` always returns input
  unchanged — "No-op when no reasoning-item event type is in the journal".
  There is no reasoning-item event type in the journal, so this is a permanently
  dead pipeline stage with a docstring promising conservatism. Deletion test
  fails: it concentrates nothing. One adapter = hypothetical seam — here the
  seam doesn't even exist yet.

### Area B: tool defer session + approval engine

- Q1/Q2: `ToolDeferSession` is deep — `namespace_of_tool` owns the only
  tool->namespace traversal ("two = real", RA-167 just re-sourced onto it).
  Strategies are thin `evaluate` adapters over `classify.decide_tool_call`;
  deletion test on any strategy would move its branch into the engine — each
  earns existence.
- `_tool_to_spec` twins `think.history.assemble._tool_to_spec` *deliberately*:
  docstring says "infrastructure must not import L2 nodes". The layer seam
  would leak if converged — earns existence. Not a candidate.
- Q4: `update_turn` fail-soft ("unknown" pseudo-namespace) vs `_describe`
  fail-fast (ValueError on undeclared namespace) — a deliberate two-level seam
  (runtime vs wiring), already covered by ADR-0256 B2. No new finding.
- No new candidate in this area.

### Area C: runtime loop / browser tools

- `runtime_loop.py` read: `CognitiveRuntime` is a narrow entry (verified
  declarative binding closure) — deep. The `developer_seed` handoff path is the
  production producer of developer rows (Area A finding).
- `browser/tools.py` structure: flat tool registry; recent rounds (RA-149, 151,
  152, 153, 156) already converged its dispatch and vocabularies. No new
  shallow sprawl found.
- Not an assessment area (per raphy-assess.md): ralph禁区 / lca-1000 / others'
  files untouched.

### Runtime verification (mandatory)

- This round (mock LLM, MockLLMAdapter): `agent.run("smoke")` x2 on one Agent →
  RUN1: completed | RUN2: completed. (a) and (c) pass.
- 01:45 round's `raphy-runtime-verify-20261020.py` (scripted LLM) covered (b)
  tool-call flow and (d) non-converging run → `Result(status=failed)`, no
  exception (RA-023 regression pinned). No new crash/hang/silent-failure found.
- The developer_message divergence (Area A) is the one runtime-observed
  inconsistency: I reproduced the fold's ValueError on a real developer row
  envelope; the writer and the shared SSOT disagree on inclusion.

### Duplication scan (secondary)

After the friction walk: the widget-fallback twin pipelines (Area A, RA-169).
No other mechanical duplication worth a story (the `_tool_to_spec` twin is
deliberate layer hygiene).

## Phase 2 — Self-grilling

### RA-168: Converge the three derive paths on `surface/developer_message`
- **Constraints**: ADR-0268 §6 (cron handoff enters as developer message;
  `job_id`/`run_id` provenance must survive); ADR-0201 MV2; kernel surface
  vocabulary is DSH-parity (`noqa: N802` markers) — changing
  `SURFACE_EVENT_TYPES` touches dsh parity; `test_known_types_fail_closed.py`
  must stay green.
- **Dependencies**: writer (`derive_messages` = LLM wire via
  `think.history.assemble`), `derive_event_message` (model_visible projection,
  token_usage), kernel `foldSurface` (transcript/history reads). Seam move
  affects all three consumers.
- **Shape**: one policy for a developer row, owned by one seam — e.g. teach the
  kernel the DSH extension vocabulary (eligible + marker "append", consistent
  with `DSH_SURFACE_EVENT_TYPES` and the RA-163 marker rule) and converge the
  wire + projection onto it; OR explicitly drop developer rows from the wire
  with provenance preserved in the journal. Assessment does not prescribe which;
  the story's acceptance criteria demand agreement.
- **Test survival**: `test_known_types_fail_closed.py` pins fail-closed for
  *unknown* types — must not regress. New test pins the agreed projection.
- **Deletion test**: deleting the divergence concentrates nothing; converging
  it removes a crash vector. **Strength: Strong.** Priority P1 (production
  path: every cron handoff turn writes this row; fold paths raise).

### RA-169: Converge the twin widget-fallback pipelines in run_session_writer.py
- **Constraints**: INV-CAP-04 (connector auth intent fallback), ADR-0280
  (browser preview fallback). Behavior must stay byte-identical (existing
  tests pin each widget kind).
- **Dependencies**: callers are `append_assistant_message` only; both pipelines
  are module-private functions in the same file — the seam move is local.
- **Shape**: one parameterized unmounted-widget seam: (widget tag regex,
  field-spec, tag builder) -> extract + ensure. Both widget kinds become two
  instantiations; a third kind would be one instantiation, proving the seam.
- **Test survival**: existing widget tests green; add a test instantiating the
  seam for a hypothetical third widget kind.
- **Deletion test**: concentrates — deleting the shared seam moves complexity
  back into hand-synced twins. **Strength: Worth exploring.** Priority P2.

### RA-170: Delete (or implement) the no-op `_drop_reasoning_after_dropped_calls`
- **Constraints**: derive_messages wire behavior must stay identical on all
  existing fixtures (orphan-drop tests in
  `tests/integration/test_orphan_tool_result_drop.py`).
- **Dependencies**: called once, at the end of `derive_messages`; module-private.
- **Shape**: recommendation is deletion — a pipeline stage for an event type
  that does not exist is a hypothetical seam. If kept, it must do something
  real and be pinned by a test.
- **Test survival**: orphan-drop tests unchanged; removing a no-op is
  behavior-neutral by construction.
- **Deletion test**: fails — concentrates nothing, moves nothing. Deleting it
  removes a misleading stage. **Strength: Worth exploring** (small, safe). P2.

## Phase 3 — Candidate table

| ID | Files | Problem | Solution | Benefits | Strength |
|---|---|---|---|---|---|
| RA-168 | `lca/runtime/session/run_session_writer.py`, `lca/plugins/session/runtime/messages/messages.py`, `lca_kernel/events/fold/inputs.py`, `lca/session/surface_types.py` | One `surface/developer_message` journal row is passthrough (LLM wire) / silently dropped (model_visible projection + token_usage) / fail-loud ValueError (kernel fold). Also carries a type-suffixed `surface_op` marker, the RA-163 mistake class. | One policy, one seam: make all three derive paths agree on developer rows (inclusion + shape), marker converged to `"append"`. | locality: "what the model sees for a developer row" decided once. leverage: removes a crash vector on every cron handoff journal. | Strong |
| RA-169 | `lca/runtime/session/run_session_writer.py` | ~200 lines of twin unmounted-widget fallback pipelines (connector_auth × browser_preview), identical algorithm, regex swapped. | One parameterized unmounted-widget seam; two instantiations. | locality: widget fallback logic in one place. leverage: third widget kind becomes one instantiation. | Worth exploring |
| RA-170 | `lca/runtime/session/run_session_writer.py` | `_drop_reasoning_after_dropped_calls` is a permanently dead pipeline stage (no reasoning-item event type exists) promising conservatism. | Delete it (or implement + pin by test). | locality: wire path has no speculative stages. leverage: trivial, honesty. | Worth exploring |

**Top recommendation**: RA-168 first. It is the only production-relevant
divergence found this round (cron handoff writes this row every handoff turn;
the kernel fold raises on it — reproduced), it is explicit RA-163 residual
debt whose "own story" was never written, and it sits exactly on the
"what text the model sees" SSOT the last three rounds converged. RA-169 and
RA-170 are safe follow-ups in the same file.

**Diversity quota**: satisfied — RA-168 is a friction-walk leaky-seam finding,
RA-170 a shallow/no-op finding; RA-169 is the (secondary) duplication finding.
Not all-duplication.

Assessment complete: 3 stories written, top is RA-168.
