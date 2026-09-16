# Run Health Report & Execution Closure

| | |
|---|---|
| **Status** | Draft (brainstorming approved, post-4-design-refinements, awaiting writing-plans) |
| **Date** | 2026-09-16 |
| **Owners** | Observability + Cognition + Runtime kernel teams |
| **Scope** | Phase 1: typed health contract + 7 derivers (entry-point discovered) + 4 consumers. Phase 2: SimpleBody multi-call surface-event completion. Phase 3: `act.fanout` true N:N + `ToolBatchExecutor` PARALLEL default. One spec, three PRs, atomic per-PR review. |
| **Closes** | 9 observability/observability-and-execution silent-failure classes found during `run_feb0f21ee770` / `run_3cf6e7c036b3` / `run_3383288d63e7` audit (B-1..B-5 +4 follow-ons). Restores AGENTS.md §3 C7 (control/observation separation), C9 (idempotency), C11 (event closed-set), C13 (information bloodline closure) across the observability/execution surface. |

## 0. Motivation

A run that "looks healthy" must actually be healthy. The 2026-09-16 audit of three web-standard runs surfaced nine silent-failure classes that today pass `terminal_status=success` while the underlying state is wrong:

1. **B-1 history injection broken on multi-call.** `lca/cognition/body/executor/simple_body.py:159-300` commits exactly one `surface/assistant_message` per cycle regardless of `len(decision.tool_calls)`. `_drop_orphan_tool_results` (`lca/runtime/session/run_session_writer.py:62-78`) silently drops 4 of 5 tool results because no preceding `assistant.tool_calls[*].id` references them. `Run 3` ran 15 useless `runCommand` invocations across 3 turns because the model never received prior turn stdout.
2. **B-2 `runtime.diagnostic` always "failed".** `lca/infrastructure/session/commit/fact_committer.py:169` defaults `status="failed"` and all 5 call sites never override to `STARTED`/`SUCCEEDED`. Any downstream consumer that reads `payload.status` sees 32/32 "failed" even when `output.ok=True`. **Root-cause fix (PR-1):** change `emit_diagnostic` default `status="failed"` to `status="info"` (per `DiagnosticStatus` enum) AND update all 5 call sites to explicitly pass `status=DiagnosticStatus.STARTED` / `SUCCEEDED` / `FAILED` per operation semantics. The `tool_deriver` reads `output.ok` (not `payload.status`) so it works either way; but **leaving `payload.status="failed"` for successful operations is permanent garbage** that any future consumer will be confused by.
3. **B-3 `act.fanout` is `envelope → [envelope]` 1:1 pass-through.** `lca/nodes/act/fanout.py:54-99` docstring: *"PR-3.8.4:1:1 only wiring; N:N fanout leaves a follow-up PR."* `ToolBatchExecutor` default policy is `SequentialToolBatchExecutionPolicy`. 5 read-only `runCommand` calls run serially with 60–80ms gaps.
4. **B-4 `journal.phases[].exited_at/outcome` always `None`.** `_record_phase` (`lca/plugins/session/derivers/step_tree/journal_fold.py:417-435`) constructs `PhaseRecord` once and never closes it.
5. **B-5 `manifest.terminal_event_seq=0`, `ledger_high_watermark=0`.** `_TERMINAL_EVENT_TYPES` is the **Session/Catalog** event vocabulary; the running webserver profile writes **spine** EPs. The two vocabularies never intersect.
6. **B-6 SOP `_LIVE_SOP_EP_PREFIXES` is a 10-entry literal.** 7 EP categories never stream to the live operator. SOP reports 25–29% fewer events than the spine actually holds.
7. **B-7 `runtime.diagnostic` soft failures are unobservable.** `_FORCE_OFFLOAD_EPS = {"exception.caught"}` only writes sidecar for hard Python exceptions. SOP live stream doesn't carry `runtime.diagnostic`. The 32+ "failed" diagnostics in `Run 3` were invisible.
8. **B-8 `runs debug --layer explain` returns `no_root_cause` on a run with 32 soft failures.** The five debug layers only inspect `phase_graph.node.end.outcome` and `kernel.run.stop.outcome`.
9. **B-9 `_render_post_create_report` happy path silences all of the above.** Renders `sidecar total : 0 caught` for any run with `count==0`, exactly the case for soft-failure-only runs.
10. **X-3 / C9-1 `record_terminal_materialization` non-idempotent (AGENTS.md §3 C9 violation).** `atomic_write_text(manifest_path, ...)` does not check `manifest.json` already exists, has no inode lock, and `flush_step_tree_artifacts` does not protect "already flushed" state. Re-running materialization (e.g. crash recovery, repeated terminal hook) re-folds journal.json (potentially new hash) and overwrites manifest with a fresh one. **Fix (PR-1):** add `_materialization_lock` (per-run-id `flock`) inside `record_terminal_materialization`; check `manifest_path.exists()` and `manifest.health_hash == expected` before re-writing. This is a one-function change with a C9 roundtrip test.
11. **X-4 / C9-1 `manifest + journal` dual-source competition with no fail-loud.** `materialization.py:46-49` flushes step-tree (writes journal.json) then writes manifest. If `flush_step_tree_artifacts` fails, `flush_errors` goes to `manifest.extra` — but the manifest itself is still written. A consumer sees a manifest with `flush_errors` non-empty and no signal that the journal.json is broken. **Fix (PR-1):** `record_terminal_materialization` raises `ManifestFlushIncompleteError` if any `flush_step_tree_artifacts` returns errors; the manifest is only written on full success. AGENTS.md §2.3 forbids "为展示状态而顺便修复" — same principle.
12. **C11-1 `AgentRunFinished` EP falls back to `execution_point="unknown"`.** `lca_kernel/events/persistence/persistence.py:108-126` `_map_session_event` falls back to `"unknown"` when the session event type has no entry in `_SPINE_EP_TO_CATEGORY`. This is an **explicit escape hatch from the C11 closed-set** (the comment acknowledges "non-spine categories keep the legacy 'unknown' fallback"). Result: `terminal_event_seq_from_file` always returns 0. **Fix (PR-1):** either remove the escape hatch (rejection = `UnknownSpineExecutionPoint` raises) OR add `AgentRunFinished` to `_SPINE_EP_TO_CATEGORY` as `spine.lifecycle.run_finished`. This is a one-line registration OR a one-line deletion — but the choice has cascading effects, so it gets an ADR cross-ref: `ADR-0233-c11-escape-hatch-policy.md` (proposed).

