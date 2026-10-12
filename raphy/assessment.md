# Raphy Assess — 2026-10-10 23:45 round

Branch: `raphy/arch-20261010-2345` (worktree `/home/lichao/.lca-worktrees/raphy-20261010-2345`)
Mode: ASSESS ONLY (no code changes outside `raphy/`). No `<promise>COMPLETE</promise>`.

## Scope

Hot spots from `git log --oneline` (~40 commits back from `696e19f8f`):

1. **Durable HITL resume across kernel restart** (`f07a82f01`, 10-10 21:47) — new
   `lca/plugins/transport/webserver/carrier/runs/recovery.py` (365 lines),
   `lca/infrastructure/observability/chat_projection.py` (446 lines), plus
   `lifecycle.py` pause hook, `command_endpoints.py` lazy-recovery handlers,
   TS `reconcileRun` patch, seam note
   `docs/notes/implemented/seam/2026-10-10-hitl-restart-lazy-recovery.md`.
2. **Parallel tool execution cluster** — `ab2383495` (tool result attribution),
   `45d714991` (batch envelopes atomic verification), `e07666ef5` (output
   hygiene guard vs system prompt leakage), `8d1fe6f44` (hanging tool-call
   sanitize).
3. **RA-115~118 merge** (`49506dc8e`) + **seam read-side accessors** (`1d6a5924c`,
   `520c70086`, iter lanes) + `f07a82f01`'s `f07a82f01` sibling work.

Read: `CONTEXT.md` (domain vocabulary), `raphy/progress.txt` top
`## Codebase Patterns` (禁区 + prior learnings), seam note above,
`runtime-findings-20261007.md` (prior runtime baseline).

## 禁区 compliance

Respected: `lca/cognition/memory/` (frozen), `ralph/` Round 2 areas,
`gate_chain_strategy.py` (hands-off), `lca/infrastructure/computer/guest/preamble.py`
(user iterating), `lca/plugins/transport/webserver/` retirement-stub work
(lca-1000 territory). RA-106's `_model` private-probe residue noted but not
re-litigated here. Nothing written outside `raphy/`.

## Runtime verification (mandatory, executed)

Environment: the **worktree** checkout of main tip `696e19f8f` (NOT the dirty
main tree — agy/grok uncommitted work lives there; verification must read a
clean tree). `LLM_API_KEY=dummy`, MockLLMAdapter, real `Agent.run()` runs
(script `/tmp/raphy-runtime-verify.py`).

| Scenario | Result |
|---|---|
| (a) basic run reaches COMPLETED | **completed** |
| (b) run with a tool call (calc tool, 2-turn mock) | **completed** |
| (c) two sequential runs on one agent | **completed / completed** |

No crash, hang, or silent failure. No new P0/P1. RA-023's non-convergence fix
(not re-run this round; confirmed 10-08 05:15: non-convergent run returns a
failed Result). Prior P2s (`run(None)` TypeError, `NativeToolCall.arguments`
str error) remain deferred to iter-quality — not re-litigated.

## Friction walk (5 questions per area)

### Area A — HITL restart recovery (`carrier/runs/recovery.py`)

Read end-to-end: `recovery.py` (all 365 lines), `lifecycle.py` pause hook
(diff), `command_endpoints.py` `_validate_run_ownership`/`_run_is_recoverable`/
`_ensure_recovered_session` (diff), seam note. Test:
`tests/plugins/transport/webserver/test_run_restart_recovery.py`.

1. **Shallow-module sprawl?** The concept (pause → bundle → lazy rebuild on
   answer) forces bouncing between 4 modules: `lifecycle.py` (write hook),
   `recovery.py` (bundle + restore), `command_endpoints.py` (validate → recover
   → resume), `handlers/runs/session/builder/builder.py` (rebuild). Inside
   `recovery.py` the 7 functions are each deep enough; the sprawl is the
   **read/write validation asymmetry** (see Q5).
2. **Shallow modules?** `_recovery_locks_guard`/`_recovery_lock`: module-level
   asyncio-Lock dict — deletion test says it earns existence (concentrates the
   double-checked-lock race; deleting it moves the race into callers).
   `_pending_tools_calling`: ~15-line pure transform; deletion would move
   approval-shape knowledge into `_seed_recovery_facts`. Both survive the
   deletion test. `load_resume_bundle` is thin but it is the single read seam
   for the bundle — its thinness is the point.
3. **Pure functions hiding real bugs?** `_pending_tools_calling` is pure and
   covered; the real risk is orchestration in `_restore_from_bundle` (builder
   rebuild + status assignment + runnable re-assembly), which the happy-path
   test covers but no failure-injection test pins (Q5).
