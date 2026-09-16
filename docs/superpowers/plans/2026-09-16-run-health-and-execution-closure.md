# Run Health Report & Execution Closure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan PR-by-PR. Each PR is a separate gate. Use `superpowers:test-driven-development` to break each Task into 2–5 minute steps inside the executing session.
>
> **Plan granularity:** This file lays out the 3-PR structure with task boundaries, file lists, key code sketches, and verification gates. The TDD step-by-step (write failing test → run → implement → run → commit) is **deliberately not** spelled out at the line level here — the executor's TDD skill will do that inside each Task based on local context. The plan defines *what* must be true at each task boundary; the executor defines *how* the test→code→commit cycle happens step-by-step.

**Goal:** Replace LCA's per-consumer ad-hoc success/failure judgement (SOP, doctor, manifest, journal all derive their own signals from different EP subsets) with one typed `RunHealthReport` contract folded from 7 entry-point-discovered derivers, and fix the two execution-side causes (multi-call surface events, 1:1 fanout) that the contract will then report as healed.

**Architecture:** Fold-only observer on the spine SSOT. `RunHealthReport` (frozen, `extra="forbid"`) carries 7 `RunHealthCondition` entries (one per deriver) with `evidence_refs: tuple[EvidenceRef, ...]` pointing to specific spine events. 4 consumers (post_create_report, runs debug 5 layers, manifest.json, new `lca-ops runs health` CLI) all read the same report. Derivers are discovered via `importlib.metadata.entry_points(group="lca.health_derivers")` — adding a deriver = 1 file in `derivers/` + 1 entry-point entry in `pyproject.toml`. No COMPAT shim (per AGENTS.md §4).