**The pattern:** LCA's observability surface is **per-consumer, not per-fact**. Each consumer re-derives its own success/failure signal from a different EP subset, with no shared health contract. The 9 bugs are projections of one architectural gap.

**The fix is not to patch 9 spots.** Introduce one typed contract — `RunHealthReport` — that:
- declares a **typed Contract** (frozen Pydantic, `extra="forbid"`) for cross-boundary health facts, per AGENTS.md §3 C13;
- has an **open `type` field** (k8s Conditions RFC 8294 / OTel Attributes pattern) so new condition types require no contract change;
- declares the **closed status alphabet** (`ok | degraded | failed | unknown`) replacing today's binary "ok/fail" half-truths;
- **forces every consumer to fold from the same derivers** (discovered via `importlib.metadata.entry_points`, k8s admission-webhook / OTel SDK Plugin / pluggy pattern);
- ships **7 core derivers** (perceive / think / act / tool+sandbox / llm / reflect / remember / lifecycle) covering AGENTS.md §2.1 six-phase closed set plus 1 cross-cutting; adding an 8th is a 2-file change (deriver + `pyproject.toml` entry).

### 1 Architecture (PR-1)

```
spine.jsonl ──> RunHealthFold (pure)
                 ├── 9 derivers (perceive / think / act / tool / sandbox / llm / reflect / remember / lifecycle)
                 └── summary aggregation
                       │
                       ▼
                 RunHealthReport (frozen, extra="forbid")
                       │
        ┌──────────────┼──────────────┬───────────────┐
        ▼              ▼              ▼               ▼
   post_create    runs debug      manifest.json   lca-ops runs health
   report (SOP)   (5 layers)      (RunManifest    (new CLI)
                                  .health_summary)
```

### 2 D1–D4 conformance (AGENTS.md §3 C13)

