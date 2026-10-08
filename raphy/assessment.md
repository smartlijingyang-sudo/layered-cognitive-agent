# Raphy Assessment — Round 11 (2026-10-08 15:05, branch raphy/arch-20261008-1505)

Fresh session. Scope via YAGNI: last ~40 commits' hot spots are
**sandbox path mapping** (b6608bb58, 8094cc234, 78034deea, f03b2359a —
the user's own in-flight fixes, marked 禁区 this round), **carrier runs**
(01f205289, 66fafdcf0, 8c662a387), and the **act/effect envelope path**
(RA-031..041 just landed). Read: runtime-findings-20261007.md (outranks
static findings), CONTEXT.md, raphy/progress.txt `## Codebase Patterns`.

## Friction walk (3 areas, read end-to-end)

### Area A — carrier/runs (lifecycle.py, runnable_assembly.py, execution_environment.py)

1. *Bouncing between modules for one concept?* YES — resolving an
   assistant's Home spec for a run touches `runnable_assembly.assemble`
   → `_assistant_spec_for_run` → `_role_profile_for_assistant` →
   `tools_from_scope` → `execution_environment.prepare` (which imports
   the PRIVATE `_assistant_spec_for_run` cross-module). → RA-045.
2. *Shallow modules?* `RunLifecycleCoordinator` is honest (delegates to
   seams); the private `_profile_backfill_for_run` wrappers in
   runnable_assembly.py AND plugin.py are two identical fail-soft
   rituals — noted, not storied (weak duplication class, 2 sites).
3. *Pure functions hiding call-site bugs?* No.
4. *Leaky seams?* YES — lifecycle.py execute()/resume() both inline
   `from lca.plugins.events._session_observe import set_session` and
   `from lca.plugins.events.publishers._session_publish import ...`
   (private modules) plus a duplicated bind/reset ritual. → RA-044.
   Also `RegistryEffectDispatcher.execute` computes `active_decision`
   then ignores it. → RA-043.
5. *Untested / untestable through the interface?* The dispatcher
   precedence comment claims behavior the code doesn't implement —
   testable, just untested. → RA-043.

### Area B — act/effect dispatch (envelope.py, execute.py, dispatch.py, handlers_provider.py)

Read end-to-end following the RA-033 diff. Found a LIVE P0:
`effect.execute`'s `state` typed port has NO graph producer (nothing
writes a `state` port anywhere; decision arrives, state arrives None).
RA-033 deleted the metadata smuggle (`context.runtime.get("state")`)
that used to supply it, so `BodyActEffectHandler` now PG-003s on every
tool call. Bisect d5eed82c5(good)..b6608bb58(bad) → first bad is RA-033
7b38118ad. The established `lca/nodes/_resolve.py::
resolve_typed_port_or_runtime` seam (think/decision/parse,
think/history/assemble) is the fix. → RA-042 (P0).

### Area C — observability/spine anomaly (spine_anomaly.py vs derivers/anomaly.py)

Two modules, different roles: A is the Session-observer adapter
(wiring), B is the deriver (8 detectors). Not duplication — a seam +
module split. 2026-10-07 P2-3 (false-positive cycle/stalled warnings on
healthy runs) is real but threshold-tuning, not a seam shape problem;
left for a future round with detector-owner context. No story.

Sandbox/guest-preamble (`_DISPLAY_PATH_KEYS` allowlist) deliberately
untouched: the user is actively iterating there this hour (4 commits
14:57–15:04); recorded as round-11 禁区.

## Runtime verification (mandatory, actually run — worktree @ b6608bb58, LLM_API_KEY=dummy)

- (a) basic run → completed ✅
- (b) run with tool_call → **FAILED** ❌ "Agent 运行结束但未产生任何输出",
  tool executed 0 times (marker-file probe) → the RA-033 P0 above
- (c) two sequential runs → completed, completed ✅
- (d) RA-023 regression (non-converging) → status=failed, no exception leak ✅
- 2026-10-07 P0 (LoopObligationExceededError escape) stays fixed.
- Open runtime P2s carried as stories: run(None) → RA-046,
  NativeToolCall str arguments → RA-047.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality+leverage) | Strength |
