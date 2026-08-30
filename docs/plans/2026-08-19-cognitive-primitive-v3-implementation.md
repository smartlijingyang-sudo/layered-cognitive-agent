# Cognitive Primitive v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 14-PR cognitive-primitive-v3 constitution in `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`, with plugin-based configuration profiles covering Ralph Loop, Voyager, MemGPT, MetaGPT, LATS, Self-Improving, and Devin-style scenarios.

**Architecture:** Plugin-based (cordis runtime) over the existing 5-layer LCA. Each PR adds a closed-set primitive, removes one legacy leakage path, and lands with tests + CI gating. The six-step loop (`perceive → think → act → reflect → remember → stop`) is the closed cognitive set; four cross-cutting systems (Journal-as-Truth / Context Lifecycle / Execution Control / Collaboration Control) are 横切 services, not loop stages.

**Tech Stack:** Python 3.14, pydantic-settings, stdlib `dataclass(frozen=True)`, cordis (vendor/cordis), structlog, pytest.

## Global Constraints

- **5-layer one-way dependency** (`contracts → layer0 → layer1 → layer2 → layer3 → layer4`); enforced by `lint-imports`. No reverse imports.
- **Protocol-First** (ADR-0004): every Protocol implementer must explicitly inherit (`check_protocol_impl.py` gate).
- **Journal-as-Truth** (ADR-0037): model-visible ⇒ recorded. No second truth source.
- **Cognitive-loop set is closed**: modifications require ADR; default denial.
- **Plugins provide named factories**, not lists (`sensor.clock`, `body.simple`, `gate.loop-breaker`).
- **Feature flags** under `LCA_LOOP_*` env; default dual-write for transitions.
- **Tests**: per-PR `--no-cov`; full pytest on contract changes.
- **No temporary code**, no hacks, no placeholders — first-principles design only.

## PR Sequence (with dependencies)

```
PR1 ✅ (architecture conformance tests exist; verify dead-code cleanup)
PR2 (journal gaps + ContextManifest dual-write) ← PR1
PR3a (PerceiveHub Protocol + Memory adapter + fold property) ← PR2  [partial skeleton]
PR3b (Clock + workspace-artifacts named factories) ← PR3a        [partial skeleton]
PR3c (Reasoner consumes Manifest; drop live paths) ← PR3b
PR4 (delete loop_intervention; RepeatToolCallGate + PolicyFact)   [partial]
PR5 (ignore _emit; apply_activation; L4 runtime_factory) ← PR4
PR6 (Envelope + Approval events + gates read Manifest) ← PR3b, PR5
PR7 (MemoryPolicy + compaction shadow) ← PR2, PR3a
PR8 (/runs → followup; steer/inject; inbox-facts Sensor) ← PR3a
PR9 (TeamMessage MVP) ← PR6, PR3a
PR9b (Blackboard lease) ← PR9
PR10 (tear down _emit; events off Hook) ← PR5
PR11 (ADR-0002 full rewrite) ← PR10
PR12 (PluginMeta TypedDict + inspect) ← PR1, suggest PR10
PR13 (workspace-instructions Sensor) ← PR3a
PR14 (skill-catalog Sensor) ← PR3a
```

## Scenarios (post-PR14)

All scenarios are **configuration** combinations over the closed primitive set; no new primitives needed:

1. **minimal** — bash + str_replace_editor only
2. **standard** — full standard implementation
3. **code** — standard + CodeMode executor strategy
4. **cordis-creator** — standard + Composer.mount/unmount
5. **ralph-loop** — workflow automation (GoalStack + LoopBreaker + sandbox)
6. **voyager** — procedural memory + skill acquisition
7. **memgpt** — 4-layer memory + CompactionPolicy
8. **metagpt** — Team XOR + Graph coordination + roles
9. **lats** — Brain replacement + Critic + GoalStack
10. **self-improving** — Composer.mount + Profile evolution
11. **devin-style** — GoalStack + Ralph + Team + ApprovalToken
12. **research-debate** — Lead + 3 researchers + evidence-weighted synthesizer

---

## Phase A — Cleanup & Conformance (PR1)