4. **Leaky seams?** `_restore_from_bundle` imports ~9 cross-seam modules via
   deferred imports (session runtime resume point, transport builder,
   harness memory events, emit, fact gateway, capability, execution env,
   runnable assembler). The deferred imports honestly flag layering strain —
   a god-orchestrator stitching plugin/runtime/contracts. Not actionable
   without a redesign; the honest local fix is the validation seam (RA-121).
5. **Untested / past-interface?** Tests pin happy path, missing bundle,
   skip-without-snapshot, write-failure containment. **Gap**: no corrupt-bundle
   test — and the code path for it is silent degradation: write side guards
   (`locator`/`approval_request`/`approval_id` checks, all fail-silent skip),
   but `load_resume_bundle` only checks `data.get("run_id") != run_id`, then
   `_restore_from_bundle` fills every missing field with `str(... or "")`
   silent defaults and `_seed_recovery_facts` no-ops on empty `approval_id`.
   A corrupt bundle builds a zombie `WAITING_INPUT` session that fails later
   with confusing errors. → **RA-121** (friction: testability gap / no
   locality of validation).

### Area B — effect attribution + source_verify marker

Read end-to-end: `lca/nodes/concept/effect/execute.py` (all 514 lines),
`lca/nodes/_resolve.py`, `lca/infrastructure/source_verify/registry.py`,
`lca/infrastructure/source_verify/claims.py`, `think/llm/persist.py` (turn/step
comparison), `run_session_writer.py` impl, `simple_body.py`/`tool_journal.py`
comparison callers.

1. **Shallow-module sprawl?** The attribution chain `_batch_rows` →
   `_owed_rows` → `_row_surface` → `_append_tool_result_surface` lives in one
   module; understanding "does the model see every call's result" requires
   only this file + `tools_meta_of` + `OBS_TOOL_RESULTS`. No sprawl — RA-033/
   ab2383495 left it well-localized.
2. **Shallow modules?** `_batch_rows`/`_owed_rows` are small but each owns one
   non-trivial rule (batch packaging read, fill-missing-calls). Deletion test:
   deleting them moves the attribution rules into `_append_tool_result_surface`
   — but the call chain is 4 deep for a ~100-line concern; not a finding.
3. **Pure functions?** `_batch_rows`/`_owed_rows` are pure and pinned by
   `tests/nodes/test_effect_execute_batch_attribution.py` (172 lines). The
   real bugs lived at the call seam (writer binding, decision fill-in) and
   the tests pin those. No gap.
4. **Leaky seams?** Two findings:
   - `execute.py:125` and `execute.py:295` each hand-roll
     `getattr(context.runtime, "state", None)` — the exact two-shape probe
     RA-118 converged into `lca/nodes/_resolve.py` as `resolve_runtime_state`.
     RA-118 gave `resolve_writer` a `required` flag but left
     `resolve_runtime_state` raise-only, so the two fail-soft probes in
     `execute.py` still can't use it (and they miss the mapping-style `.get`
     fallback the seam implements). → **RA-119** (shallow probe sprawl).
   - `source_marker()` (`registry.py:97`) produces `[source:<id>]` via f-string
     while `_EXPLICIT_MARKER` (`claims.py:21`) consumes it via an independent
     regex — two independent definitions of one wire format. Same drift class
     as RA-116 (prompt markers), where drift already happened once in
     practice. `test_source_verify.py:43` pins the format text, but nothing
     forces producer and consumer to stay in sync. → **RA-120** (leaky seam).
5. **Untested / past-interface?** Attribution is well pinned. Marker
   round-trip (`source_marker` → `extract_citations`) is tested at the text
   level but through the interface of each half separately — the pairing is
   not pinned. Covered by RA-120's acceptance criteria.

### Area C — chat projection (`observability/chat_projection.py`)

Read end-to-end (all 446 lines) + `test_chat_projection.py` (188 lines).

1. **Shallow-module sprawl?** No: one module owns Postgres row writes for the
   chat UI; concepts are identity, ask card, final reply, card clearing.
2. **Shallow modules?** The module is a set of ~12 functions each with a clear
   SQL operation; interface (function per write) matches implementation
   depth. `lobehub_database_url`'s hand-rolled `.env` line parser is a
   mini-ritual but it exists once — deletion would move env-resolution
   elsewhere, not concentrate it. Not a finding (no failure evidence).