| Letter | Surface | File | Notes |
|---|---|---|---|
| **D1** Definition | `lca/contracts/observability/health/{condition,report,evidence_ref}.py` | 3 frozen Pydantic models |
| **D2** Constraint | `SPINE_EXECUTION_POINTS` (unchanged) | No new EPs introduced |
| **D3** Transform | `lca/plugins/observability/health/{run_health_fold.py,derivers/*.py}` | Pure function chain |
| **D4** Consumer | 4 surfaces, all switch to fold-only | SOP, debug, manifest, new CLI |

### 3 PR-1 contract code

```python
# evidence_ref.py
class EvidenceRef(BaseModel, frozen=True, extra="forbid"):
    """Pointer to a specific spine event. Per AGENTS.md §3 C13, every
    cross-boundary reference MUST be a typed Contract (frozen, forbid-extra).
    Agents should use EvidenceRef to jump directly to the relevant spine
    event, not parse the reason text."""

    run_id: str
    spine_path: str       # absolute; matches RunSession.spine_path
    event_id: str         # spine event_id, e.g. "run_<id>:457"
    execution_point: str  # spine EP, must be in SPINE_EXECUTION_POINTS
    seq: int              # 1-based monotonic, from event_id suffix


# condition.py
class RunHealthCondition(BaseModel, frozen=True, extra="forbid"):
    """One observable fact about a run.

    The ``type`` field is intentionally an OPEN string (not a Literal)
    to follow the k8s Condition RFC 8294 and OTel Attributes pattern:
    the contract is the fold function, not the type vocabulary. New
    types are added by registering a new HealthDeriver entry point —
    no contract change, no consumer change, no fold change.

    The ``reason`` field is a stable identifier (k8s pattern), NOT
    a human-readable message. Agents and consumers MUST NOT parse
    the reason text. Use ``evidence_refs`` to jump to the spine.
    Example stable identifiers: ``"tool_orphan_dropped"``,
    ``"sandbox_enter_unmatched"``, ``"messages_incomplete"``.
    """

    type: str                          # OPEN; convention documented in docstring
    status: Literal["ok", "degraded", "failed", "unknown"]
    reason: str                        # stable identifier, NOT for parsing
    evidence_refs: tuple[EvidenceRef, ...]   # minimum 1
    observed_at: float                 # epoch_seconds, monotonic per type


# report.py
class RunHealthSummary(BaseModel, frozen=True, extra="forbid"):
    conditions_ok: int
    conditions_degraded: int
    conditions_failed: int
    conditions_unknown: int
    by_type: dict[str, Literal["ok", "degraded", "failed", "unknown"]]

class RunHealthReport(BaseModel, frozen=True, extra="forbid"):
    schema_version: Literal["1.0"]
    run_id: str
    generated_at: float
    conditions: tuple[RunHealthCondition, ...]   # tuple, hashable
    summary: RunHealthSummary
```

### 4 PR-1 deriver table

**Discovery**: derivers are registered via `importlib.metadata.entry_points(group="lca.health_derivers")`. The fold function does not import any specific deriver. Adding a new deriver = 1 new file in `derivers/` + 1 entry-point entry in `pyproject.toml`. No contract change, no fold change. (k8s admission-webhook pattern.)

| File | type | Consumes EPs | Status rules |
|---|---|---|---|
| `perceive_deriver.py` | `perceive` | `perceive.*.fold` | `ok` if `perceive.phase.fold.end` present, else `unknown` |
| `think_deriver.py` | `think` | `think.*.fold`, `think.llm.dispatch` | `ok` if `think.main` closed by `think.decision.repair` → `terminal.commit`; `degraded` if `decision.repair` outputs empty routing |
| `act_deriver.py` | `act` | `act.*.fold`, `act.fanout` next_hint | `ok` if `fanout_ntom` or empty, `degraded` if `fanout_1to1` |
| `tool_deriver.py` | `tool` + `sandbox` | `step.tool_call.record`, `step.tool_result.record`, `body.sandbox.enter`/`exit`, `runtime.diagnostic` (operation=tool.*) | `ok` if every call has a result with `ok=True` AND every sandbox enter has matching exit; `degraded` if any result has `ok=False`; `failed` if any call has no matching result, or any sandbox enter/exit is unmatched, or any diagnostic with `output.ok=False` (B-2 fix: read `output.ok` not `payload.status`) |
| `llm_deriver.py` | `llm` | `llm.request.header`, `llm.call.end`, `step.tool_call.record` (cross-ref) | `ok` if every tool_call in a turn has a matching `role=tool` or `role=user`-with-tool-payload message in the next `llm.request.header`; `degraded` if some match; `failed` if zero match |
| `reflect_deriver.py` | `reflect` | `reflect.*.fold` | `ok` if reflect subgraph closed; `unknown` if absent |
| `remember_deriver.py` | `remember` | `remember.*.fold` | Same as reflect |
| `lifecycle_deriver.py` | `lifecycle` | `kernel.run.stop`, `lifecycle.finally` | `ok` if `kernel.run.stop.outcome="success"`; `failed` otherwise |

