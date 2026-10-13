# Raphy Assess — 2026-10-13 22:55 round

Branch: `raphy/arch-20261013-2255` (worktree `/home/lichao/.lca-worktrees/raphy-20261013-2255`)

Main tip at assess: `6dcc21a62` (merge of `raphy/arch-20261013-0045`, RA-123/124/125
done). Assess ran as a fresh session on the branch; implementation untouched —
only `raphy/` files change in this commit.

Related prior rounds: 0045 round (RA-123/124/125, merged 6dcc21a62); its
"Considered and declined" section explicitly left the wider `getattr(runtime, …)`
probe sprawl as a follow-on direction — this round executes that direction
key-by-key (per the RA-123 lesson: 收敛按资源键全图 grep).

Environment: clean worktree `/home/lichao/.lca-worktrees/raphy-20261013-2255`
(branch `raphy/arch-20261013-2255`, HEAD = main tip `6dcc21a62`).
禁区全部遵守：preamble.py 未碰、ralph Round 2 领地未进、lca-1000
（`contracts/event.py` PILOT、`plugins/transport/webserver/`）未碰、
`gate_chain_strategy.py` 未碰、memory/tools-Assistant 未碰、typed ports 未碰。
iter-tests 的 worktree `~/.lca-worktrees/iter-tests-20261013-2243` 全程未碰。

## Explore

1. **Hot spots (`git log --oneline -40`)**: the newest landings are
   iter-tests-20261013-1843 (`run facade session-interface pin`, console
   `record_runtime` fallback pin), iter-quality-20261013-1831 (skills
   `_resolve_package` dedup → `lca/infrastructure/tools/skills/_package_lookup.py`),
   iter-tests-20261013-1443 (render-contract wire-key allowlist + JWT env scrub),
   and PR #43 (`agent-run-binding` / `lca-ops runs answer` CLI). RA-123/124/125
   (00:45 round) are the immediate predecessors.
2. **CONTEXT.md**: read (profile-launch-product / programmatic profile input /
   StopPolicy vocabulary). No new domain term needed by this round's stories.
3. **runtime-findings-2026-10-07.md**: read first (prompt requirement). Its P0
   (non-converging run raising `LoopObligationExceededError` out of `Agent.run()`)
   is marked fixed by RA-023 — re-verified this round (see Runtime verification).

## Friction walk (3 areas, READ end-to-end, 5 questions each)

### Area A — run execution facade chain (friction-walk subagent + coordinator spot-reads)

Files read: `lca/contracts/runtime/facade.py` (116 lines), `lca/application/runtime/
default_facade.py` (308 lines, head 80 + invariants), `lca/plugins/session/runtime/
bus/facade.py` (165 lines, head 60), `tests/scenario/run_1/
test_run_execution_facade.py` (90 lines, full), `lca/application/runtime/`
directory listing.

Call path: L0 adapters (CLI/HTTP/test) → `RuntimeFacade` contract (ADR-0199 L1
Port, §2.2.3) → `default_facade.py::dispatch_run` (RunIntent → SessionActivation →
RunDispatcher; invariants I-HPC-1/2/3, C8/C9) → `RunLifecycleCoordinator`
(不复制 loop, delegated) → session runtime; the legacy path pins
`lca.plugins.transport.webserver.carrier.runs.execute::execute_run/resume_run`.

**Verdict: no story.** Two independent reasons, both load-bearing:
- `lca/contracts/runtime/` + `lca/application/runtime/` are the **active
  ADR-0199 migration** (P1-01…P1-10 parallel PRs still landing; `RunHandle` is a
  NewType placeholder awaiting P1-04). Deepening mid-migration = fighting the
  migration's own churn.
- The pin test pins `plugins/transport/webserver/carrier/runs/execute.py` — the
  **lca-1000 webserver territory** (禁区), owned by iter-tests this cycle.
- `SessionBusFacade` itself is an honest adapter: the two shapes (runtime
  `Session` public face vs EnvelopeBus `append/observe` contract) are real, the
  docstring documents the contract precisely (category → event_type mapping,
  in-flight payload sharing by session identity, observer containment), and
  `as_bus_facade` is idempotent. Deletion test: deleting it moves the
  shape-translation into every bus publisher/consumer. Earns existence.
Q1–Q5 answers for this area: no shallow sprawl / no leaky seam / no testability
gap found — the friction here is organizational (migration in flight), not
architectural. (Documented per quota rule.)

### Area B — skills tool lifecycle + package-resolution seam (friction-walk subagent)