3. **Pure functions?** `_upsert_message`, `final_message_id`/`ask_message_id`
   are pure helpers; real bugs hide in `resolve_identity`'s
   read-modify-write against the messages table — but the docstring documents
   the deliberate reason (session often knows only `solo`; the topic row is
   the truth). Speculative without failure evidence → declined, noted below.
4. **Leaky seams?** Raw SQL + `psycopg`/`psycopg2` dual import is honest
   infrastructure; `_connect`'s adapter ritual is contained. The
   `write_pending_question` row-shape (message row + message_plugins row)
   must match what LobeHub's client renders — but the seam note + browser
   e2e verification in `f07a82f01` cover it. Not a finding.
5. **Untested?** `test_chat_projection.py` pins id functions and upsert
   SQL against a fake cursor. **Gap (minor)**: the
   `asyncio.to_thread(_with_connection, _write)` + try/except log wrapper is
   copy-pasted in `persist_waiting_projection` and `persist_terminal_projection`
   — exactly two occurrences, i.e. a real seam by this repo's own rule
   ("one adapter = hypothetical seam, two = real"). → **RA-122**
   (secondary duplication class).

## Duplication scan (secondary, after the friction walk)

Mechanical line-level scan of the hot files found no literal clusters beyond
the chat_projection pair (RA-122). Checked and declined: `_PHASE_ALIAS_OF`
(single cluster, RA-109 pinned), `CacheConfig(enabled=False)` (single site —
prior idiom, no story), `_revision_of` two sites (needs a third — prior idiom,
no story).

## Self-grilling (per candidate)

### RA-119 — converge two `getattr(context.runtime, "state")` probes onto `_resolve.py`
- **Constraints**: `execute.py:125` fallback accepts only a real `AgentState`
  (`isinstance` check is load-bearing for legacy fixtures on the fail-loud
  path); `execute.py:295` (`_append_tool_result_surface`) uses fail-soft None.
  Zero behavior change on real runs; keep the isinstance gate at the call site.
- **Dependencies**: callers — none (module-private); callee — `_resolve.py`
  (already imported for `resolve_writer`). `persist.py`/`invoke.py` already
  use `resolve_runtime_state` fail-loud; adding `required` mirrors
  `resolve_writer`'s existing flag.
- **Shape of the deepened module**: `resolve_runtime_state(*, context, node,
  required: bool = True)`; `execute.py` calls with `required=False` and keeps
  its isinstance check. The mapping-style `.get` fallback comes free.
- **Test survival**: `tests/nodes/test_effect_execute_batch_attribution.py`
  (172 lines) pins attribution; the probes are exercised through the same
  tests. New: a test that a mapping-style runtime (`{"state": ...}`) resolves
  — currently silently None.
- **Deletion test verdict**: deleting one probe concentrates the two-shape
  ritual in the seam — earns existence. **Strength: Strong** (RA-118's own
  seam, one round old, still incomplete).

### RA-120 — single seam for the `[source:<id>]` marker format
- **Constraints**: wire format `[source:<id>]` is model-visible and pinned by
  `test_source_verify.py:43`; must not change the text. ProvenanceGuard
  semantics (ADR-0292 honesty boundary) unchanged.
- **Dependencies**: producer `registry.py::source_marker` (called from
  `execute.py`); consumer `claims.py::_EXPLICIT_MARKER` (called from
  `extract_citations`). Nothing else constructs/parses the literal.
- **Shape of the deepened module**: one module (registry.py is the natural
  owner) exposes `format` + `parse`/`match` — claims.py imports the parser
  instead of its own regex. Producer and consumer can never drift.
- **Test survival**: `test_source_verify.py` pins format text and
  `extract_citations` behavior — both must keep passing; add a round-trip
  test (format → extract → same source_id).
- **Deletion test verdict**: deleting the duplicate regex concentrates the
  format knowledge — earns existence. **Strength: Strong** (RA-116 proved
  this exact drift class breaks in practice).

### RA-121 — converge resume-bundle validation into the load seam
- **Constraints**: write side stays best-effort (pause path must never raise);
  read side returning `None` must keep mapping to the handler's existing 404
  path (`_run_is_recoverable` → "run not found"). Schema version
  `lca.run.resume_bundle/1` unchanged.
- **Dependencies**: writers — `lifecycle.py` pause hook calls
  `write_resume_bundle`; readers — `command_endpoints.py`
  `_run_is_recoverable`/`_ensure_recovered_session` via `restore_waiting_run`.
  `_BUNDLE_SCHEMA` check can ride along.
- **Shape of the deepened module**: a `validate_bundle(data) -> dict | None`
  seam in `recovery.py` shared by write (pre-write guard) and load; rejects
  missing/ill-typed `approval_request`, missing `approval_id`,
  missing/unparseable `resume_point` — fail-loud at the seam, never a zombie
  `WAITING_INPUT` session with silent `""` defaults.