**Sandbox merged into tool_deriver** because the tool execution lifecycle is: enter sandbox → execute → exit sandbox → record result. Sandbox enter/exit mismatch is a tool-sub-condition, not a peer condition. (A user reading the health report should not have to check two conditions for one root cause.)

### 5 PR-1 fold code

```python
# lca/plugins/observability/health/run_health_fold.py
def _discover_derivers() -> tuple[HealthDeriver, ...]:
    """Discover health derivers via Python entry points.

    Each deriver is registered in pyproject.toml under the
    ``lca.health_derivers`` group. The fold function does not import
    any specific deriver — it only knows the HealthDeriver Protocol.

    This mirrors k8s admission-webhook / OTel SDK Plugin / pluggy
    patterns: the registry is the source of truth, not the fold file.
    """
    return tuple(
        ep.load()()
        for ep in importlib.metadata.entry_points(group="lca.health_derivers")
    )

# Module-level cache; fold_run_health is called per-run, no churn.
_DERIVERS: tuple[HealthDeriver, ...] = _discover_derivers()

def fold_run_health(spine_path: Path) -> RunHealthReport:
    events = _read_spine_events(spine_path)
    conditions: list[RunHealthCondition] = []
    for deriver in _DERIVERS:
        conditions.extend(deriver.evaluate(events))
    return RunHealthReport(
        schema_version="1.0",
        run_id=_extract_run_id(events),
        generated_at=time.time(),
        conditions=tuple(conditions),
        summary=_summarize(conditions),
    )
```

**Properties (testable):**
1. Determinism: identical spine → identical report (modulo `generated_at`).
2. Closedness: `len(conditions) >= 6` for any non-empty run.
3. Evidence: every condition has `len(evidence_refs) >= 1`.
4. Traceability: `evidence_refs[*].execution_point ∈ SPINE_EXECUTION_POINTS`.

### 6 PR-1 consumer rewrites (sketched; not full code)

**post_create_report (`lca/infrastructure/cli/commands/runs/runs.py`):**
```python
def _build_post_create_report(run_id, base_url) -> dict:
    spine_path = _DEFAULT_TRACES_ROOT / "runs" / run_id / f"{run_id}.spine.jsonl"
    report = fold_run_health(spine_path)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "terminal_status": _spine_terminal_outcome(spine_path),
        "elapsed_s": round(time.monotonic() - start, 1),
        "health": report.model_dump(mode="json"),
        "health_summary": {
            "overall": _worst_status(report),
            "by_type": report.summary.by_type,
        },
    }
```

**Deletions in same PR (no shim, AGENTS.md §4):**
- `_LIVE_SOP_EP_PREFIXES` (10-entry tuple)
- `_LIVE_SOP_EP_SUPPRESS` (1-entry frozenset)
- `_live_sop_run` function
- `_format_spine_event` (75-line formatter)

**debug 5 layers:** replace per-layer ad-hoc judgement with `fold_run_health` + `report.summary` reads.

**manifest:** add `health_summary: RunHealthSummary` + `health_hash: str` to `RunManifest`. Old `terminal_event_seq`/`ledger_high_watermark` become informational, no longer the integrity source.

**manifest close-path:** wrap `record_terminal_materialization` body in a per-run-id `flock`; add `manifest_path.exists() && manifest.health_hash == expected` early-return; raise `ManifestFlushIncompleteError` if `flush_step_tree_artifacts` returns errors (no half-written manifest allowed). This restores AGENTS.md §3 C9 (idempotency) and C7 (no silent partial success).

**emit_diagnostic default:** change `fact_committer.py:169` `status: str = "failed"` → `status: str = "info"`. Update 5 call sites to pass `status=DiagnosticStatus.{STARTED|SUCCEEDED|FAILED}` per operation semantics. This is the **root-cause fix** for B-2 (current spec only patches the consumer; this fixes the producer so the field is no longer garbage for any future consumer).