Files read: `lca/infrastructure/tools/skills/_package_lookup.py` (28),
`activate/tool.py` (301), `deactivate/tool.py` (100), `retire/tool.py` (130),
`lca/infrastructure/skills/activation/bridge.py` (164), `activation/scope.py`
(134), `exec/tool.py` (180), plus `search/tool.py` and the three commits'
diffs (991ff7ba3, a03f36935).

**Findings that became stories:**

- **F1 (→ RA-126):** `SkillActivationReducerBridge.current_state()`
  (bridge.py:116-129) is an orphaned seam. RA-124 deleted its only two callers
  (scope.py's ContextVar-loss fallback, now `find_activated`); `rg current_state
  lca/ tests/` hits only the definition — zero callers, zero tests. The
  docstring still claims it serves `resolve_skill_for_exec`, which is now false.
  Deletion test: concentrates to zero — pure deletion. Q2 shallow+dead.
- **F2 (→ RA-127):** `_package_lookup.py`'s dedup is real (three consumers), but
  each tool kept a private one-line `_resolve_package` method adapter
  (activate/tool.py:300-301, deactivate/tool.py:99-100 — the latter without a
  return annotation) and retire/tool.py uses a third style (import alias,
  :20-22/:49). Each adapter has exactly one call site, zero behavioral delta —
  hypothetical seams. Worse, two tests poke the adapter instead of the seam
  (`tests/infrastructure/test_skill_store_resolver.py:119`,
  `tests/scenario/operational/test_operational_skills.py:465` call
  `tool._resolve_package(...)` while the shared `resolve_package(store, raw)` has
  **no direct unit test** — "interface is the test surface" violated.
- `_package_lookup` itself (28 lines, one function) is shallow but earns
  existence: three consumers = real seam (deleting it moves the ritual back into
  three tools). Read but no story — documented.
- `bridge.find_activated` (RA-124) verified clean: no third hand-rolled
  `reversed(...activated)` scan anywhere; strip normalization inside the seam;
  6 direct bridge-level unit tests (textbook seam testing). No story.

### Area C — resource-key dimension of the runtime probe (coordinator, full-map grep)

Per the RA-123 lesson （收敛按资源键全图 grep), mapped `getattr(runtime, "<key>"`
across `lca/nodes/`: `state` ×13 (12 hand-rolled + the seam itself), `brain` ×10,
`reducer` ×2, `memory` ×2, `agent_state` ×2, others ×1.

- **`state` key:** 3 sites already delegate to `resolve_runtime_state`
  (persist.py, invoke.py, execute.py ×2); 9 sites still hand-roll the raw
  fail-soft probe `state = getattr(runtime, "state", None)` —
  think/gate.py:67, think/route/route.py:65, think/route/shortcut.py:65,
  think/context/budgeting.py:88, think/reason/plan.py:65,
  think/reason/render.py:191, think/budget/threshold_gate.py:145+169,
  perceive/fold/fold.py:76. One exact shape, one existing seam with
  `required=False` fail-soft semantics — **→ RA-128**.
- **`brain` key:** 10 sites hand-roll the single-shape
  `brain = getattr(runtime, "brain", None)` — reflect/score/score.py:133,
  think/gate.py:68, think/route/route.py:66, think/route/shortcut.py:66,
  think/reason/plan.py:66, think/reason/render.py:153+160+192,
  concept/decision_enforce/chain_run.py:94,
  concept/decision_shortcut_try/try_shortcut.py:74. No seam exists; adding one
  with the proven two-shape ritual (attribute first, then mapping `.get` —
  NodeContext declares `runtime: Mapping`, RA-119 实证) plus `required=False`
  converges all ten — **→ RA-129**.
- **port-then-runtime shape:** 3 concept/ sites hand-roll
  `state = input.port_values.get(PortName("state")) or getattr(runtime, "state",
  None)` — concept/memory_write/dispatch.py:72,
  concept/decision_shortcut_try/try_shortcut.py:70,
  concept/reflection_critique/critique_run.py:64. `resolve_typed_port_or_runtime`
  exists but is fail-loud only (3 existing callers: parse.py ×2, assemble.py
  ×2-state+writer); adding `required: bool = True` (default preserves them)
  converges the 3 fail-soft sites with `required=False` — the RA-119
  "required 旗语要一次给全" lesson — **→ RA-130**.

Q1 sprawl: understanding "how does a node read runtime resources" bounces across
~15 modules, but the bounce terminates at one seam file (`_resolve.py`) — the
sprawl is the tail of RA-118/119/123, not new chaos. Q3: no pure-function
extraction here — the probes are inline, which is exactly why they drift.
Q4: no leaky seam in this dimension (both shapes respect the carrier).
Q5: `resolve_runtime_state`'s both-required-branches are pinned by seam tests
(RA-119); the 9 raw sites carry no probe-level tests of their own.

## Runtime verification (mandatory, clean worktree)

Environment: worktree `/home/lichao/.lca-worktrees/raphy-20261013-2255`
(branch `raphy/arch-20261013-2255`, HEAD = main tip `6dcc21a62`),
`LLM_API_KEY=dummy`, `timeout 120`, script fed via stdin. Find-only, no code
changes.

| # | Flow | Result |
|---|------|--------|
| 1 | Basic run (MockLLMAdapter) → COMPLETED | ✅ PASS — `status=completed`, `Result` |
| 2 | Run with a tool call (NoopTool, mock returns one tool call then converges) | ✅ PASS — tool dispatch chain works |
| 3 | Two sequential runs on one agent | ✅ PASS — no session/state leakage |
| 4 | Non-converging run (InfiniteMock, `max_steps=5`) — RA-023 regression check | ✅ PASS — **no exception**, returns `Result` with `status=failed` |

**No P0 candidates.** RA-023's fix is real: the 2026-10-07 P0
(`LoopObligationExceededError` escaping `Agent.run()`) no longer reproduces;
non-converging runs return a failed `Result`. (Side note: anomaly_detector
cycle/stalled warnings still appear in logs — P2, out of scope.)

## Duplication scan (secondary)

No mechanical duplication clusters beyond the probe ritual above and the
adapter residue in Area B (both covered by stories). Prior rounds already swept
the obvious clusters (RA-001/002/008, RA-056, RA-118/119/123/124/125); the
`_resolve_package` adapter pair is the only new one-line-wrapper cluster.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-126 | `lca/infrastructure/skills/activation/bridge.py` | `SkillActivationReducerBridge.current_state()` (116-129) is an orphaned public seam: RA-124 deleted its only two callers (now `find_activated`); `rg` finds zero callers/tests; its docstring falsely claims to serve `resolve_skill_for_exec`. A public, tested-by-nobody interface is bait for future misuse. | Delete the method. If its `AgentState` import becomes unused, drop it too (ruff F401). | Locality: the bridge's public surface = its live contract only. Leverage: removes a false-documented seam before anyone builds on it. Testability: "interface is the test surface" — the deleted interface had zero tests to lose. | Strong |
| RA-127 | `lca/infrastructure/tools/skills/activate/tool.py`, `deactivate/tool.py`, `retire/tool.py`, `lca/infrastructure/tools/skills/_package_lookup.py`, `tests/infrastructure/test_skill_store_resolver.py`, `tests/scenario/operational/test_operational_skills.py` | Three tools each keep a private one-line `_resolve_package` adapter over the shared `resolve_package(store, raw)` seam (activate:300-301, deactivate:99-100 without return annotation; retire uses an import-alias third style). Each adapter has one call site and zero behavioral delta — hypothetical seams. Two tests poke the private adapter instead of the seam, so the shared seam itself has no direct unit test. | Delete the two method adapters (inline to `resolve_package(self._store, raw)`); unify retire to a plain `from ..._package_lookup import resolve_package`; retarget the two tests to `resolve_package(tool._store, raw)`; add direct seam unit tests (exact-id hit, name fallback, miss → None). | Locality: user-reference→package resolution has one interface, one test surface. Leverage: the next skill tool gets the resolution free with the seam's tests pinning it. Testability: tests move from the adapter to the seam ("interface is the test surface"). | Strong |
| RA-128 | `lca/nodes/_resolve.py` (existing `resolve_runtime_state`), 9 node modules (think/gate.py, think/route/route.py, think/route/shortcut.py, think/context/budgeting.py, think/reason/plan.py, think/reason/render.py, think/budget/threshold_gate.py ×2, perceive/fold/fold.py) | 9 hand-rolled `getattr(runtime, "state", None)` fail-soft probes — the unfinished tail of RA-118/119/123. Same key, same shape, same missing semantics; each drifts independently (this is exactly the RA-123 lesson: 收敛按资源键全图 grep). | Replace each with `resolve_runtime_state(context=context, node="<node-id>", required=False)`; verify per site that `context` is available and fail-soft None semantics are preserved (mapping `.get` fallback = type-contract fulfillment per RA-119 实证, no behavior change on attribute carriers). | Locality: probe ritual + error convention fixed once, fixed everywhere; future state readers get the seam. Leverage: closes the `state` key dimension completely (with RA-119/123, zero raw probes remain). Testability: the seam's required/non-required branches are already pinned; add a test asserting each converged site goes through the seam? (at minimum, seam tests + per-site regression suite green). | Worth exploring |
| RA-129 | `lca/nodes/_resolve.py` (new `resolve_runtime_brain`), 10 node modules (reflect/score/score.py, think/gate.py, think/route/route.py, think/route/shortcut.py, think/reason/plan.py, think/reason/render.py ×3, concept/decision_enforce/chain_run.py, concept/decision_shortcut_try/try_shortcut.py) | 10 hand-rolled single-shape `getattr(runtime, "brain", None)` probes — no seam exists for the `brain` key. Single-shape is the same drift pattern RA-118/119/123 already closed for `writer`/`state`/`adapter`. | Add `resolve_runtime_brain(*, context, node, required=False)` two-shape seam (attribute first, then mapping `.get`; fail-soft default since all 10 sites treat None as absent) in the exact RA-118/119/123 shape; converge all 10 sites; add seam tests for both branches. | Locality: the fourth resource key gets the same one-ritual discipline. Leverage: future brain consumers call one function; the `required` flag is available if any caller ever needs fail-loud. Testability: the new seam is unit-testable through its interface like the other three. | Worth exploring |
| RA-130 | `lca/nodes/_resolve.py` (`resolve_typed_port_or_runtime`), concept/memory_write/dispatch.py:72, concept/decision_shortcut_try/try_shortcut.py:70, concept/reflection_critique/critique_run.py:64 | 3 fail-soft port-then-runtime probes `input.port_values.get(PortName("state")) or getattr(runtime, "state", None)` — the same ritual `resolve_typed_port_or_runtime` performs, but that seam is fail-loud only, so these 3 sites hand-roll the soft variant. | Add `required: bool = True` to `resolve_typed_port_or_runtime` (default keeps the 3 existing fail-loud callers byte-identical); converge the 3 fail-soft sites with `required=False`. The RA-119 lesson "required 旗语要一次给全" — two semantics, one seam. | Locality: port-then-runtime probe exists in one place, with the missing-mode documented on the seam. Leverage: completes the `state`-key convergence story (RA-128 handles the runtime-only probes; this one the port+runtime probes). Testability: seam tests cover both required branches. | Worth exploring |

**Top recommendation**: RA-126 first — pure deletion, zero callers, zero tests,
five minutes of work and the codebase is permanently cleaner. RA-127 second —
same shape of honesty (delete the hypothetical, test the real interface). The
probe cluster (RA-128/129/130) is the mechanical tail: RA-128 and RA-130 are
converge-onto-existing-seam work (low risk), RA-129 adds a new seam in the
proven shape (slightly higher surface, still mechanical).

**Diversity quota**: satisfied — RA-126 (dead public seam) and RA-127
(hypothetical adapters + misplaced test surface) are friction-walk findings,
not duplication; RA-128/129/130 are the one duplication/pattern-class cluster
(the RA-123 lesson's prescribed follow-through).

## Self-grilling

### RA-126

- **Constraints**: nothing may change behaviorally — provably, since there are
  zero callers. `find_activated` (RA-124) is the live fallback seam and stays
  untouched. The bridge singleton lifecycle (`install`/`dispose`) unchanged.
- **Dependencies**: none. `rg "current_state" lca/ tests/` hits only the
  definition (verified this round).
- **Shape of the deepened module**: deletion — remove the method
  (bridge.py:116-129). Check whether `AgentState`'s import is still needed;
  drop it if orphaned (`ruff check` F401 will catch).
- **Test survival**: no test references it (rg-proven). The
  `test_resolve_skill_fallback.py` suite must pass unchanged (it pins the
  `find_activated` behavior, not this method).
- **Deletion test verdict**: concentrates to zero — the method moves nowhere
  and breaks nothing. The purest deletion of the round.

### RA-127

- **Constraints**: zero behavior change — the adapters add no logic (pure
  delegation), so inlining is behavior-identical. `resolve_package`'s contract
  (`SkillPackage | None`, exact-id first, case-insensitive name fallback)
  unchanged.
- **Dependencies**: 3 production call sites (activate/tool.py:170,
  deactivate/tool.py:62, retire/tool.py:49); 2 test call sites
  (`tool._resolve_package(...)`).
- **Shape of the deepened module**: the shared seam gains nothing; the tools
  lose their private adapters; retire's import alias normalizes to a plain
  import. The seam gets direct unit tests (exact hit / name fallback / miss).
- **Test survival**: the two retargeted tests must pass with identical
  assertions (only the call path changes: `tool._resolve_package(x)` →
  `resolve_package(tool._store, x)`); the new seam tests pin the interface.
  Full skills test dirs must stay green.
- **Deletion test verdict**: the adapters delete to zero (hypothetical seams —
  one caller each, zero delta). The seam itself concentrates and stays.

### RA-128

- **Constraints**: fail-soft `None` semantics preserved at every site
  (`required=False`); no wording changes (no raise path taken); mapping `.get`
  fallback is type-contract fulfillment, not a behavior change on attribute
  carriers.
- **Dependencies**: 9 node modules; the callee is `context.runtime` carrier.
  Each site must have `context` in scope — verify per site before editing.
- **Shape of the deepened module**: no new seam; `resolve_runtime_state`
  gains 9 delegates with node ids matching each site's node naming convention
  (check the existing ids, e.g. `llm.invoke`, `effect.execute`).
- **Test survival**: seam branch tests (RA-119) already pin both required
  modes; run each affected node's test file + the nodes regression dir.
- **Deletion test verdict**: concentrates — deleting the seam would scatter 12
  probe sites back into hand-rolled ritual (9 new + 3 existing delegates).

### RA-129

- **Constraints**: all 10 sites treat `None` as absent (fail-soft) — the seam
  defaults `required=False`; per-site `None`-handling must be re-verified
  before editing (no site may dereference unconditionally).
- **Dependencies**: 10 node modules; carrier shapes (attribute + mapping) as
  with the other seams.
- **Shape of the deepened module**: `resolve_runtime_brain(*, context:
  NodeContext, node: str, required: bool = False)` in `lca/nodes/_resolve.py`,
  next to the three proven siblings, in their exact docstring/signature shape;
  10 call sites delegate.
- **Test survival**: new seam tests for both `required` branches (fail-loud
  raises naming the node; fail-soft returns None on empty carrier); affected
  node tests green.
- **Deletion test verdict**: concentrates — without it, the 11th brain
  consumer re-invents the single-shape probe (and the 12th, and so on).

### RA-130

- **Constraints**: the 3 sites keep fail-soft `None` (they currently return
  None on empty port+runtime); the 3 existing fail-loud callers (parse.py ×2,
  assemble.py ×2) must stay byte-identical — `required: bool = True` default.
- **Dependencies**: callers of the seam are parse/assemble (fail-loud, keep
  default); the 3 concept/ sites gain `required=False`.
- **Shape of the deepened module**: one parameter added to
  `resolve_typed_port_or_runtime`; 3 sites delegate with
  `node=` naming per their module ids.
- **Test survival**: parse/assemble behavior pinned by existing tests (default
  branch unchanged); seam tests for the new `required=False` branch; concept
  node tests green.
- **Deletion test verdict**: concentrates the two missing-semantics into one
  seam — the RA-119 lesson's exact prescription.

## Considered and declined

- Area A run-execution facade chain: declined — active ADR-0199 migration
  (P1-01…P1-10 in flight) + lca-1000 webserver territory (禁区). Files read
  and reasons documented above.
- `resolve_package` name-fallback silently takes the first match on collision
  (Area B F3): real, but the fix is a domain decision (raise on ambiguity vs
  rank vs return-all) — speculative without a settled policy; not filed.
- `run_skill_script`'s silent tail fallback when `skill_id` is omitted (Area B
  F4): real, but a one-line tool-`description` fix is not architectural
  deepening; not filed.
- "Single truth in reducer state" aspiration vs the ContextVar fast path
  (Area B F5): eliminating the fast path is a semantic change to a proven
  fallback chain; aspirational; not filed.
- `OSError` from `list_installed`/`get` passing through `resolve_package`
  (Area B F6): leak depends on the outer tool framework's containment, which
  this area did not verify — speculative; not filed.
- Store capability discovery via two `getattr` mechanisms in activate/tool.py
  (Area B F7): speculative; not filed.
- strip-normalization ownership drift risk between `find_activated` (inside)
  and `resolve_package` (caller-side) (Area B F8): no evidence of drift;
  speculative; not filed.
- `agent_state` vs `state` carrier-key naming divergence (from 0045 round):
  still no failure evidence; still declined.

## Assessment complete: 5 stories written, top is RA-126.