- **Test survival**: `test_run_restart_recovery.py` pins happy path, missing
  bundle, skip-without-snapshot, write-failure containment. New: corrupt-bundle
  cases (bad `approval_request` type, missing `approval_id`, non-dict JSON)
  must return `None`.
- **Deletion test verdict**: concentrates the scattered `str(... or "")`
  defaults into one explicit contract — earns existence.
  **Strength: Worth exploring** (real silent-degradation path, no observed
  failure yet).

### RA-122 — converge the two `_with_connection`+thread+log wrappers
- **Constraints**: both wrappers are best-effort (log-and-continue); the log
  event names (`chat_projection_wait_failed` /
  `chat_projection_terminal_failed`) are observable — keep them as parameters.
- **Dependencies**: two callers inside the same module only.
- **Shape of the deepened module**: `_project_in_thread(fn, *, run_id,
  log_event)` — one seam for "run sync SQL on a thread, log failure".
- **Test survival**: `test_chat_projection.py` (188 lines) — behavior
  unchanged; keep both log-event names asserted.
- **Deletion test verdict**: concentrates the ritual; the two call sites keep
  their distinct payloads. **Strength: Worth exploring** (small, honest
  two-occurrence seam).

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality+leverage) | Strength |
|---|---|---|---|---|---|
| RA-119 | `lca/nodes/concept/effect/execute.py`, `lca/nodes/_resolve.py` | Two hand-rolled `getattr(context.runtime, "state")` probes duplicate the two-shape ritual RA-118 converged; they miss the mapping-style `.get` fallback and can't use the seam (raise-only) | Add `required: bool` to `resolve_runtime_state` (mirror `resolve_writer`); both probes converge to it with `required=False` | Locality: the runtime-carrier probe ritual lives in exactly one module. Leverage: every future fail-soft runtime read reuses the flag instead of hand-rolling | Strong |
| RA-120 | `lca/infrastructure/source_verify/registry.py`, `lca/infrastructure/source_verify/claims.py` | `[source:<id>]` format defined twice: producer f-string vs consumer regex — same drift class as RA-116 | One seam owns format + parse; consumer imports the parser | Locality: format knowledge in one place. Leverage: ProvenanceGuard citations can't silently break on a format edit | Strong |
| RA-121 | `lca/plugins/transport/webserver/carrier/runs/recovery.py` | Write-side guards vs read-side only-checks-`run_id`; corrupt bundle → silent `""` defaults → zombie WAITING_INPUT session | Shared `validate_bundle` at the load seam; corrupt → `None` (fail-loud, existing 404 path) | Locality: validation contract in one seam. Leverage: recovery failures surface at restore time instead of confusing later errors | Worth exploring |
| RA-122 | `lca/infrastructure/observability/chat_projection.py` | `_with_connection`+`to_thread`+log wrapper copy-pasted twice | `_project_in_thread(fn, *, run_id, log_event)` seam | Locality: the sync-SQL-on-thread ritual in one place | Worth exploring |

**Top recommendation**: RA-119 first — it completes RA-118's own seam one
round later (the pattern, the tests, and the `required` precedent all exist;
risk is near zero and the mapping-fallback is a latent correctness fix).
RA-120 is the highest-leverage correctness story (ProvenanceGuard citations are
a trust seam; drift there is silent). RA-121 and RA-122 are hygiene with clear
acceptance tests.

**Diversity quota**: satisfied — RA-119 (shallow probe sprawl), RA-120 (leaky
marker seam), RA-121 (testability/validation gap) are all friction-walk
findings; RA-122 is the only duplication-class story.

## Considered and declined

- `turn=step` in `execute.py`/`persist.py`: deliberate documented convention
  ("the old single node used `state.step` for both writer rows"); the turn
  seam itself is owned by RA-029. Not re-litigated.
- `resolve_identity`'s messages-table backfill (session knows only `solo`):
  documented deliberate; no failure evidence → speculative.
- `ProactiveScheduler.js` four stringly keys (`last_run_ms`/`attempts`/
  `next_retry_ms`/`last_error`): true friction, no failure evidence —
  speculative, stays unfiled per prior round's call.
- `_connect` psycopg/psycopg2 dual import, `.env` line parser in
  `lobehub_database_url`: single-occurrence rituals, no failure evidence.
- NativeToolCall wire getattr guards (prior round's note): type-guaranteed,
  no story.

## Assessment complete: 4 stories written, top is RA-119.