**C11 escape hatch:** add `AgentRunFinished` → `spine.lifecycle.run_finished` to `_SPINE_EP_TO_CATEGORY` (or document the choice to keep the escape hatch with an ADR). Either way the spec resolves the open C11 violation.

**new CLI `lca-ops runs health <run_id>`:** single-line health answer with all 9 condition types and their evidence_refs.

### 7 PR-2 — SimpleBody multi-call

```python
# lca/cognition/body/executor/simple_body.py:159-300
async def dispatch_tool_calls(self, decision) -> list[EffectReceipt]:
    """One surface/assistant_message per decision; per-call surface/tool_result."""
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

Invariant: **1 surface/assistant_message (with all N tool_calls) + N surface/tool_result per decision cycle.** Enforced by new roundtrip test.

### 8 PR-3 — fanout N:N + PARALLEL

Three coordinated changes (see §2.6 above). New ADR-0232 required.

### 9 Verification matrix (per PR; full table in `docs/superpowers/plans/2026-09-16-run-health-and-execution-closure.md` §5)

### 10 Migration & rollout (full plan in `docs/superpowers/plans/2026-09-16-run-health-and-execution-closure.md` §6)

### 11 Non-goals

- No new spine EP
- No change to AGENTS.md invariants
- No change to ADR-0186/0191/0192/0193/0194/0195/0196
- No change to capability grants
- No change to Reducer
- No removal of file-sink on disk (SOP live stream is replaced; on-disk remains)

### 12 ADRs required by this spec

- **ADR-0233** (PR-1, before merge): resolve the `_SPINE_EP_TO_CATEGORY` escape hatch for `AgentRunFinished` (X-12 / C11-1). Either add the EP to the closed set (preferred) or document why the escape hatch stays.
- **ADR-0232** (PR-3, before merge): `act.fanout` 1:N topology + `ToolBatchExecutor` PARALLEL default + new `next_hint="fanout_ntom"` value. Closed-set expansion.

### 13 References


- Audit runs: `traces/runs/{run_3383288d63e7, run_3cf6e7c036b3, run_feb0f21ee770}/`
- AGENTS.md §3 (invariants C1, C4, C5, C7, C9, C11, C13)
- AGENTS.md §4 (no COMPAT shim)
- AGENTS.md §5 (delete-when for `@deprecated` manifest fields by 2027-01-01)
- AGENTS.md §6 (verification matrix)
- ADR-0167 (spine SSOT — health is a fold view)
- ADR-0186 (Session SSOT — health does not write to Session)
- ADR-0192 (FactPlane — health is a fold observer)
- ADR-0219 (phase graph unification)
- ADR-0228 (typed port graph — PR-3 uses `envelopes: tuple[CommandEnvelope, ...]` typed port)

---


### 14 Backward compatibility & restart-safety guarantee

After all 3 PRs merge and `lca-ops kernel-restart` runs, the system MUST satisfy the following guarantees. Each is a testable property, not an aspiration.

**Restart-safety (kernel boots clean after merge):**

| # | Guarantee | Verification |
|---|---|---|
| R-1 | `lca-ops kernel-restart` exit code 0 | `./scripts/lca-ops kernel-restart` |
| R-2 | Profile resolve returns 15 plans validated (same as pre-change) | post-restart report shows `profile=profiles/web-standard.yaml 15 plans validated` |
| R-3 | Health probe 200 with `4/4 plugin, fiber_count` non-zero | `curl http://127.0.0.1:8765/health` |
| R-4 | No new lint-imports / check_package_contracts / ruff / mypy failures introduced by any PR | compare pre-merge gate output to post-merge gate output; only "introduced by this PR" lines count |
| R-5 | New `lca.health_derivers` entry-point group is registered before any fold function call | bootstrap-time test: `import lca.plugins.observability.health.fold_provider` and assert `_DERIVERS` length == 7 |

**Old-run safety (the 3 audit runs `run_3383288d63e7`, `run_3cf6e7c036b3`, `run_feb0f21ee770` MUST stay readable after PR-1):**

