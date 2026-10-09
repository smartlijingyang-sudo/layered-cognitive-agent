# Raphy Assessment — Round 14 (2026-10-09 10:30, branch raphy/arch-20261009-1008)

Fresh session. Baseline `0127c7120` (main tip; merge: raphy RA-051..RA-080 sweep).
Scope via YAGNI: last ~40 commits' hot spots are **skills package lifecycle**
(RA-051..080 just landed: doctor chain, overlay/frontmatter/disk/catalog/factory),
**CLI services** (`cli/commands` 12 commits), **kernel boot** (RA-054/070), and
**trace-coherence/v3 scenario pins** (iter-tests). Read: CONTEXT.md,
raphy/progress.txt `## Codebase Patterns` (top first), raphy/prd.json (RA-001..080
themes — no duplicate filings), skills/improve-codebase-architecture/SKILL.md,
relevant docs/adr/ (0119, 0175, 0185, 0232, 0248, 0251, 0268). 禁区 respected:
preamble.py (user in-flight), gate_chain_strategy.py (other's work, not even read),
ralph Round 2 territory (DecisionGates/Ingest/ContextFiles shims/Read Runs
micro-dirs/lca/cognition/memory//infrastructure/tools/assistant/), lca-1000 active
migration (contracts/event.py PILOT, webserver retired stubs), typed ports /
delegation cache (iter lanes in flight).

Three friction-walk zones delegated to fresh-session subagents (ASSESS ONLY, read-only,
end-to-end reads, 5 questions mandatory each); runtime verification run directly
with the R13 probe (adapted to this worktree). This file synthesizes their reports
with self-grilling per candidate.

## Friction walk

### Area A — lca/agent/ + lca/runtime/loop/ + lca_kernel/boot/ + lca/nodes/ (zone: agent core runtime)

Read end-to-end: cognitive_agent.py (397), team_handle.py (166), member_invoke.py (96),
orchestration_registry.py (39), runtime_loop.py (605), runtime_lifecycle_emitter.py (141),
runtime_lifecycle.py (16), agent_runtime/phases.py (32), boot.py (559), lifespan.py (115),
stages.py (40).

1. *One concept, many modules?* YES — "start one fresh run" crosses ~8 modules
   (CognitiveAgent.run → runtime_loop.run → vocal runtime_wiring → settle_guard →
   capability_bindings → auto_review gate → BoxAccessor → skills activation bridge).
2. *Shallow?* YES — `_publish_terminal_event` (3-line delegate); `_RunEventSessionBinder`
   Protocol defined **verbatim twice** (cognitive_agent.py + team_handle.py);
   `CognitiveAgent`'s 16 read-only `self._bindings.*` delegates are factual adapter
   surface (nodes/composer read runtime.brain ×8) — honest, not filed.
3. *Pure fns, bugs in callers?* YES — `_capture_resume_memory` wraps a pure fn in
   try/except fail-soft: the swallow decision lives at the call site, not in the fn.
4. *Leaky seams?* YES, strongest: `_run_driver` uses `getattr(vocal_ctx.gate,
   "is_awaiting_widget", lambda: False)()` + `m.get("type")=="widget"` +
   `latest_widget.get("message_id")` — vocal internals in the generic run driver;
   same sniff repeated in result_projection.py:193 ("two adapters = real seam").
   Second: lifespan.py docstring promises "no plugin/cli implementation details"
   while `_lifespan` hard-imports `...webserver.handlers.runs.terminal.handoff_dispatch.LcaRunHandoffDispatcher`
   and starts CronDaemonService — docstring-vs-code verbatim contradiction; plus
   `getattr(ctx, "lock_dir", None)` duck-reads and a fail-soft `except Exception`
   swallowing daemon-start failure in an otherwise fail-loud boot.
5. *Testability?* YES — `CognitiveRuntime.run()`'s ~120-line composition corridor
   (bridge install, session writer, vocal resolve, auto-review, capability bindings)
   has no seam: only a full run reaches it; its top-level imports are empty with
   10+ deferred imports inside `run()` — the static interface says nothing about
   the 10 subsystems it touches. Also `transcript_features` fallback derivation
   (~15 lines in `_run_driver.finally`) belongs to its only consumer
   `evaluate_initiative` (no locality) and is untestable without a full run.

### Area B — lca/cognition/ (excl. memory/) + lca/contracts/ (excl. atoms/artifact/state.py, event.py)

Read end-to-end: body/ dispatch chain (simple_body, tool_batch_executor,
execution_policy, tool_wire_gate, guard×3, internal/_retry_classification,
actions×3, contracts/cognition/body/tools/registry.py,
protocols/act/tool/batch_execution.py); prompt assembly (sections/types,
sections/assembler, brain/prompt/skill_router, models/cognition/prompt_assembly.py,
perception.py, brain/pipeline/context_manifest.py); atoms/mechanisms (seam.py,
plugin.py, registries.py, exhaustive.py — all honest leaf tools, **no filing**).

1. *One concept, many modules?* YES — "how is a tool batch scheduled" crosses
   protocol → execution_policy → tool_batch_executor → registry.py (effects
   taxonomy), two trees (contracts/cognition vs lca/cognition); "why this
   template" crosses skill_router → prompt_assembly → assembler → reasoner → harness.
2. *Shallow?* YES — `tools/tool_registry.py` (26-line NamedRegistry alias),
   `actions/action_registry.py` (61-line alias dict): deletion test = just moves,
   stable registration seams — not filed. `types.py` single-field wrapper
   dataclasses (ManifestClock/Subtasks/Artifacts) — noted, folded into RA-093.
3. *Pure fns, bugs in callers?* YES — `missing_arguments_block_observation(decision,
   tool_registry: object)` hides the real contract in `object`; `_catalog_skill_count(catalog:
   object | None)` — failure modes live in what callers pass, not the counting.
4. *Leaky seams?* YES — `ToolBatchExecutor._resolve_tool_effects` getattr-chains
   through `tool.manifest.api[0].effects` (manifest internals known to the
   executor); `select_mode_with_audit` getattr-probes a capability the protocol
   never declares; assembler's catalog seam is typed `object` while contracts
   has `BrainPromptCatalog`; `_dispatch` switches on bare strings "pure"/"stateful".
5. *Testability?* YES — PARALLEL-selection behavior only testable through
   `select_mode_with_audit` (protocol `select_mode` can't express it); the audit
   channel's contract is unwritable; wire-block observation shape asserted per-gate.

### Area C — lca/infrastructure/cli/ (excl. doctor) + computer/ (excl. preamble) + tools/ (excl. assistant) + env/ + assistant/ + path/

Read: cli.py, commands/__init__.py, steps.py (293), service.py (~450),
services/*, tools/_shared.py, tool/invocation_scope.py, seam/file_ref_args.py,
box_accessor.py (62), box_sandbox_adapter.py (282), box_port.py (60),
env/bootstrap.py, path/locator.py, path/policy.py.

1. *One concept, many modules?* YES — `lca-ops lobehub restart` crosses 4 layers,
   two of them string-keyed (`step_map` dict → `register_step` global registry via
   cli.py side-effect imports).
2. *Shallow?* YES — 14 of 17 steps are 6–10-line verb→method translations;
   ServiceRegistry is 7 dict one-liners; two `__init__.py` re-export barrels.
   Deletion test: just moves — but the *capability gap* they paper over is real (RA-084).
3. *Pure fns, bugs in callers?* YES — `daemon_ensure` (steps.py:113) calls
   `CliShippingService`'s **private** `_cli_deployed()`/`_cli_source_changed()`
   cross-module: the real coupling (this service ships a CLI) lives in the caller's
   isinstance-narrowing + private calls, not on the interface.
4. *Leaky seams?* YES, strongest: **box sandbox boundary has two owners and
   diverged correctness** — `BoxAccessor.resolve_path` uses
   `str(resolved).startswith(str(root_dir))` (line 37: `/home/box2/evil` escapes
   `/home/box`), while `LocalBoxAdapter._resolve_safe_path` uses `relative_to`
   (correct); production traffic (tools/box/tool.py:67/124/168 via
   asyncio.to_thread) goes through the **vulnerable** one. Two byte-identical
   atomic-write copies, two identical sudo/su hard-gate copies (117 vs 229 lines),
   `self.adapter` written 3× never read (vestigial; BoxExecutionPort hypothetical
   on the sync path), `get_box_adapter` zero production callers.
   Second: `stack_heal` downcasts Service → KernelServeService for `.spawner()`
   with a TypeError guard apologizing for the dishonest seam.
   Third: file_ref_args seam claims "every path arg flows through resolve_path_arg"
   but tools/ has zero callers; only read_file wires it, write/edit/list bypass.
5. *Testability?* YES — stack_heal/daemon_ensure need fakes shaped like
   KernelServeService, not the Service protocol ("interface is NOT the test
   surface"); test_box_sandbox_adapter.py pins the **production-unused** path;
   BoxAccessor.resolve_path prefix behavior has no pin.

env/ (bootstrap constants, layered pure fns), path/locator.py (real multi-source
priority complexity), assistant/io.py (RA-056 digest depth) — read, honest depth,
**no filing**.

## Runtime verification (real run, LLM_API_KEY=<redacted>

Probe `~/workspace/raphy-probe-r14.py` (R13 script, worktree path updated):
- (a) basic run → COMPLETED
- (b) one-shot tool-call run → COMPLETED, marker file written by tool (tool truly executed)
- (c) two sequential runs on one agent → both COMPLETED
- (d) infinite-loop mock, max_steps=3 → FAILED, no exception leak
- (e) run(None) → TypeError at entry; NativeToolCall(arguments="str") → TypeError at construction

**No crashes/hangs/silent failures. No P0 runtime candidates this round.**

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-081 | computer/box_accessor.py, box_sandbox_adapter.py, tools/box/tool.py, box_port.py | Sandbox boundary has two owners; containment correctness diverged — production path has a prefix-escape bug | Converge to one gate (relative_to semantics); one atomic-write; one hard-gate copy; resolve vestigial adapter | Security invariants in one place; new box ops inherit the gate; tests pin the production path | **Strong** |
| RA-082 | agent/cognitive_agent.py, agent/team_handle.py | Run-lifecycle envelope hand-written twice, outcome-translation rules duplicated; binder Protocol defined verbatim twice | One envelope seam; carriers supply started/finished factories + outcome policy | Outcome matrix testable without driving agent AND team; 3rd carrier reuses the envelope | **Strong** |
| RA-083 | cli/service/service.py | Protocol types and 7 subprocess probing primitives share "the core abstraction"; service/ vs services/ naming collision | service.py → pure protocol; primitives → honestly-named probing deep module | Gotcha set discoverable + fake-testable; protocol half becomes pure interface | Worth exploring |
| RA-084 | cli/steps/steps.py, service.py, services/kernel/serve.py, services/daemon/daemon.py | Service protocol bypassed: isinstance downcast for .spawner(), cross-module private _cli_* calls; CliShippingService single-impl pseudo-protocol | Promote respawn + CLI-fingerprint to first-class protocol capabilities | Interface becomes the test surface again; future services hang capabilities on protocol bits | **Strong** |
| RA-085 | contracts/cognition/body/tools/registry.py | audit_tool_manifest_effects: zero callers, body returns immediately; __all__ missing 2 names; whitelist literal ×2 | Delete dead fn; complete __all__; one _AUDITED_DEFAULT_TOOLS constant | Module shows its real enforcement face; 5th audited tool can't diverge the two sites | **Strong** |
| RA-086 | cognition/body/tools/tool_batch_executor.py, contracts/.../registry.py | Executor re-implements select_effect inline (getattr through manifest.api[0], silent "external" fallback, duplicated closed-set check); registry's fail-loud select_effect has zero production callers | Converge on a registry-level tool-effects seam; executor deletes its helpers | Effects semantics (closed-set check + multi-API rule) in one place; taxonomy gains a 4th value in one edit | **Strong** |
| RA-087 | protocols/act/tool/batch_execution.py, execution_policy.py, tool_batch_executor.py | PARALLEL-decision logic lives in select_mode_with_audit — never declared by the protocol; one getattr probe + one implementer = hypothetical seam; third-party policies silently degrade to SEQUENTIAL | Declare the audit channel (extension protocol or enriched entry); isinstance dispatch, no probing | Future batch policies implement a declared interface; "policy needs which facts" lives in the protocol | **Strong** |
| RA-088 | lca_kernel/boot/lifespan.py, plugins/transport/webserver/server/server.py | make_lifespan docstring promises "no plugin/cli details" but imports the webserver dispatcher and starts the cron daemon; only production caller is server.py; fail-soft except in fail-loud boot | Cron start/stop → webserver plugin setup; make_lifespan → pure ASGI adapter | "Production needs cron" (ADR-0268) lives where its deps live; lifespan reusable without dragging cron along | **Strong** |
| RA-089 | runtime/loop/runtime_loop.py, runtime/projection/result_projection.py, protocols/vocal/protocol.py, infrastructure/vocal/gate.py | _run_driver getattr-bypasses the declared is_awaiting_widget(); two sites sniff gate internals ("widget"/"message_id"/"content" strings); swap the gate → silent no-op | Typed vocal projection seam (pending_widget_approval(), visible texts); impl by gate classes | Message-shape knowledge back with its owner; driver loses vocal vocabulary; gate projection unit-testable | **Strong** |
| RA-090 | runtime/loop/runtime_loop.py, application/initiative/hooks.py | transcript_features fallback derivation (~15 lines) lives in _run_driver.finally; sole consumer is evaluate_initiative; duck-reads prior_turns on a typed dataclass; untestable without a full run | Move derivation next to its consumer; driver = 3-line call | Role-counting rules get pure unit tests; initiative evolution never touches the run driver | **Strong** |
| RA-091 | cognition/body/tools/tool_wire_gate.py | Two wire-block Observation constructors share identical shape + verbatim model-facing guidance text; trigger conditions differ | One private constructor seam; gates supply condition+status+reason | Guidance text single-sourced; 3rd gate reuses the shape; extra-contract asserted once | Worth exploring |
| RA-092 | models/cognition/prompt_assembly.py, harness/memory/events.py, brain/prompt/skill_router.py, sections/assembler.py | "Why this template" has two vocabularies: closed SelectorDecisionPath (trace) vs bare str (SkillRouted); KeywordSkillRouter emits values outside the closed set | One vocabulary across channels; contract test: router-emitted values ∈ closed set | New routing strategies get consistent attribution for free; coerce fallback documented | Worth exploring |
| RA-093 | cognition/brain/sections/types.py, models/core/perceive/perception.py | kind→payload-type knowledge split 3 ways (docstring, 4 helpers' isinstance checks, ItemKind Literal); ContextManifest.by_kind exists but is bypassed by _manifest_items | Typed kind→payload accessor on the manifest; helpers converge | New kinds get one pairing point; payload-type contracts testable per kind | Worth exploring |
| RA-094 | cognition/brain/sections/assembler.py | Catalog seam typed `object` while BrainPromptCatalog exists; getattr duck-probing; _catalog_skill_count docstring promises 3 fallbacks, implements 1 | Type the seam; delete probing; fix doc (or add the fallback — explicit choice) | "What the assembler needs from catalog" moves from probe code into the type declaration | Worth exploring |
| RA-095 | infrastructure/tools/seam/file_ref_args.py, computer/sandbox/computer.py | Seam claims "every path arg flows through resolve_path_arg"; tools/ has zero callers; only read_file wires it (write/edit/list bypass) | Explicit choice: universal choke point, or honest read-path-only scoping | Path-resolution policy decided in one place; wiring scope pinned by tests | Worth exploring |
| RA-096 | agent/cognitive_agent.py | _enrich_run_context hand-rebuilds all 8 RunContext fields; the 9th field will be silently dropped | dataclasses.replace (keeping defensive copies of context_refs/extra) | "Fill default deadline" = one expression; future fields ride along | Worth exploring |

Diversity quota: duplication-class = RA-082, RA-085(whitelist part), RA-091 → 3/16, within limit.
Friction-walk-sourced (shallow/leaky-seam/testability): RA-081, RA-083, RA-084, RA-086,
RA-087, RA-088, RA-089, RA-090, RA-092, RA-093, RA-094, RA-095 — quota satisfied.

## Self-grilling (per candidate)

### RA-081 box boundary
- Constraints: ADR-0248 §3.2 (sandbox root, no sudo/su privilege); ADR-0251 decision 1
  (atomic write tmp+fsync+os.replace) — semantics unchanged; tools/box sync-via-to_thread
  shape kept; BoxExecutionPort contract + existing tests unbroken.
- Dependencies: tools/box/tool.py (4 tool classes + build_box_tools) → BoxAccessor;
  execution_environment.py lazily constructs BoxAccessor(); LocalBoxAdapter ←
  BoxAccessor.__init__ (vestigial) + tests; OnlyboxesBoxAdapter/get_box_adapter ← tests only.
- Shape: deep gate module — `contain(path) -> Path` (relative_to, escape → PermissionError),
  `atomic_write(path, content)` (ADR-0251 full set); BoxAccessor + LocalBoxAdapter become
  thin callers; `self.adapter` used or deleted.
- Test survival: test_box_sandbox_adapter.py pins adapter behavior (keep); NEW pin:
  BoxAccessor.resolve_path rejects sibling-prefix escapes — this is a behavior change,
  record as bugfix not pure refactor; tools/box call-path tests verify delegation parity.
- Deletion verdict: concentrates — security invariants converge in one gate.

### RA-082 run-lifecycle envelope
- Constraints: journal payloads (AgentRunStarted/Finished vs TeamRunStarted/Finished)
  byte-identical — tests/scenario/journal_* pin them; ADR-0037 (team handle = narrative
  edge); RA-046 (None-task fail-loud, agent-only); RA-023 (LoopObligationExceededError→failed,
  agent-only); binder Protocol from ADR-0186; todo-38 hot-path comment — do NOT merge the
  cheap active_publish_session() checks into one "optimization".
- Dependencies: callers of .run() are transport/composer (external behavior unchanged);
  internals call lca.loop.emit.cognitive.agent_spawn, observability, session.bindings.
- Shape: new module under lca/agent/ exposing the envelope: inputs = started-event
  factory + finished-event factory + execute callable + outcome-translation policy
  (agent flavor has Cancelled/LoopObligation branches, team flavor doesn't); output = Result.
- Test survival: team_1/test_team_modes_scripted.py, journal_0/*, carrier_terminal_observation —
  must stay green; NEW: table-driven outcome-matrix tests (success/cancelled/failed/
  loop-obligation × agent/team), currently unwritable.
- Deletion verdict: concentrates — the outcome-translation rules (exit paths × carriers)
  are the real complexity; converging them is not moving lines.

### RA-083 service.py split
- Constraints: 7 primitives' probing semantics (fallback order, timeouts, listening-only,
  health-body rule) — production experience, NOT ONE WORD changes; Service protocol public
  shape unchanged (registry/steps/services/* depend on it).
- Dependencies: primitives ← services/{lobehub,kernel/*,daemon,infra,onlyboxes},
  commands/runs/workflow.py, host_runtime/providers/user_cli.py, console.py, steps.py;
  protocol types ← registry.py, services/*.
- Shape: service.py shrinks to pure protocol (Service/ServiceStatus/HealthCheck/ServiceState
  + RA-084's disposition of CliShippingService); new module = "host probing with production
  gotchas", interface simple (pid_alive, http_ready), implementation deep — textbook deep module.
- Test survival: primitives currently integration-only; pure move, update import paths;
  NEW: fake-subprocess tests pin fallback semantics (lsof missing → ss).
- Deletion verdict: concentrates — gotcha set centralized; protocol half becomes pure interface.

### RA-084 Service capabilities
- Constraints: ADR-0119 decision 4 (lca-ops never manages LCA processes; kernel_serve does
  state/heal, heal may self-respawn); Service idempotency semantics; all lca-ops command
  behavior unchanged; do NOT invent a second CliShippingService impl for "generality".
- Dependencies: 17 register_step fns → ctx.registry (ServiceRegistry, built by
  services/__init__.py::build_registry) → protocol; commands/runs/services.py dispatches by
  string step name; protocol ← registry.py; CliShippingService ← steps.py + daemon.py;
  KernelServeService.spawner ← steps.py only.
- Shape: Service protocol grows explicit capability faces (respawn, deployment-fingerprint);
  steps.py zero downcast, zero private calls; mechanical wrappers may converge to single
  verb→protocol-method dispatch.
- Test survival: stack.heal/daemon.ensure behavior (spawn-failure actionable assembly,
  fingerprint logic) must hold; NEW: pure-protocol fakes drive stack_heal (downcast dead)
  and prove privates untouched.
- Deletion verdict: concentrates — two real capability concepts surface at the protocol
  layer instead of hiding in caller type-gymnastics.

### RA-085 registry cleanup
- Constraints: ToolEffectsDeclarationError fail-loud semantics unchanged; EFFECTS_UNSET
  sentinel purpose (distinguish "kwarg not passed" vs "explicit external") kept.
- Dependencies: only test_registry_effects.py; zero production callers of the dead fn;
  audit happens at bundle registration via register_manifest_with_audit.
- Shape: registry.py keeps 4 live public functions + 1 constant; whitelist becomes
  _AUDITED_DEFAULT_TOOLS.
- Test survival: test_registry_effects.py fully green (deleted fn had no callers;
  __all__ completion lets tests use normal imports).
- Deletion verdict: concentrates — deleting the dead fn makes the module's real
  enforcement face visible.

### RA-086 select_effect convergence
- Constraints: ToolEffects 3-value closed set is ADR-bound (new values need ADR — do not
  expand); PR-3 conservative default (unaudited → sequential) kept.
- Dependencies: _resolve_tool_effects only called by _select_mode_with_optional_audit;
  select_effect currently test-only.
- Shape: registry.py gains a tool-level effects-resolution function (Tool|manifest →
  ToolEffects); executor deletes its two private helpers.
- Test survival: test_registry_effects.py pins select_effect fail-loud;
  test_tool_batch_executor_parallel.py pins read+concurrent→PARALLEL; NEW: illegal-effects
  tool on the executor path raises (explicit, not silent sequential).
- Deletion verdict: concentrates — manifest-structure knowledge moves into the taxonomy module.

### RA-087 audit protocol
- Constraints: ToolBatchExecutionPolicy is a published extension point —
  select_mode signature frozen; ADR-0232 PARALLEL semantics (read + grant.concurrent) frozen;
  existing tests unbroken.
- Dependencies: executor.execute → policy; policy ← default_tool_batch_policy(),
  _resolve_tool_effects/_resolve_tool_grant; ReadOnlyToolBatchEntry flows executor↔policy.
- Shape: protocol gains an explicit audit-aware extension (or entry type enriched);
  executor branches on isinstance, not getattr.
- Test survival: parallel tests pin current behavior; NEW: protocol-targeted tests —
  a base-protocol-only policy gets explicit (non-silent) behavior.
- Deletion verdict: concentrates — "the audit channel exists" moves from scattered
  getattr/comments into the protocol definition.

### RA-088 lifespan cron
- Constraints: ADR-0119 decisions 3/4 (lifespan protocol shape; acyclic plugin/cli
  direction — this change makes the code match the ADR text); ADR-0268 (cron is a
  production-runtime need — behavior kept); ADR-0115 closure discipline (K3 untouched);
  _FakeCtx test semantics preserved, relocated.
- Dependencies: make_lifespan ← server.py:156 (production), test_cron_lifespan_integration.py,
  tests/support/webserver_app.py (mimics the protocol shape, not cron behavior — confirm);
  moved code needs MultiAssistantCronStore, CronDaemonService, get_lca_home, LcaRunHandoffDispatcher.
- Shape: make_lifespan(ctx) keeps signature; body = app.state.ctx mount + yield + shutdown
  cleanup (~15 lines, an honest protocol impl); cron start becomes a named step in
  server.py setup (input ctx/app, output app.state.cron_daemon).
- Test survival: cron integration test follows the behavior (plugin setup path);
  tests/boot/ must not notice cron.
- Deletion verdict: for lifespan = just moves (purer); for plugin = concentrates
  (composition returns where its deps live).

### RA-089 widget seam
- Constraints: ADR-0248 (vocal runtime + hard gate; INPUT_REQUIRED pause facts owned by
  RuntimeResultFinalizer ONLY — driver sets state + extra["approval_request"], never emits
  pause events, else double-append); approval_request {type,message_id,content,options} is a
  frontend contract (loop_drivers.py:130 → session.approval_request → projection.py:49) —
  byte-identical; VocalGateProtocol stays runtime_checkable-compatible.
- Dependencies: _run_driver (sole production writer of approval_request[type/widget]);
  result_projection final-text fallback; gate.py's two concrete classes; webserver session
  lifecycle (reads approval_request).
- Shape: 1–2 query methods on the vocal protocol (pending_widget_approval() →
  WidgetApproval | None, delivered visible texts); driver/projection consume the protocol;
  payload assembly stays in the driver (UI shape is a transport contract).
- Test survival: vocal gate unit tests; carrier_terminal_observation (approval_request→session
  chain); NEW: gate-projection shape tests + driver tests with stub-protocol gate.
- Deletion verdict: concentrates — the leak (driver sniffing gate internals) is deleted;
  shape knowledge concentrates with its owner.

### RA-090 transcript_features
- Constraints: RunContext is read-only input, not an output bus (per comments) — result
  goes to Result.extra["initiative_offer"]; ADR-0248 slice 8 (successful runs feed
  InitiativeHook transcript_features); extra["transcript_features"] caller-override semantics kept.
- Dependencies: _run_driver → evaluate_initiative; RunContext.prior_turns (typed);
  downstream readers of Result.extra["initiative_offer"] if any.
- Shape: lca/application/initiative/ gains the derivation fn: (prior_turns, extra_override)
  → features dict; driver = one call.
- Test survival: existing initiative_offer pins; NEW: pure unit tests (empty/mixed/override).
- Deletion verdict: concentrates — derivation rules move in with their only consumer.

### RA-091 wire-block seam
- Constraints: ADR-0047 trigger semantics (ToolCall native fields first, extra fallback);
  unexposed_tool_block_observation defer semantics untouched.
- Dependencies: callers = UseToolOperation (body/actions side); required_arguments tolerant
  schema reading kept.
- Shape: private _wire_block_observation(status, reason, ...) in tool_wire_gate.py;
  public signatures unchanged.
- Test survival: existing trigger-condition tests; NEW: parameterized test asserting both
  gates share the blocking-observation extra contract.
- Deletion verdict: just moves (two public fns → one private seam) — acceptable convergence.

### RA-092 decision vocabulary
- Constraints: PromptTrace.selector_decision_path is str-typed; reflection_events.py depends
  on _coerce_decision_path fallback; ADR-0175 D2 trace structure intact.
- Dependencies: reasoner.py ← normalize_selector_result; skill_router.py → spine envelope +
  SkillEventSink side channel; reasoner_prompt.py hook ← trace.
- Shape: shared decision-reason vocabulary module (or SkillRouted.decision_path folded into
  SelectorDecisionPath); router protocols document their reason-carrying.
- Test survival: test_skill_router.py keyword behavior; NEW: router-emitted values ∈ closed set.
- Deletion verdict: concentrates — "reason" gets one source of truth.

### RA-093 manifest accessor
- Constraints: ContextManifest is a cross-layer contract (perceive→reasoner) — additive
  only; ItemKind closed-set discipline kept; _manifest_items None-tolerance kept.
- Dependencies: types.py's 4 helpers ← stateful section impls; by_kind ← perception itself.
- Shape: typed accessor (payload_of(kind)) near perception.py; types.py helpers become thin
  wrappers or are deleted.
- Test survival: existing prompt-render tests; NEW: per-kind payload-type contract tests.
- Deletion verdict: concentrates — query+assert logic of four lookalike helpers in one place.

### RA-094 catalog typing
- Constraints: _catalog()'s INTENTIONAL swallow (not-ready → treated absent) is deliberate —
  not fail-loud; ADR-0185 AvailableSkillsReason derivation unchanged.
- Dependencies: catalog_provider injected by lca/plugins/prompts/assembler.py at composition;
  available_skills_count → PromptTrace → narrative/viewer.
- Shape: SectionManifestPromptAssembler.catalog_provider: BrainPromptCatalog | None;
  _catalog_skill_count takes the Protocol type, no getattr.
- Test survival: existing no-catalog→0 compat tests; NEW: bad-shape catalog behavior explicit.
- Deletion verdict: concentrates — seam shape owned by the type declaration.

### RA-095 path-arg seam
- Constraints: ADR-0121 PR-C /files/<aid> interception semantics; 3 input shapes +
  allowed_refs scoping; UnresolvedFileRefError→passthrough fallback — all unchanged.
- Dependencies: sole production caller _resolve_path_arg_or_passthrough (computer.py, lazy
  import vs cycles); test_file_ref_args.py; docstring's universal claim (currently false).
- Shape: (a) one path-entry fn shared by all guest ops; or (b) seam renamed/re-scoped to
  read-path. Either way: one place decides.
- Test survival: adapter tests kept; NEW: pin on the wiring scope (a or b).
- Deletion verdict: (b) = just moves (honest docstring); (a) = concentrates.

### RA-096 dataclasses.replace
- Constraints: keep defensive copies — list(context_refs), dict(extra) — naive replace()
  would alias originals and change downstream-mutation behavior; deadline short-circuit
  semantics unchanged.
- Dependencies: CognitiveAgent.run → _enrich_run_context; get_run_workspace() /
  effective_agent_wall_clock.
- Shape: 3–5 lines: replace(ctx, deadline=..., context_refs=list(...), extra=dict(...)).
- Test survival: existing deadline-propagation tests; NEW: no-dropped-field regression
  (assert against fields()).
- Deletion verdict: concentrates — the default-deadline rule becomes one expression.

## Top recommendation

**RA-081 first**: the box sandbox boundary is the only candidate where a *security*
bug rides the production path today (prefix-escape in BoxAccessor.resolve_path while
the correct relative_to implementation sits in the test-covered but
production-unused adapter) — locality failure = security failure, and the fix shape
is already proven in-tree. Runner-up: **RA-082** (run-lifecycle envelope) — the
largest structural duplication, and outcome-translation rules are the most
edit-fragile part of the agent core.

Dependency order for the optimize loop: RA-083 before RA-084 (split the module
before growing its protocol); RA-085 before RA-086 before RA-087 (registry cleanup
→ executor convergence → protocol promotion); RA-082 before RA-096 (envelope move
first, replace() after).

## Learnings for future iterations

- `getattr(x, "method", lambda: default)()` on a protocol-declared method is a
  review smell worth grepping for: it means the protocol exists but the caller
  doesn't trust it (RA-089) or the capability was never declared (RA-087).
- When two implementations of a safety invariant exist, check the *production*
  call path first: the tested one may be the unused one (RA-081 — test coverage
  on the wrong path is worse than no coverage because it looks safe).
- Docstring-vs-code verbatim contradictions (lifespan.py "no plugin details" vs
  hard import) are cheap to find and strong evidence — read the module docstring
  first, then check every claim against the body (RA-088).
- Assessment evidence goes stale within the same round: RA-083/086/087 share
  registry.py + executor; implement in dependency order and re-grep before each.
- `str(path).startswith(str(root))` is a containment bug until proven otherwise;
  `relative_to` is the correct idiom — grep the tree for more startswith-containments.