|----|-------|---------|----------|------------------------------|----------|
| RA-042 | lca/nodes/concept/effect/execute.py | RA-033 removed the state/metadata smuggle; the `state` typed port has no producer, so every tool call PG-003s and no tool ever executes (P0, runtime-verified, bisected to 7b38118ad) | Resolve `state`/`decision` via the shared `resolve_typed_port_or_runtime` seam (typed port first, kernel runtime carrier fallback) | locality: one resolve rule for all nodes; leverage: every future port-migration gets the fallback for free; the handler's fail-loud stays | Strong |
| RA-043 | lca/harness/declarative/execute/dispatch.py | `active_decision` computed but never passed to `handler.handle`; no `active_state` — the documented precedence is dead code | Pass the precedence-resolved values to the handler | locality: comment and code agree; leverage: constructor-injected dispatchers become usable | Worth exploring |
| RA-044 | lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py | execute()/resume() duplicate the publish-session ContextVar bind/reset ritual and both import private `lca.plugins.events._session_observe` / `_session_publish` | One public context-manager seam in lca/plugins/events/ | locality: bind/reset can't unpair; leverage: the private modules gain a public face | Worth exploring |
| RA-045 | runnable_assembly.py, execution_environment.py | Assistant Home spec resolution is a private fn imported cross-module; the fail-loud policy is restated 3× with different messages | Public `require_assistant_spec` seam | locality: policy stated once; leverage: assistant-binding changes touch one seam | Worth exploring |
| RA-046 | lca/application/api/api.py (+ team/profile.py) | `agent.run(None)` → deep TypeError in objective_preview | Entry validation: str \| AgentMessage or clear TypeError | locality: every run crosses one entry seam | Worth exploring |
| RA-047 | lca/contracts/models/core/conversation/llm.py | `NativeToolCall(arguments='<json str>')` → obscure ValueError in decision.parse | Coerce via json.loads or clear construction-time error | locality: construction is the one crossing point | Worth exploring |

Top recommendation: **RA-042 first, immediately** — it is a P0 regression on
the core agent loop (no tool call executes), introduced by the previous
raphy round's own story. Everything else is Worth-exploring hygiene.

## Self-grilling

### RA-042
- **Constraints**: no live objects back into envelope.metadata (RA-033's
  core win); handler's PG-003 fail-loud stays; `decision` port behavior
  unchanged.
- **Dependencies**: `lca/nodes/_resolve.py` (stable, converged seam);
  `NodeRuntimeView.state` (host_wiring, verified). Callers of
  `gateway.execute`: only effect.execute and remember/write (the latter
  already passes kwargs explicitly).
- **Shape**: two-line change in `node_execute`; the seam owns the
  port-vs-runtime lookup order.
- **Test survival**: `test_effect_execute_tool_result_surface.py` (RA-033
  rewrote it to use the real minter — it pins attribution, not the
  state source); the E2E marker-file repro is the new pin.
- **Deletion test**: concentrates — deleting the fallback re-breaks every
  tool call; the seam already exists.

### RA-043
- **Constraints**: `EffectHandler.handle` signature unchanged; per-call
  kwargs still win over constructor values.
- **Dependencies**: `RegistryEffectDispatcher` only impl; factory
  `create()` already accepts state/decision.
- **Shape**: compute `active_state`, pass both resolved values.
- **Test survival**: existing dispatcher tests (test_registry_dispatch.py
  touched by RA-033) pin execute; add a precedence unit test.
- **Deletion test**: concentrates — removes a comment/code lie.

### RA-044
- **Constraints**: resume()'s spine-hook ritual is separate; keep.
  Private modules stay private; new seam is their public face.
- **Dependencies**: `lca.plugins.events._session_observe`,
  `publishers._session_publish` (both private, stable).
- **Shape**: `publish_session_scope(bound_bridge)` context manager;
  both methods use it.
- **Test survival**: carrier lifecycle tests; the ritual is
  behavior-preserving.
- **Deletion test**: concentrates — bind/reset pairing currently
  duplicated and easy to unpair.

### RA-045
- **Constraints**: ADR-0242 D3/D4/D9 semantics unchanged; empty
  assistant_id → None path stays.
- **Dependencies**: assistant catalog capability; three current call sites
  + execution_environment.
- **Shape**: `require_assistant_spec(scope, assistant_id)` public;
  delete the private cross-module import.
- **Test survival**: assistant/carrier tests pin the fail-loud paths.
- **Deletion test**: concentrates — four policy copies become one.

### RA-046 / RA-047
- Standard entry/construction validation; constraints noted in table.
- Deletion test: concentrates (single crossing point each).

## Diversity quota

Satisfied: RA-042/043/044/045 come from the friction walk (leaky seams,
dead code, policy sprawl) — not duplication. RA-046/047 come from
runtime verification. No story is pure mechanical duplication.

---
Assessment complete: 6 stories written, top is RA-042.

---