| # | Guarantee | Verification |
|---|---|---|
| O-1 | `lca-ops runs debug <old_run_id> --layer summary` still works | exits 0, returns `RunHealthReport` JSON |
| O-2 | `lca-ops runs health <old_run_id>` returns the same health verdict as a fresh fold of the same spine | deterministic: same `conditions[*].reason` text, only `generated_at` differs |
| O-3 | `lca-ops journal trace <old_run_id>` still reads the old `journal.json` unchanged | `git diff traces/runs/<old_run_id>/journal.json` returns empty |
| O-4 | `traces/runs/<old_run_id>/manifest.json` is **not rewritten** by the post-merge code path | `manifest.health_hash` field may be None for old runs; `terminal_event_seq` / `ledger_high_watermark` still present and untouched |
| O-5 | `traces/runs/<old_run_id>/<old_run_id>.spine.jsonl` is **not rewritten** | `md5sum` of file matches pre-merge hash |

**O-1..O-5 are enforced by a new test `tests/integration/test_old_runs_still_readable.py`** that runs after each PR merge and re-validates all 3 audit runs.

**Forward-compatibility (the next 3 PRs MUST NOT depend on PR-1 being deployed):**

| # | Guarantee | Verification |
|---|---|---|
| F-1 | PR-2 merge does not require PR-1 deployed | CI runs `git checkout main && git merge feat/pr-2` without PR-1; tests pass |
| F-2 | PR-3 merge does not require PR-2 deployed | same |
| F-3 | Each PR's CI gate runs **without** the previous PR's branch | each PR has its own `verify-pr.sh` that re-derives the gate from `main` + this PR only |

### 15 Garbage inventory & clean-up commitments

Per AGENTS.md §4 (no COMPAT shim, no half-deletion) and §5 (delete-when for deprecations), this section is the **authoritative garbage inventory** for this design. Every item has a delete-when, an owner (the PR that removes it), and a verification test that it is gone.

**Slim-0-exception sidecar file is NOT garbage** — `lca/infrastructure/observability/spine/sinks/file_sink.py:352-374` deliberately creates an empty `<run_id>.exceptions.jsonl` for "slim:0" runs (no exceptions). This is a product decision (operators want a file to confirm "we checked for exceptions, there were none"). **Stays.** Justified here so it is not confused with garbage.