**Tech Stack:** Python 3.11, Pydantic v2, `importlib.metadata` entry points, pytest, ruff, mypy --strict, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md` (346 lines, 15 sections, 22-item garbage inventory, 13 restart-safety/old-run/forward-compat guarantees). The plan argues from the spec; the executor reads both.

**Companion plan:** `/home/lichao/.grok/sessions/.../plan.md` (585 lines) — includes the full brainstorming trail, the 4 post-plan design refinements, and the §1 root-cause → PR-ownership table.

## Global Constraints

- All new contracts `BaseModel, frozen=True, extra="forbid"` per AGENTS.md §3 C13 D1.
- All derivers discoverable via `importlib.metadata.entry_points(group="lca.health_derivers")`; `run_health_fold.py` imports no specific deriver (k8s admission-webhook / OTel SDK Plugin pattern).
- `Condition.type` is `str` (open enum), not `Literal[...]`; the convention is documented in the contract docstring.
- No new spine EP introduced; `SPINE_EXECUTION_POINTS` unchanged.
- No COMPAT shim: deletions and replacements happen in the same PR. Where deletion must wait (manifest fields for backward read), explicit `@deprecated` + `delete-when: 2027-01-01` (k8s `resourceVersion` pattern).
- Per PR: 24h (PR-1, PR-2) or 7d (PR-3) telemetry window before next PR merges; see spec §10 Migration & rollout.
- Pre-push gate: `ruff check --fix && ruff format && lint-imports && mypy lca && pytest`; no `--no-verify`. Distinguish "introduced by this PR" from "pre-existing" lint-imports / check_package_contracts failures (AGENTS.md §6).
- ADR-0232 (PR-3) and ADR-0233 (PR-1) must be `Accepted` before their PR merges.

---

## PR-1: Run Health Contract & Consumers

**Risk:** Low. Observation-only; no cognition, no topology change. ~900 net add, ~200 net remove, 12 new files, 5 modified files, 6 tests directories.

**Closes:** B-2, B-4, B-5, B-6, B-7, B-8, B-9, X-3, X-4, C9-1, C11-1 (11 root causes). Garbage G-1..G-15, G-22 not applicable. Restart-safety R-1..R-5, Old-run O-1..O-5 (test gates).

### Task 1.1: Health contract types

**Files:**
- Create: `lca/contracts/observability/health/__init__.py`
- Create: `lca/contracts/observability/health/evidence_ref.py`
- Create: `lca/contracts/observability/health/condition.py`
- Create: `lca/contracts/observability/health/report.py`
- Test: `tests/contracts/observability/health/test_health_contract_types.py`

**Interfaces (consumed by 1.2/1.3):**
- `EvidenceRef(run_id, spine_path, event_id, execution_point, seq)` — frozen, `extra="forbid"`
- `RunHealthCondition(type: str, status: Literal["ok","degraded","failed","unknown"], reason: str, evidence_refs: tuple[EvidenceRef,...], observed_at: float)` — frozen
- `RunHealthSummary(conditions_ok, conditions_degraded, conditions_failed, conditions_unknown, by_type: dict)` — frozen
- `RunHealthReport(schema_version: "1.0", run_id, generated_at, conditions: tuple[RunHealthCondition,...], summary)` — frozen, hashable

**Key invariant (test):** `RunHealthReport(...)` is `__hash__`-able and `__eq__`-comparable; `conditions` is `tuple` (not list) to ensure determinism per AGENTS.md §3 C8.

**Verify:** `pytest tests/contracts/observability/health/test_health_contract_types.py` passes; `mypy --strict lca/contracts/observability/health/` 0 errors.

### Task 1.2: HealthDeriver Protocol + entry-point registration

**Files:**
- Create: `lca/contracts/observability/health/deriver.py` (Protocol)
- Modify: `pyproject.toml` (add `[project.entry-points."lca.health_derivers"]` table with 8 stub entries that point to Task 1.3's derivers)

**Interfaces:**
- `HealthDeriver` Protocol: `evaluate(events: list[SpineEvent]) -> list[RunHealthCondition]`
- 8 stub entry points: `perceive`, `think`, `act`, `tool`, `llm`, `reflect`, `remember`, `lifecycle` (note: `tool` covers sandbox as sub-rule per spec §15 G-21)

**Key invariant (test):** `importlib.metadata.entry_points(group="lca.health_derivers")` returns exactly 8 entries after `pip install -e .`; `_discover_derivers()` returns an 8-tuple.

**Verify:** `pytest tests/contracts/observability/health/test_deriver_protocol.py` passes; `python -c "from lca.plugins.observability.health.run_health_fold import _DERIVERS; assert len(_DERIVERS) == 8"` exits 0.

### Task 1.3: Eight derivers

**Files:**
- Create: `lca/plugins/observability/health/derivers/__init__.py`
- Create: `lca/plugins/observability/health/derivers/perceive_deriver.py` (`type="perceive"`)
- Create: `lca/plugins/observability/health/derivers/think_deriver.py` (`type="think"`)
- Create: `lca/plugins/observability/health/derivers/act_deriver.py` (`type="act"`)
- Create: `lca/plugins/observability/health/derivers/tool_deriver.py` (`type="tool"` + `type="sandbox"` as sub-rule; consumes `body.sandbox.enter`/`exit` for unmatched-pair detection)
- Create: `lca/plugins/observability/health/derivers/llm_deriver.py` (`type="llm"`)
- Create: `lca/plugins/observability/health/derivers/reflect_deriver.py` (`type="reflect"`, `unknown` if EPs absent)
- Create: `lca/plugins/observability/health/derivers/remember_deriver.py` (`type="remember"`, `unknown` if EPs absent)
- Create: `lca/plugins/observability/health/derivers/lifecycle_deriver.py` (`type="lifecycle"`)
- Test: `tests/observability/health/test_derivers/<one per deriver>.py` (4 status cases × 8 derivers = 32 tests)

**Status rules (per spec §10.4):**
- `perceive`: `ok` if `perceive.phase.fold.end` present, else `unknown`
- `think`: `ok` if `think.main` closed by `think.decision.repair` → `terminal.commit`; `degraded` if `decision.repair` outputs empty routing
- `act`: `ok` if `next_hint="fanout_ntom"` (post PR-3) or empty, `degraded` if `next_hint="fanout_1to1"`
- `tool`: `ok` if every `step.tool_call.record` has matching `step.tool_result.record` with `ok=True` AND every `body.sandbox.enter` has matching `body.sandbox.exit`; `degraded` if any result `ok=False`; `failed` if any call unmatched, sandbox unmatched, or any `runtime.diagnostic` with `output.ok=False`
- `llm`: `ok` if every tool_call in a turn has matching `role=tool` or `role=user`-with-tool-payload in next `llm.request.header`; `degraded` if some match; `failed` if zero match
- `reflect` / `remember`: `ok` if subgraph closed, else `unknown`
- `lifecycle`: `ok` if `kernel.run.stop.outcome="success"`, else `failed`

**Key invariant (test):** each deriver returns `list[RunHealthCondition]`; every condition has `len(evidence_refs) >= 1`; `evidence_refs[*].execution_point ∈ SPINE_EXECUTION_POINTS`.

**Verify:** `pytest tests/observability/health/test_derivers/ -v` — 28 cases pass; integration with audit runs shows the 3 audit runs fold into the expected conditions (regression baselines captured here).

### Task 1.4: Fold + factory wiring

**Files:**
- Create: `lca/plugins/observability/health/__init__.py`
- Create: `lca/plugins/observability/health/run_health_fold.py` (pure `fold_run_health(spine_path) -> RunHealthReport`)
- Create: `lca/plugins/observability/health/seam_provider.py` (Cordis seam)
- Create: `lca/plugins/observability/health/fold_provider.py` (provides `fold_run_health` callable)
- Modify: `bundles/observability-default.yaml` (3-line wiring: add seam + provider entries)
- Test: `tests/observability/health/test_run_health_fold.py` (36 cases: 8 derivers × 4 status + 1 entry-point discovery + 3 cross-aggregate)

**Key invariant (test):** `fold_run_health(spine_path)` is deterministic (same spine → same report modulo `generated_at`); `len(conditions) >= 6` for any non-empty run; `generated_at` is the only seam-injected non-determinism.

**Verify:** `pytest tests/observability/health/test_run_health_fold.py -v` — 36 cases pass; `./scripts/lca-ops profile resolve web-standard` still validates 15 plans (no regression).

### Task 1.5: post_create_report rewrite

**Files:**
- Modify: `lca/infrastructure/cli/commands/runs/runs.py` (rewrite `_build_post_create_report`; **delete** `_live_sop_run` / `_format_spine_event` / `_LIVE_SOP_EP_PREFIXES` / `_LIVE_SOP_EP_SUPPRESS`; update `_render_post_create_report` to drop EP-formatting refs)
- Test: `tests/infrastructure/cli/test_runs_create_health_*.py` (2 new tests: health-shape JSON + happy path no EP-format refs)
- Verify existing: `pytest tests/infrastructure/cli/test_runs_create_facade_path.py` — 12 existing tests still pass

**Key invariant (test):** `_render_post_create_report` output no longer contains any `phase_graph.node.start` / `step.tool_call` formatted lines; instead contains `health_summary.by_type` JSON.

**Verify:** `pytest tests/infrastructure/cli/test_runs_create_*.py -v`; `grep -r '_LIVE_SOP_EP_PREFIXES' lca/` returns 0; `grep -r '_format_spine_event' lca/` returns 0.

### Task 1.6: runs debug 5 layers read health

**Files:**
- Modify: `lca/infrastructure/cli/commands/runs/debug.py` (`_layer_summary`, `_layer_graph`, `_layer_events`, `_layer_diff`, `_layer_explain` all read `fold_run_health` instead of per-layer ad-hoc judgement)
- Test: `tests/infrastructure/cli/test_runs_debug_health_*.py` (5 tests, one per layer)

**Key invariant (test):** `_layer_explain` for the 3 audit runs returns `root_cause_present=True` (because of B-1's orphan drops and B-2's `output.ok` failures visible now); pre-change behavior was `no_root_cause`.

**Verify:** `pytest tests/infrastructure/cli/test_runs_debug_*.py -v`; re-run `lca-ops runs debug run_feb0f21ee770 --layer explain --json` and confirm `root_cause_present=true` + `llm.status=failed` + `tool.status=failed` (audit gap closed).

### Task 1.7: manifest close-path + G-12/G-13

**Files:**
- Modify: `lca/plugins/transport/webserver/read/runs/terminal/materialization.py:RunManifest` (add `health_summary: RunHealthSummary`, `health_hash: str`; mark `terminal_event_seq`/`ledger_high_watermark`/`ledger_summary` `@deprecated` with `delete-when: 2027-01-01`; **G-9** delete `_TERMINAL_EVENT_TYPES`; **G-12** add `_materialization_lock(run_id)` `flock` for C9 idempotency; **G-13** raise `ManifestFlushIncompleteError` on partial flush)
- Test: `tests/transport/webserver/test_materialization_*.py` (roundtrip + replay determinism + idempotency test + fail-loud test)

**Key invariant (test):** calling `record_terminal_materialization(session)` twice in a row leaves `manifest.json` mtime unchanged on the second call (idempotent); inject `flush_step_tree_artifacts` failure → `ManifestFlushIncompleteError` raised, manifest NOT written.

**Verify:** `pytest tests/transport/webserver/test_materialization_*.py -v`; re-run all 3 audit runs and confirm `manifest.json` for each is unchanged (md5 match pre-change).

### Task 1.8: emit_diagnostic root-cause fix (G-14)

**Files:**
- Modify: `lca/infrastructure/session/commit/fact_committer.py:169` (default `status: str = "failed"` → `status: str = "info"`)
- Modify: `lca/cognition/body/emit/tool_journal.py:131,213,318` (pass `status=DiagnosticStatus.{STARTED|SUCCEEDED|FAILED}` per operation)
- Modify: `lca/cognition/perceive/hub.py:62,78` (same)
- Test: `tests/infrastructure/session/test_emit_diagnostic_*.py` (default is "info"; 5 call sites pass explicit `DiagnosticStatus`)

**Key invariant (test):** `runtime.diagnostic` events for successful tool completions carry `payload.status="succeeded"` (not "failed"); `tool.start` carries `status="started"`; `tool.denied` carries `status="failed"`.

**Verify:** `pytest tests/infrastructure/session/test_emit_diagnostic_*.py -v`; re-run audit runs and confirm `runtime.diagnostic.payload.status` distribution is now mixed (not 100% "failed").

### Task 1.9: C11 escape hatch decision (G-15 + ADR-0233)

**Files:**
- New: `docs/adr/0233-c11-escape-hatch-policy.md` (decision: register `AgentRunFinished` as `spine.lifecycle.run_finished` AND remove the `_map_session_event` fallback to `"unknown"`; preferred direction per spec §15 G-15)
- Modify: `lca_kernel/events/persistence/persistence.py:108-126` (register the new EP in `_SPINE_EP_TO_CATEGORY`)
- Modify: `lca_kernel/events/payloads/spine.py` (`SPINE_EXECUTION_POINTS` if needed — closed-set expansion requires spec-level approval)
- Test: `pytest tests/lca_kernel/events/test_persistence_*.py` (every emitted EP is in closed set; `AgentRunFinished` no longer falls back to `"unknown"`)

**Key invariant (test):** `terminal_event_seq_from_file` now returns the actual seq instead of 0 (regression test against the 3 audit runs).

**Verify:** `pytest tests/lca_kernel/events/ -v`; ADR-0233 status `Accepted`; re-run audit runs and confirm `manifest.terminal_event_seq != 0`.

### Task 1.10: journal exceptions fallback removal (G-11)

**Files:**
- Modify: `lca/infrastructure/cli/commands/journal/exceptions.py:54-69` (delete the spine-scan fallback; sidecar file is the only source of `exceptions.count`)
- Test: `tests/infrastructure/cli/test_journal_exceptions_*.py` (returns 0 for runs without sidecar; does not speculate from spine)

**Verify:** `pytest tests/infrastructure/cli/test_journal_exceptions_*.py -v`; re-run `lca-ops journal exceptions run_feb0f21ee770 --json` and confirm `count=0` (not 38 from spine scan).

### Task 1.11: New CLI `lca-ops runs health`

**Files:**
- Create: `lca/infrastructure/cli/commands/runs/health.py` (CLI: `lca-ops runs health <run_id>`; reads `fold_run_health` and prints JSON)
- Modify: `lca/infrastructure/cli/commands/runs/__init__.py` (register the new subcommand)
- Test: `tests/infrastructure/cli/test_runs_health_cli.py` (3 happy + 1 error path)

**Key invariant (test):** for the 3 audit runs, `lca-ops runs health <run_id>` returns a `RunHealthReport` JSON with `by_type.llm=failed` (Run 1/2/3) and `by_type.tool=failed` (Run 3 only).

**Verify:** `pytest tests/infrastructure/cli/test_runs_health_cli.py -v`; manual `lca-ops runs health run_feb0f21ee770` shows the B-1 + B-2 issues now visible.

### Task 1.12: Old-run safety test (R-1..R-5, O-1..O-5, F-1)

**Files:**
- Create: `tests/integration/test_old_runs_still_readable.py` (5 tests O-1..O-5 against the 3 audit runs)
- Create: `tests/integration/test_restart_safety.py` (R-1..R-5: spawn kernel, hit `/health`, expect 200; resolve profile, expect 15 plans; fold an old run, expect same conditions as pre-merge)

**Key invariant:** the 3 audit runs (`run_3383288d63e7`, `run_3cf6e7c036b3`, `run_feb0f21ee770`) must fold to the same `conditions` and `summary` before and after PR-1 merge (modulo `generated_at`); their on-disk files (journal.json / manifest.json / spine.jsonl) must not be rewritten.

**Verify:** `pytest tests/integration/test_old_runs_still_readable.py -v`; `pytest tests/integration/test_restart_safety.py -v`; `md5sum` of all 3 runs' `spine.jsonl` pre-merge vs post-merge.

### PR-1 Commit Sequence

Per TDD discipline, each Task ends with:
1. Failing test committed (`test: add failing test for <task>`)
2. Implementation committed (`feat(<scope>): <task>`)
3. Refactor commit if applicable (`refactor(<scope>): <task>`)

Final PR-1 commit message: `feat(observability): introduce RunHealthReport typed contract; close 11 root causes`. Body lists the 22 garbage items closed (G-1..G-15 + the 4 entry-point registrations) and the 13 restart-safety/old-run/forward-compat guarantees met.

**PR-1 merge gate:**
- `./scripts/lca-ops lint-imports` no new failures
- `./scripts/lca-ops check_package_contracts.py` no new failures
- `ruff check --fix && ruff format && mypy lca && pytest` all exit 0
- `./scripts/lca-ops kernel-restart` exit 0 + `curl /health` 200
- ADR-0233 status `Accepted` (blocks Task 1.9, not other Tasks)
- 24h telemetry window: `health_summary.by_type` across 100+ runs; alert if >5% `conditions_failed`

---

## PR-2: SimpleBody Multi-Call Surface Completion

**Risk:** High. One cognitive-cycle function rewrite on the think→act mainline. ~30 net add, 1 modified file, 1 new test file.

**Closes:** B-1 (multi-call orphan drop). Garbage G-16..G-17.

**Dependency:** PR-1 must be merged (because PR-2's roundtrip test asserts `tool.status=ok` and `llm.status=ok` after fold).

### Task 2.1: BodySurfaceEventContract Protocol + failing roundtrip test

**Files:**
- Create: `lca/contracts/cognition/body/executor/contracts.py` (Protocol)
- Create: `tests/integration/test_body_surface_event_contract.py` (3 failing tests: `test_one_assistant_message_per_decision`, `test_n_tool_results_per_decision`, `test_orphan_drop_count_is_zero_for_multi_call`)

**Key invariant (test):** for `decision.tool_calls=[X, Y, Z]`, after `dispatch_tool_calls(decision)`:
- exactly 1 `surface/assistant_message` in the Session with `tool_calls=[X, Y, Z]`
- exactly 3 `surface/tool_result` in the Session, one per call
- `_drop_orphan_tool_results` keeps all 3 (no orphans)
- `orphan_dropped_count` counter stays 0

**Verify:** `pytest tests/integration/test_body_surface_event_contract.py -v` — all 3 fail initially (proves the gap).

### Task 2.2: dispatch_tool_call → dispatch_tool_calls

**Files:**
- Modify: `lca/cognition/body/executor/simple_body.py:159-300` (rename to `dispatch_tool_calls`; loop over `decision.tool_calls`; commit 1 assistant + N tool_results)

**Key code:**
```python
async def dispatch_tool_calls(self, decision) -> list[EffectReceipt]:
    self._session_writer.append_assistant_message(
        content=decision.response_text,
        tool_calls=decision.tool_calls,    # all N
    )
    receipts = []
    for call in decision.tool_calls:
        receipt = await self._execute_one(call)
        self._session_writer.append_tool_result(
            tool_call_id=call.call_id,
            content=_format_receipt(receipt),
        )
        receipts.append(receipt)
    return receipts