# Raphy Assessment — Round 12 (2026-10-08 22:05 CST, branch raphy/arch-20261008-2205)

Fresh session. Scope via YAGNI: last ~45 commits' hot spots are
**sandbox** (SandboxPaths single-seam todo-81, per-exec mount namespaces,
session-root staging, RA-037/040), **effect dispatch**
(RA-033/042/043 typed-kwarg discipline), and **carrier run lifecycle**
(lifecycle.py / execution_environment.py). Skipped: assistant skill
overlay (agy has uncommitted work there — read-only), raphy/ralph Round 2
areas, `lca/cognition/memory/`, `gate_chain_strategy.py`. Read:
runtime-findings-20261007.md (outranks static findings),
hidden_files/runtime baseline 2026-10-08, CONTEXT.md,
raphy/progress.txt `## Codebase Patterns` (禁区 list).

## Friction walk (3 areas, read end-to-end)

### Area A — sandbox (paths/sandbox_paths.py, paths/mount_namespace.py, local/adapter.py, runtime/mount.py)

1. *Bouncing between many small modules for one concept?* Mild — the exec
   path crosses `adapter._exec_shell` → `SandboxPaths` → `mount_namespace`,
   but every crossing is at the documented seam; the bounce IS the design.
2. *Shallow modules?* YES — `LocalSandboxAdapter._rewrite_command` /
   `_project_host_to_guest` are one-line delegates whose interface is as
   complex as their implementation. Worse: production-dead (repo-wide grep:
   only `test_adapter_host_path_projection.py` calls them; `_exec_shell`
   builds `SandboxPaths` inline). Deletion test: deleting concentrates
   nothing but removes a false second seam — and the wrappers construct
   `SandboxPaths.for_local(root)` WITHOUT the `mounted` flag, so in
   per-exec mount-namespace mode they would string-rewrite a command the
   kernel already translates. → RA-050.
3. *Pure functions extracted just for testability?* `wrap_in_mount_namespace`
   is pure string construction — honest; the real bug class here would be
   bind/reset pairing, which doesn't exist (per-exec, no holder).
4. *Leaky seams?* `_is_identity()` vs `mounted` are two documented identity
   conditions; `mount_namespace_enabled()` env+probe is clean. No new leak.
5. *Untested / untestable-through-interface?* `SandboxPaths` is pinned by
   `test_sandbox_paths.py` (round-trip / containment / totality) — the
   interface IS the test surface. The dead wrappers are tested directly —
   tests pin the wrong seam. → RA-050.

### Area B — effect dispatch (harness/declarative/execute/dispatch.py, nodes/_resolve.py)

Recently deepened by RA-033/042/043: the dispatcher is now the single typed
contract for the effect gateway, `lca/nodes/_resolve.py` is one module with
one interface for port resolution. Read end-to-end; no new friction found.
Recorded so the next round doesn't re-walk it.

### Area C — carrier run lifecycle (carrier/runs/lifecycle/lifecycle.py, carrier/runs/execute/execution_environment.py)

1. *Bouncing for one concept?* YES — "what happens when a run fails"
   requires diffing THREE except blocks in ONE class: `execute()` × 2
   (`(PlaneBindingError, _UnknownExecutionTargetError)` and `Exception`)
   plus `resume()`'s `except Exception`.
2. *Shallow modules?* YES — the three blocks are near-identical four-step
   rituals (`_record_failure` → `exc_to_record`/`emit_exception_caught` →
   `emit_carrier_run_failed` → [`emit_carrier_exception_finally`]); none
   earns separate existence. → RA-048.
3. *Leaky seams?* YES, twice: (a) failure semantics leak across the rituals —
   `resume()` already omits `emit_carrier_exception_finally`, so the
   divergence has started; the next observability change to one block will
   silently diverge the others. (b) `resume()` hand-pairs three ContextVar
   set/reset (capability_bindings / tools_service / defer_session) in
   try/finally while create-run binds the same trio inside `prepare()` —
   the pairing can split, and `resume()`'s own comment documents this
   failure class (spine hook lost on resume). → RA-049.
4. *Untestable through the interface?* The rituals are only exercised via
   full lifecycle runs; a converged `_observe_failure` seam would be
   directly unit-testable with a fake session. → RA-048.
5. *Deletion test?* A converged failure-observation helper concentrates
   (deleting it re-scatters the ritual); a resume-capability CM concentrates
   the bind/reset pairing. Both pass. → RA-048 / RA-049.