- [ ] PR1.A.1 — Delete leftover `lca/plugins/guards/__init__.py` references; clean `bundles/web-app.yaml`
- [ ] PR1.A.2 — Rewrite `tests/harness/test_phase_c_middleware.py` to use new `RepeatToolCallGate` + `PolicyFact` (no `loop_intervention_mw`)
- [ ] PR1.A.3 — Update `tests/harness/test_runtime_middleware_integration.py` to remove `loop_intervention` from forbidden-pattern check (it's already gone)
- [ ] PR1.A.4 — Run `tests/test_architecture_conformance.py` until green

## Phase B — Journal + Context (PR2 / PR3a / PR3b / PR3c)

- [ ] PR2.B.1 — Verify `ContextManifested` / `PerceptionMerged` / `GateDecided` in catalog
- [ ] PR2.B.2 — Verify `RunStore.get` / `get_event` / `get_blob` exist
- [ ] PR2.B.3 — Confirm dual-write flag default = True
- [ ] PR3a.B.4 — `PerceiveHub` Protocol exists; `SequentialPerceiveHub` wired
- [ ] PR3a.B.5 — Memory adapter copy/diff algorithm in Hub (not Sensor)
- [ ] PR3a.B.6 — `NullPerceiveHub` available for tests
- [ ] PR3a.B.7 — `test_journal_reducer_apply_delta_equivalent_to_fold_events.py` green
- [ ] PR3b.B.8 — `ClockSensor` and `WorkspaceArtifactsSensor` named factories exist; Composer wires by §5.5 order
- [ ] PR3b.B.9 — Hub is sole emitter; `context_manifest.py` is pure builder only
- [ ] PR3c.B.10 — Drop `datetime.now` / `_with_artifact_context` / `_with_subtasks` from Reasoner
- [ ] PR3c.B.11 — Template drops `CURRENT_DATE` row when no clock item

## Phase C — Loop Discipline (PR4 / PR5)

- [ ] PR4.C.1 — `RepeatToolCallGate(DecisionGate)` exists, records `GateDecided` (warn only, no degraded_from)
- [ ] PR4.C.2 — `decision_gates/__init__.py` chain emits `record_gate_decided` helper
- [ ] PR4.C.3 — All workspace gates (`OfficeWorksSealer` / `TerminalRespondGate` / `ArtifactRespondInjector`) explicitly inherit `DecisionGate`
- [ ] PR4.C.4 — Reasoner reads `_with_loop_warning` removed; uses Manifest `policy_fact` item
- [ ] PR4.C.5 — `test_policy_fact_survives_into_next_manifest.py` green
- [ ] PR5.C.6 — `runtime_factory.py` in `lca/application/` (not in `lca-loop-cognitive`)
- [ ] PR5.C.7 — `_emit` return value ignored; `_sync_activated_skills` → `apply_activation`
- [ ] PR5.C.8 — `DefaultStopRule` pure function returning `StopDecision`; Runtime applies via `apply_stop`

## Phase D — Execution Control (PR6 / PR7)

- [ ] PR6.D.1 — `ExecutionEnvelope` Protocol / dataclass; `Body.act` requires envelope
- [ ] PR6.D.2 — `ApprovalRequested` / `ApprovalResolved` events emitted; idempotency_key
- [ ] PR6.D.3 — `RunStore.find_terminal_tool_invoked(key)` for resume dedupe
- [ ] PR6.D.4 — Gates read Manifest artifact items, never live `get_run_workspace()`
- [ ] PR6.D.5 — `OfficeWorksSealer` migrated to Body finalize
- [ ] PR7.D.6 — `MemoryPolicy.commit` returns `MemoryCommitResult`; `MemoryCommitted` journaled
- [ ] PR7.D.7 — `CompactionPolicy.compact` shadowed inside `Memory.perceive`; `ContextCompacted` journaled
- [ ] PR7.D.8 — `WORKING_MEMORY_KEYS` is single registry (no `working_memory_keys.py`)

## Phase E — Collaboration (PR8 / PR9 / PR9b)

- [ ] PR8.E.1 — `/runs` creation goes via Inbox `followup`; `CognitiveRunDriver.run(question)` removed
- [ ] PR8.E.2 — Steer/inject reach in-flight run via `inbox-facts` Sensor (journal-only)
- [ ] PR8.E.3 — L1 ↛ harness (importlinter forbidden)
- [ ] PR9.E.4 — `TeamMessagePublished` event + `team_message` tool (no new ActionType)
- [ ] PR9.E.5 — `TeamInboxSensor` named factory `sensor.team-inbox`
- [ ] PR9b.E.6 — Blackboard `read/append/CAS/lease`; no CRDT

## Phase F — Hook Tear-Down (PR10 / PR11)

- [ ] PR10.F.1 — `_emit` removed; protocol-boundary `record()` replaces
- [ ] PR10.F.2 — `StepCompleted` / `ActionDegraded` derived at Body.act / Brain.reflect, not Hook
- [ ] PR10.F.3 — `_middleware_bag` removed
- [ ] PR11.F.4 — ADR-0002 rewritten to match v3

## Phase G — Plugin Surface (PR12 / PR13 / PR14)

- [ ] PR12.G.1 — `lca/contracts/harness/plugin_meta.py` TypedDict (`PluginMeta`)
- [ ] PR12.G.2 — Inspect CLI / API returns derived capability graph
- [ ] PR12.G.3 — Composer does NOT reject unknown meta (until coverage threshold hit)
- [ ] PR13.G.4 — `WorkspaceInstructionsSensor` for AGENTS.md (named `sensor.workspace-instructions`)
- [ ] PR14.G.5 — `SkillCatalogSensor`; `SkillCatalogPublished.source = perceive`

## Phase H — Scenarios (Plugin Configs)

For each scenario:
- [ ] Profile YAML under `lca/profiles/` (or scenario file under `tests/fixtures/scenarios/`)
- [ ] Bundle YAML referencing closed primitive set only
- [ ] `tests/test_scenario_<name>.py` simulation harness: composes agent, runs a deterministic task, asserts structured behavior (no real LLM)
- [ ] All scenarios pass `tests/test_scenario_plugin_composition_e2e.py` (already exists)

Scenarios:
1. minimal
2. standard
3. code
4. cordis-creator
5. ralph-loop
6. voyager
7. memgpt
8. metagpt
9. lats
10. self-improving
11. devin-style
12. research-debate

## Phase I — Verification & Quality Gates

- [ ] `uv run ruff check --fix <changed> && uv run ruff format <changed>`
- [ ] `uv run lint-imports`
- [ ] `uv run mypy lca`
- [ ] `uv run pytest --no-cov -q <relevant>`
- [ ] Full `uv run pytest` green
- [ ] `uv run vulture lca --min-confidence 80` clean
- [ ] `python scripts/check_protocol_impl.py` green
- [ ] `python tools/ci/check_cognitive_loop_order.py` green
- [ ] `tests/test_architecture_conformance.py` green (PR1 canary)

## Phase J — Logs & Diagnostics (spec §24.5)

- [ ] `lca-ops diagnose <pattern>` for: model_not_seen / loop_stuck / memory_poisoned / approval_rejected
- [ ] `tests/test_diagnose_patterns.py` covers all 4 patterns
- [ ] Log schema: `trace_id` / `parent_trace_id` / `run_id` / `delegation_id` / `agent_role` / `turn` / `step` / `seq` / `ts` / `event_type` / `data` / correlation ids

---

## Architectural Decisions Locked In

D1-D25 from spec §29 — all in effect. Key for execution:

- **D2** Gate ⊂ Think; ExecutionControl ⊂ Act; **never** `_loop` steps.
- **D6** `PolicyFact` replaces `working_memory["loop_warning"]`; warning-only at threshold ≥3.
- **D7** Clock = journaled context item; no third clock.
- **D9** Composer assembles `SequentialPerceiveHub(sensors)`; plugins provide **named factories**.
- **D15** Incremental PR + dual-write + shadow; no big-bang.
- **D17** `Body.act` continues raising `ApprovalPendingError`; no union return type.
- **D19** Prompt persistence: (a) refs+digest default; (c) full text on `persist_full_prompt=True` or `verbosity=verbose`.
- **D22** Live path `apply_delta`; `fold_events` replays only PerceptionMerged/ContextManifested/MemoryCommitted/ContextCompacted subset.
- **D23** Hub folds `GateDecided` by `expires_at_step >= view.step`, NOT by `seq > head`.
- **D24** All user input via Inbox → journal → inbox-facts sensor → Perceive.
- **D25** TeamMessage MVP: one topic per team; `thread_id` for delegation sub-threads.

---

## File Map (per PR)

(Concrete file paths will be added per-PR as tasks start.)