```

**Key invariant (test):** the 3 tests from Task 2.1 now pass; `tests/integration/test_orphan_tool_result_drop.py` still passes (the defensive orphan-drop remains; it just never has work to do for valid multi-call decisions).

**Verify:** `pytest tests/integration/test_body_surface_event_contract.py tests/integration/test_orphan_tool_result_drop.py -v` — all pass.

### Task 2.3: Orphan counter instrumentation (G-17)

**Files:**
- Modify: `lca/runtime/session/run_session_writer.py:62-78` (add `orphan_dropped_count: int = 0` to module state; increment in `_drop_orphan_tool_results`)
- Test: `tests/runtime/session/test_orphan_counter.py` (orphan count == 0 for valid multi-call)

**Verify:** `pytest tests/runtime/session/ -v`.

### PR-2 Commit Sequence

Final PR-2 commit: `fix(cognition): commit one assistant + N tool_results per decision; close B-1`. Body references spec §7 and PR-1.

**PR-2 merge gate:**
- All PR-1 gates still pass
- The 3 audit runs re-run manually; `lca-ops runs health run_feb0f21ee770` now shows `tool.status=ok` and `llm.status=ok` (audit gap closed end-to-end)
- 24h telemetry: `llm.status=ok` rate vs `llm.status=failed` rate (alert on regression)

---

## PR-3: `act.fanout` N:N + `ToolBatchExecutor` PARALLEL Default

**Risk:** High. Topology + executor policy change. ~120 net add, 5 modified files, 1 new ADR, 5 new test files, 1 new benchmark script.

**Closes:** B-3 (silent serial). Garbage G-18..G-22.

**Dependency:** PR-1 + PR-2 must be merged. ADR-0232 must be `Accepted` before merge.

### Task 3.1: ADR-0232 (closed-set expansion for `next_hint="fanout_ntom"` + `ToolBatchExecutionMode.PARALLEL` default)

**Files:**
- Create: `docs/adr/0232-act-fanout-n-to-n-and-parallel-tool-batch.md`

**Decision:** adopt `fanout_ntom` as the new healthy-fanout next_hint value; make `ParallelReadOnlyToolBatchPolicy` the default for tools declaring `effects="read"`; no profile rollback flag (revert PR if regression).

**Verify:** ADR status `Accepted` (review from Cognition + Runtime kernel teams).

### Task 3.2: Tool `effects` declaration (G-21)

**Files:**
- Create: `lca/contracts/cognition/body/tools/registry.py` (add `effects: Literal["read", "write", "external"]` to tool registry schema)
- Modify: `lca/plugins/tools/bash.py` (`effects="external"` — bash can read OR write depending on command; default to external)
- Modify: `lca/plugins/tools/file_write.py` (`effects="write"`)
- Modify: every tool plugin under `lca/plugins/tools/` (declare explicit `effects`; default `external` for unknown)
- Test: `tests/contracts/cognition/body/tools/test_registry_*.py` (every tool has explicit `effects`)

**Verify:** `pytest tests/contracts/cognition/body/tools/ -v`; `grep -l 'effects=' lca/plugins/tools/*.py` returns all tools.

### Task 3.3: `act.fanout` 1:1 → N:N (G-18)

**Files:**
- Modify: `lca/nodes/act/fanout.py:54-99` (accept `envelopes: tuple[CommandEnvelope, ...]` typed port; emit `next_hint="fanout_ntom"` when N>=2; backward-compat: single `envelope` input still works)
- Test: `tests/nodes/act/test_fanout_n_to_n.py` (4 tests: 0 envelopes, 1 envelope, N>=2 envelopes, back-compat single)

**Key invariant (test):** for 5 envelopes in, `next_hint="fanout_ntom"`; for 1 envelope, `next_hint="fanout_1to1"`; for 0 envelopes, `next_hint="fanout_empty"`.

**Verify:** `pytest tests/nodes/act/test_fanout_n_to_n.py -v`.

### Task 3.4: `act.envelope` 1 → N (G-20)

**Files:**
- Modify: `lca/cognition/body/executor/act_envelope.py` (produce N envelopes from N `decision.tool_calls`)
- Test: `tests/nodes/act/test_envelope_n_to_n.py` (2 tests: 1 tool_call → 1 envelope, 5 tool_calls → 5 envelopes)

**Verify:** `pytest tests/nodes/act/test_envelope_n_to_n.py -v`.

### Task 3.5: `ToolBatchExecutor` PARALLEL default (G-19)

**Files:**
- Create: `lca/cognition/body/tools/execution_policy.py` (replaces inline policy; `ParallelReadOnlyToolBatchPolicy` PARALLEL iff all read-only AND `grant.concurrent`)
- Modify: `lca/cognition/body/tools/tool_batch_executor.py:99-135` (default policy now `ParallelReadOnlyToolBatchPolicy`)
- Test: `tests/cognition/body/tools/test_tool_batch_executor_*.py` (3 tests: all read-only parallel, any write serial, mixed)

**Key invariant (test):** for 5 `runCommand` calls all with `effects="read"`, execution is parallel (5 `body.sandbox.enter` events with overlapping timestamps); for 1 `file_write` with `effects="write"`, execution is serial.

**Verify:** `pytest tests/cognition/body/tools/ -v`; re-run audit `run_feb0f21ee770` and confirm 5 `runCommand` complete in <200ms wall (vs 220ms serial pre-PR-3).

### Task 3.6: Sandbox pool (G-22) — only if needed for PARALLEL

**Files:**
- Create: `lca/cognition/body/sandbox/pool.py` (concurrent sandbox execution; max-concurrency = `min(8, os.cpu_count())`)
- Test: `tests/cognition/body/sandbox/test_pool.py` (4 tests: concurrent ok, max-concurrency cap, latency budget, error containment)

**Key invariant (test):** 5 concurrent `body.sandbox.enter` events all complete within 200ms; max-concurrency never exceeds pool cap; a sandbox exception in one slot does not poison the pool.

**Verify:** `pytest tests/cognition/body/sandbox/ -v`.

### Task 3.7: Latency benchmark (acceptance gate)

**Files:**
- Create: `scripts/bench/fanout_parallel.py` (5 `runCommand` calls; measure wall time)
- Modify: `scripts/bench/README.md` (add entry)

**Key invariant:** the 5 `runCommand` benchmark completes in <200ms (down from 220ms serial). Assert in `pytest tests/integration/test_benchmark_*.py` (run as a slow test, marked `@pytest.mark.slow`).

**Verify:** `python scripts/bench/fanout_parallel.py` exits with 0; `pytest -m slow` passes.

### PR-3 Commit Sequence

Final PR-3 commit: `feat(topology): N:N fanout + PARALLEL tool batch default; close B-3`. Body references ADR-0232 + spec §8 and PR-2.

**PR-3 merge gate:**
- All PR-1 + PR-2 gates still pass
- ADR-0232 status `Accepted`
- Latency benchmark <200ms
- 7d telemetry: `act.next_hint="fanout_ntom"` frequency; `tool.status=ok` rate vs `tool.status=failed`; zero profile rollback requests (revert PR if any)

---

## Cross-PR Invariant Sweep (per AGENTS.md §3)

| Invariant | PR-1 | PR-2 | PR-3 |
|---|---|---|---|
| C1 cognitive closed-set | OK (no new EPs) | OK | **ADR-0232** required for `fanout_ntom` next_hint |
| C4 Reducer single-write | OK (fold is read-only) | OK | OK |
| C5 capability monotonic | OK | OK | `grant.concurrent` is part of existing C5 schema |
| C7 control/observation separation | **OK** (health is observation) | OK | OK |
| C9 idempotency | **G-12 fix** | OK | OK |
| C11 event closed-set | **G-15 + ADR-0233** | OK | OK (next_hint is not an EP) |
| C13 information bloodline | **OK** (D1→D4 typed chain) | OK | OK |

---

## Per-PR File List Summary

| PR | New files | Modified files | Net LOC | Test files |
|---|---|---|---|---|
| PR-1 | 12 (3 contracts, 8 derivers, 1 fold, 1 CLI, 1 test dir entry) | 5 (runs.py, debug.py, materialization.py, fact_committer.py, persistence.py, exceptions.py, 2 tool_journal/perceive hubs, pyproject.toml, bundle yaml) | +900, -200 | 7 test files |
| PR-2 | 1 (contracts.py) | 1 (simple_body.py, run_session_writer.py) | +30, -10 | 1 test file |
| PR-3 | 4 (ADR, policy, pool, benchmark) | 5 (fanout.py, act_envelope.py, tool_batch_executor.py, registry.py, all tool plugins) | +120, -20 | 5 test files |
| **Total** | **17 new** | **11 modified** | **+1050, -230** | **13 test files** |

---

## Telemetry Windows (per spec §10)

| After PR | Wait | Check | Action |
|---|---|---|---|
| PR-1 | 24h | `health_summary.by_type` across 100+ runs; alert if >5% `conditions_failed` | Investigate unexpected failures |
| PR-2 | 24h | `llm.status=ok` rate (should jump from 0% to ~95% for multi-call runs) | Alert on regression |
| PR-3 | 7d | `act.next_hint="fanout_ntom"` frequency; latency benchmark; zero profile rollback requests | Revert PR if regression |

---

## References

- **Spec:** `docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md` (346 lines)
- **Companion plan:** `/home/lichao/.grok/sessions/.../plan.md` (585 lines; brainstorming trail)
- **Audit data:** `traces/runs/{run_3383288d63e7, run_3cf6e7c036b3, run_feb0f21ee770}/`
- **AGENTS.md:** §3 invariants C1, C4, C5, C7, C9, C11, C13; §4 no COMPAT shim; §5 delete-when; §6 verification matrix
- **ADR-0232 (proposed):** act.fanout N:N + ToolBatchExecutor PARALLEL default
- **ADR-0233 (proposed):** C11 escape hatch policy (`AgentRunFinished` registration)
- **ADR-0167:** spine SSOT — health is a fold view
- **ADR-0186:** Session SSOT — health does not write to Session
- **ADR-0192:** FactPlane — health is a fold observer
- **ADR-0219:** phase graph unification
- **ADR-0228:** typed port graph — PR-3 uses `envelopes: tuple[CommandEnvelope, ...]` typed port
- **k8s Conditions RFC 8294** (external): inspiration for open `type`, stable `reason`, 4-value status
- **OTel SDK Plugin** (external): inspiration for entry-point discovery
- **pluggy** (external): inspiration for registry-as-source-of-truth
- **k8s admission-webhook** (external): inspiration for declarative registration