| # | Garbage | File:line | PR | Verification |
|---|---|---|---|---|
| G-1 | `_LIVE_SOP_EP_PREFIXES` (10-entry literal) | `runs.py:397-409` | PR-1 | `grep -r '_LIVE_SOP_EP_PREFIXES' lca/` returns 0 hits |
| G-2 | `_LIVE_SOP_EP_SUPPRESS` frozenset | `runs.py:409` | PR-1 | `grep -r '_LIVE_SOP_EP_SUPPRESS' lca/` returns 0 hits |
| G-3 | `_live_sop_run` function | `runs.py:449-528` | PR-1 | `grep -r '_live_sop_run' lca/` returns 0 hits |
| G-4 | `_format_spine_event` 75-line EP-exhaustive formatter | `runs.py:530-606` | PR-1 | `grep -r '_format_spine_event' lca/` returns 0 hits |
| G-5 | `_format_spine_event`'s callers (`_render_post_create_report` JSON branch + the human branch) | `runs.py:715+` | PR-1 | `_render_post_create_report` no longer references any EP |
| G-6 | `RunManifest.terminal_event_seq` Session/Catalog vocabulary mismatch | `materialization.py:135-167` | PR-1 | Field marked `@deprecated`; docstring note + `delete-when: 2027-01-01`; existing consumers not broken |
| G-7 | `RunManifest.ledger_high_watermark` same vocabulary mismatch | `materialization.py:140-152` | PR-1 | Same as G-6 |
| G-8 | `RunManifest.ledger_summary` hash of last 1 MiB spine (now replaced by `health_hash`) | `materialization.py:171-185` | PR-1 | Field marked `@deprecated`; `delete-when: 2027-01-01` |
| G-9 | `_TERMINAL_EVENT_TYPES` constant (`{AgentRunFinished, RunFinished, RunSealed}`) | `materialization.py:27` | PR-1 | Constant deleted; replaced by `spine.lifecycle.run_finished` lookup |
| G-10 | `_format_spine_event` for `kernel.run.stop` JSON branch (no longer needed; health contract subsumes) | `runs.py:_format_spine_event` | PR-1 | Same as G-4 |
| G-11 | `journal exceptions --json` fallback that scans spine for `execution_point=="exception.caught"` | `journal/exceptions.py:54-69` | PR-1 | Fallback path removed; sidecar file is the only source of `exceptions.count`. If a run has zero sidecar, `exceptions.count=0` is the truth and no fallback speculation. |
| G-12 | `record_terminal_materialization` no inode lock (C9 violation) | `materialization.py:78-85` | PR-1 | `_materialization_lock(run_id)` `flock` added; test `test_terminalization_is_idempotent` (re-run terminalize twice, second is no-op) |
| G-13 | `record_terminal_materialization` no fail-loud on partial flush (C7 + C9 violation) | `materialization.py:46-49` | PR-1 | Raises `ManifestFlushIncompleteError` if any `flush_step_tree_artifacts` returns errors; manifest is NOT written on partial success |
| G-14 | `emit_diagnostic` default `status="failed"` | `fact_committer.py:169` | PR-1 | Default changed to `status="info"`; 5 call sites pass explicit `DiagnosticStatus.{STARTED|SUCCEEDED|FAILED}` |
| G-15 | `AgentRunFinished → execution_point="unknown"` escape hatch (C11 violation) | `persistence.py:108-126` + `_SPINE_EP_TO_CATEGORY` | PR-1 | Either (a) `AgentRunFinished` registered as `spine.lifecycle.run_finished` AND escape hatch removed, OR (b) escape hatch documented as a deliberate C11 carve-out with ADR-0233. Decision in ADR-0233. |
| G-16 | `simple_body.dispatch_tool_call` (single-call) — only commits 1 `surface/assistant_message` + 1 `surface/tool_result` per decision | `simple_body.py:159-300` | PR-2 | Renamed to `dispatch_tool_calls`; loop over `decision.tool_calls`; commit 1 assistant + N tool_result |
| G-17 | `run_session_writer._drop_orphan_tool_results` — currently silently eats 4/5 tool_results in multi-call | `run_session_writer.py:62-78` | PR-2 | (Logic unchanged; the upstream bug is fixed so it never has work to do.) Add a runtime counter `orphan_dropped_count` and a test asserting it stays 0 for multi-call. |
| G-18 | `act.fanout` 1:1 pass-through (`envelope → [envelope]`) with comment "PR-3.8.4:1:1 only wiring" | `fanout.py:7-8, 85` | PR-3 | Accepts `envelopes: tuple[CommandEnvelope, ...]` typed port; emits `next_hint="fanout_ntom"` when N>=2 |
| G-19 | `ToolBatchExecutor` default `SequentialToolBatchExecutionPolicy` | `tool_batch_executor.py:99-135` | PR-3 | Default policy replaced by `ParallelReadOnlyToolBatchPolicy` (PARALLEL iff all read-only AND `grant.concurrent`) |
| G-20 | `act.fanout` consumers downstream — `act.dispatch`, `act.join` — that assumed 1 envelope input | `act_dispatch.py`, `act_join.py` | PR-3 | Updated to handle `envelopes: tuple`; backward-compat: if `envelopes` is absent, fall back to single `envelope` input |
| G-21 | Tool `effects` declaration (every tool hard-coded as `effects="external"` or unmarked) | `lca/plugins/tools/*.py` | PR-3 | Each tool declares `effects: Literal["read", "write", "external"]`; `bash` and `read_file`-like tools → `read`; `file_write` and friends → `write`; default unknown → `external` |
| G-22 | No profile flag `act_fanout_mode` rollback shim | (does not exist) | PR-3 | (Confirmed not to exist; PR-3 is a hard cutover.) |

**Total: 22 explicit garbage items, each with a PR owner and a verification test. PR-1 owns G-1..G-15 (15 items). PR-2 owns G-16..G-17 (2 items). PR-3 owns G-18..G-22 (5 items).**

**Reconciliation with §0 motivation's "9 root causes"**: B-1..B-9 + X-1..X-12 + C9-1 + C11-1 = 23 root-cause items; G-1..G-22 covers 22 of them. The 1 not-covered item is the B-2 *symptom* (consumer reading `payload.status`), which is closed by G-14 (the producer fix). Total = 23 closed.