Cross-module private import noted: `_UnknownExecutionTargetError` is caught
as a private name in three modules (lifecycle.py, loop_drivers.py,
intent.py); the defining module is `lca/plugins/loop/driver/plugin.py`.
Folded into RA-048 as a public-alias criterion (RA-044's pattern).

## Runtime verification (mandatory; worktree @0ab9d67cd, MockLLMAdapter, LLM_API_KEY=dummy)

- (a) basic run: `completed`
- (b) one-shot tool call (marker file): `completed`, marker written — RA-042 regression stays fixed
- (c) two sequential runs on one agent: `completed completed`
- infinite tool-loop mock, `max_steps=3`: returns `Result(status=failed)`, NO exception escapes — RA-023 fix holds
- No new P0/P1. (10-07's P2s are RA-046/047, landed.)

## Duplication scan (secondary)

- `runtime/mount.py`: `load_mount_files` + `build_mount_manifest` repeat the
  identical lazy `from ...attachment_scope import merge_attachment_ids`
  (cycle-avoidance comment in two places). Weak duplication class — not
  opened as a story.

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-048 | carrier/runs/lifecycle/lifecycle.py; plugins/loop/driver/plugin.py | Three near-identical run-failure observation rituals in one class; resume's already diverges (omits finally-emit); failure semantics leak across the copies | One `_observe_failure(session, exc, *, boundary, hub, user_message, emit_finally)` seam; public alias for `_UnknownExecutionTargetError` | locality: one ritual, emit set identical per path by construction; leverage: the next observability step is added once; the helper is directly unit-testable | Strong |
| RA-049 | carrier/runs/lifecycle/lifecycle.py | resume() hand-pairs 3 ContextVar set/reset; create-run binds the same trio elsewhere; a future capability can be forgotten on resume (the documented spine-hook failure class) | `bind_resume_capabilities` contextmanager owning set/reset + ADR-0248 defer policy | locality: pairing can't split; leverage: new binds land in both paths at once | Worth exploring |
| RA-050 | infrastructure/sandbox/local/adapter.py; tests/.../test_adapter_host_path_projection.py | `_rewrite_command`/`_project_host_to_guest` are production-dead one-line wrappers that also drop the `mounted` flag — a second "single seam" disagreeing with the first | Delete both; migrate their tests 1:1 onto `SandboxPaths.rewrite_command`/`present_text` | locality: one seam, one claim; leverage: mounted-mode drift impossible | Worth exploring |

Top recommendation: **RA-048 first** — failure observability is the highest-leverage seam in the carrier: every run failure crosses it, and the triple-copy is where the next observability change will silently diverge.

## Self-grilling

### RA-048
- Constraints: emit sets per path must stay bit-identical — parameterize (`emit_finally`), don't normalize; boundary labels stay distinct; the helper is sync (all four emits are sync calls at current call sites — verify); `_log.exception` lines stay at call sites.
- Dependencies: `RunLifecycleCoordinator` only; the emit functions stay where they are; `loop_drivers.py`/`intent.py` keep working via the alias.
- Shape: private method `_observe_failure(session, exc, *, boundary: str, hub, user_message: str, emit_finally: bool)`.
- Test survival: run-lifecycle failure-path tests under `tests/plugins/transport/webserver/`; new unit test drives the seam directly (fake session + exc, assert emit set for True/False).
- Deletion test verdict: concentrates.

### RA-049
- Constraints: resume's None-guards (`bindings is None` → skip capability/tools; `tools_service is None` → skip) and the ADR-0248 gated-vocal-mode defer mirror are load-bearing — move them inside the CM, don't simplify.
- Dependencies: `capability_bindings` / `tool_defer` session modules unchanged; `resume()` callers unchanged.
- Shape: `@contextlib.contextmanager def bind_resume_capabilities(session, bindings)` in lifecycle.py (or a small module next to capability_bindings if the implementer prefers).
- Test survival: HIL resume tests.
- Deletion test verdict: concentrates the pairing.

### RA-050
- Constraints: boundary-aware rewrite coverage must not drop — migrate cases 1:1.
- Dependencies: only `test_adapter_host_path_projection.py` references the wrappers (verified by grep).
- Shape: pure deletion; `_guest_to_host` / `_paths_for` stay.
- Test survival: `test_sandbox_paths.py` keeps pinning the seam; migrated tests assert identical expectations.
- Deletion test verdict: deletes cleanly — the wrappers fail it (they move no complexity).

## Diversity quota

Satisfied: RA-048/049 are leaky-seam findings from the friction walk; RA-050 is a deletion-test finding. No story is pure mechanical duplication.

---
Assessment complete: 3 stories written, top is RA-048.
