# Raphy Assess — 2026-10-13 00:45 round

Branch: `raphy/arch-20261013-0045` (worktree `/home/lichao/.lca-worktrees/raphy-20261013-0045`)
Mode: ASSESS ONLY (no code changes outside `raphy/`). No `<promise>COMPLETE</promise>`.

## Scope

Hot spots from `git log --oneline` (~40 commits back from `40717b8f4`):

1. **memory-extract response-code guard** (`19ee778ec`, 10-12) —
   `lca/nodes/reflect/memory_extract/memory_extract.py`: prompt rule +
   deterministic post-parse filter dropping `preference:response_code` candidates.
2. **session observer mount idempotence + activated_skills re-wiring**
   (`c5696c81e`, 10-12) — `lca/plugins/events/_session_observe.py`,
   `lca/infrastructure/skills/activation/bridge.py` / `scope.py`,
   `lca/nodes/concept/context_compose/skills.py`.
3. **manifest/ package split follow-ups** (`4a6b5e04a`, `b71a73f2d`) —
   `lca/infrastructure/observability/spine/manifest/`.

Read: `CONTEXT.md` (domain vocabulary), `raphy/progress.txt` top
`## Codebase Patterns` (禁区 + prior learnings),
`~/workspace/goals/layered-cognitive-agent-agent/hidden_files/runtime-findings-20261007.md`
(prior runtime baseline; still the newest file — nothing newer exists).

## 禁区 compliance

Respected: `lca/cognition/memory/` (frozen), ralph Round 2 areas,
`gate_chain_strategy.py` (hands-off), `lca/infrastructure/computer/guest/preamble.py`
(user iterating), `lca/plugins/transport/webserver/` retirement-stub work
(lca-1000 territory), main worktree (dirty: `docs/plans/task.md` —
not even read; everything executed inside the clean worktree).
Nothing written outside `raphy/`.

## Runtime verification (mandatory, executed)

Environment: clean worktree `/home/lichao/.lca-worktrees/raphy-20261013-0045`
at main tip `40717b8f4` (per progress.txt lesson — prompt's literal
`cd ~/layered-cognitive-agent` would have read the dirty main tree).
`LLM_API_KEY=<redacted>

| Scenario | Result |
|---|---|
| (a) basic run reaches COMPLETED (MockLLMAdapter) | **completed** |
| (b) run with a tool call (noop tool, 2-turn mock) | **completed** |
| (c) two sequential runs on one agent | **completed / completed** |
| (d) RA-023 regression: non-converging run (InfiniteMock, max_steps=5) | **no raise, status=failed** (framework log: `status=failed max_steps=5`) |

No crash, hang, or silent failure. RA-023's translation of
`LoopObligationExceededError` into a failed Result holds on the current
tip. No new P0/P1. Prior P2s (`run(None)` TypeError,
`NativeToolCall.arguments` str error) remain deferred to iter-quality —
not re-litigated.

## Friction walk (5 questions per area)

### Area A — reflect memory_extract (`lca/nodes/reflect/memory_extract/memory_extract.py`)

Read end-to-end: full file (387 lines). Tests:
`tests/reflect/test_memory_extract_distills_identity.py` (checked existence).

1. **Bouncing between modules to understand one concept?** No real sprawl —
   one 387-line module carries the whole extraction concept (prompt template,
   JSON parse, candidate filter, node executor, plugin setup). Imports are
   declare-and-use, not concept-splitting. Does not apply; the module is
   deep enough on its own.
2. **Shallow modules?** The two policy layers — prompt-steering text
   (`_EXTRACT_PROMPT`, "preference:response_code 不是合法维度") and the
   deterministic enforcement (`_is_response_code_preference` +
   `_RESPONSE_CODE_PREFERENCE_RE`) — form a *policy pair*, not a shallow
   module. But the shared **identity literal** `preference:response_code`
   appears in both the prompt text (line 78) and the filter (line 108): a
   RA-120-class literal drift. → RA-125.
3. **Pure functions extracted for testability hiding call-site bugs?** No.
   `_parse_candidates` failure mode (fail-soft empty list) is exercised at
   its call site in `node_execute`, and `_is_response_code_preference` is
   only called inside `_parse_candidates` — call context is honest.
4. **Leaky seams?** The three two-shape runtime probes (`agent_state`,
   `memory`, `adapter`) each hand-roll the attribute-then-`.get` ritual.
   `adapter` is the leftover half of RA-118/119: same ritual, two call
   sites, divergent missing semantics (fail-loud in
   `lca/nodes/think/llm/invoke.py::_resolve_adapter`, fail-soft passthrough
   here) — never converged onto `lca/nodes/_resolve.py`. → RA-123.
   (The `agent_state` vs `state` key naming divergence was noticed but is
   out of scope — no failure evidence, speculative.)
5. **Untestable through the interface?** No — the node is exercised via
   `node_execute` in the existing test file; the probes degrade to
   passthrough, which is the documented fail-soft contract (ADR-0246 §0.6).

### Area B — skill activation truth (`bridge.py`, `scope.py`, `context_compose/skills.py`, `_session_observe.py`)

Read end-to-end: `bridge.py` (159 lines), `scope.py` (170 lines),
`context_compose/skills.py` (first 120 lines + diff of c5696c81e),
`_session_observe.py` (155 lines). Tests:
`tests/infrastructure/skills/activation/test_resolve_skill_fallback.py`.

1. **Bouncing between modules?** Moderate: the "activated skills" concept
   is split across ContextVar (`scope.py`), reducer single-write
   (`bridge.py`), prompt assembly (`context_compose/skills.py`), and the
   exec-time resolver (`resolve_skill_for_exec`). Each owns a real concern,
   but the *fallback knowledge* (reducer state is the single truth) leaks
   back into `scope.py` twice.
2. **Shallow modules?** `resolve_skill_for_exec` hand-rolls the same
   "ContextVar miss → `bridge.current_state()` → scan
   `state.activated_skills`" ritual **twice** (by-id lookup and empty-tail
   lookup). The bridge already documents itself as the 真值 owner
   (`current_state` docstring: "激活状态单一真值在 reducer state"), yet
   the fallback ritual lives in the caller — the bridge is shallower than
   it should be. → RA-124.
3. **Pure functions hiding call-site bugs?** The `can_activate` idempotency
   check and `unregister_activated`'s False-on-miss are honest. The real
   recent bug (double observer mount from resume contexts) hid in *call
   timing across asyncio contexts*, not in a pure function — fixed by
   c5696c81e with the mount marker on the underlying Session. Not a story.
4. **Leaky seams?** `_session_observe.py::_underlying_session` probes
   attributes `("session", "inner")` then duck-checks `observe` — a
   two-shape unwrap. One occurrence only ("one adapter = hypothetical
   seam") → no story. `_session_observe.py`'s module-level
   `__getattr__` `_current_session` shim is deliberate compat; not friction.
5. **Untestable?** The fallback is pinned through the public interface by
   `test_resolve_skill_fallback.py` — good. A deepened bridge seam would be
   *more* testable (bridge-level unit test without the ContextVar), which
   is part of RA-124's upside.

### Area C — spine manifest/ package

Read end-to-end: `manifest.py` (67 lines) + `__init__.py`. One intentional
COMPAT re-export with `delete_when`/`forbidden_new_usage` annotations
(ADR-0195 O1). The module-level `__getattr__` lazy-load ritual earns its
existence: it breaks the
`event_record → manifest → payloads_spine → events.persistence → …`
import cycle, documented in the docstring. Deletion test: deleting it
re-introduces the cycle. No friction; no story. (Question 1–5: N/A — read
both files fully; the seam is documented and deliberate.)

## Candidate table

| ID | Files | Problem | Solution | Benefits (locality + leverage) | Strength |
|---|---|---|---|---|---|
| RA-123 | `lca/nodes/_resolve.py`, `lca/nodes/think/llm/invoke.py` (`_resolve_adapter`), `lca/nodes/reflect/memory_extract/memory_extract.py` | The `adapter` two-shape runtime probe is hand-rolled twice with divergent missing semantics — fail-loud `TypeError` (invoke.py) vs fail-soft `None` passthrough (memory_extract.py). RA-118/119 converged `writer` and `state` but left this half behind. | Add `resolve_runtime_adapter(*, context, node, required=True)` to `_resolve.py` in the exact RA-118/119 shape; invoke.py delegates with `required=True`, memory_extract with `required=False`. | Locality: lookup order + error wording fixed once, fixed everywhere. Leverage: the RA-119 "收完两种语义，别留半截" lesson finally closed; future resource probes have a third precedent. | Strong |
| RA-124 | `lca/infrastructure/skills/activation/bridge.py`, `scope.py` (`resolve_skill_for_exec`) | `resolve_skill_for_exec` hand-rolls the "ContextVar miss → bridge.current_state() → scan state.activated_skills" fallback ritual twice (by-id and tail). The bridge owns the 真值 contract but the ritual lives in the caller — a leaky seam. | Deepen the bridge with `find_activated(skill_id: str \| None) -> ActivatedSkill \| None` encapsulating the reducer-state read + reversed id/name scan + tail fallback; `resolve_skill_for_exec` keeps the ContextVar fast path and delegates the fallback. | Locality: the fallback ritual collapses from 2 call sites into the module that already owns the single-write path. Leverage: future ContextVar-loss callers get the fallback free instead of copying it. Testability: the seam is unit-testable at bridge level. | Worth exploring |
| RA-125 | `lca/nodes/reflect/memory_extract/memory_extract.py` | Same policy ("一次性回复格式要求不是偏好") stated twice in two languages: prompt-steering text and deterministic filter. The identity literal `preference:response_code` is hardcoded in both the prompt (line 78) and the filter (line 108) — RA-120-class drift. | Canonical `_RESPONSE_CODE_DEDUPE_KEY = "preference:response_code"` constant, used in the filter comparison and interpolated into the prompt build (the prompt already uses `{existing_memories}`/`{task}` replacement). | Locality: the key's identity exists once; renaming it no longer requires lockstep edits in prompt text and code. Leverage: RA-120 marker-class drift prevented at the policy's second enforcement point. | Worth exploring |

**Top recommendation**: RA-123 first — it is the unfinished tail of
RA-118/119 (the pattern, the `required` precedent, and the
`{node}: 'x' must be supplied via context.runtime` message convention are
all proven; risk is near zero). RA-124 is the deeper architectural move
(bridge earns the 真值 contract it already claims in prose). RA-125 is
small, honest literal convergence — the only duplication-class story.

**Diversity quota**: satisfied — RA-123 (shallow probe sprawl) and RA-124
(leaky fallback seam) are friction-walk findings; RA-125 is the one
duplication-class story.

## Self-grilling

### RA-123

- **Constraints**: behavior must not change. invoke.py path stays fail-loud
  (`TypeError` naming the node); memory_extract.py path stays fail-soft
  (returns `None` → existing passthrough branch). Error wording follows the
  proven convention `{node}: 'adapter' must be supplied via context.runtime`
  (the `'state'` variant is pinned by
  `tests/nodes/test_effect_execute_batch_attribution.py:200` — no wording
  drift allowed).
- **Dependencies**: callers are the think.llm.invoke plugin and the
  reflect memory_extract node; the callee is the `context.runtime` carrier
  (Mapping or attribute namespace — both shapes must keep working, incl.
  `runtime is None`).
- **Shape of the deepened module**: `resolve_runtime_adapter(*,
  context: NodeContext, node: str, required: bool = True) -> Any` in
  `lca/nodes/_resolve.py`, next to `resolve_writer`/`resolve_runtime_state`.
  invoke.py's private `_resolve_adapter` becomes a thin delegate
  (or call sites call the seam directly); memory_extract's probe block is
  replaced by `resolve_runtime_adapter(..., node="phase.reflect.memory.extract", required=False)`.
- **Test survival**: no existing test pins `_resolve_adapter`'s wording
  (grep found none) — wording is pinned only by convention. Add a seam test
  covering both `required` branches (fail-loud raises naming the node;
  fail-soft returns None on empty carrier).
- **Deletion test verdict**: concentrates — deleting it scatters the
  attribute-then-`.get` ritual back into two call sites, exactly the
  verdict that earned `resolve_writer`/`resolve_runtime_state` their
  existence.

### RA-124

- **Constraints**: behavior must not change. ContextVar has priority;
  reversed id/name scan order; tail semantics for `skill_id=None`;
  `SkillNotFoundError` messages stay byte-identical (pinned by
  `tests/infrastructure/skills/activation/test_resolve_skill_fallback.py`).
  Bridge singleton lifecycle (`install`/`dispose`) unchanged.
- **Dependencies**: `resolve_skill_for_exec` callers are the skill tool
  exec path (`skills/exec/tool.py` etc.); the bridge reads reducer state
  via the late-bound `state_getter`.
- **Shape of the deepened module**: `SkillActivationReducerBridge.
  find_activated(skill_id: str | None) -> ActivatedSkill | None` —
  returns `None` when the bridge is not installed, no state, or no match.
  `scope.py` keeps the ContextVar fast path; on miss/empty it delegates to
  the bridge seam and raises `SkillNotFoundError` iff the seam returns
  `None`.
- **Test survival**: `test_resolve_skill_fallback.py` must pass unchanged
  (behavior pinned through the public interface). Add a bridge-level test
  for the new seam (installed/uninstalled, by-id, by-name, tail).
- **Deletion test verdict**: concentrates — without it, every future
  ContextVar-loss caller re-invents the "read reducer state, scan in
  reverse" ritual; with it, the ritual lives next to the module that owns
  the single-write path. Earns existence.

### RA-125

- **Constraints**: prompt wording must stay functionally identical (LLM
  steering behavior); filter semantics unchanged (`_is_response_code_preference`
  keeps its fail-open regex; explicit `memory_add` unaffected).
- **Dependencies**: consumers are `_parse_candidates` and `node_execute`;
  the prompt is built by string `.replace` of `{existing_memories}`/`{task}`.
- **Shape of the deepened module**: module-level
  `_RESPONSE_CODE_DEDUPE_KEY = "preference:response_code"`; the prompt
  interpolates it (third `.replace`); the filter compares against the
  constant. Steering prose and enforcement regex stay where they are —
  only the *identity* is single-sourced.
- **Test survival**: `tests/reflect/test_memory_extract_distills_identity.py`
  must pass unchanged.
- **Deletion test verdict**: concentrates the key's identity — a rename
  otherwise requires lockstep edits in prompt text and code. RA-120 class;
  small but honest.

## Considered and declined

- `agent_state` vs `state` carrier-key naming divergence (memory_extract
  reads `agent_state`, `_resolve.py` reads `state`): noticed, but no
  failure evidence and two keys may be load-bearing for different
  harnesses → speculative.
- `_underlying_session`'s `("session", "inner")` attribute unwrap in
  `_session_observe.py`: one occurrence = hypothetical seam → not filed.
- Wider `getattr(runtime, …)` probe generalization (`brain`, `reducer`,
  `memory`, `hub`, `standing_refresher` across 10+ node modules): real
  sprawl, but a single generic `resolve_runtime_attr` seam would change
  many call sites at once — bigger than one honest story; note as a
  follow-on direction after RA-123 lands.
- The `_RESPONSE_CODE_PREFERENCE_RE` regex vs prompt rule text wording
  drift (prompt says 「答完只回复一句」, regex only matches 代号/验证码/
  口令/暗号): the filter is deliberately narrower (fail-open by design);
  not drift until evidence.

## Assessment complete: 3 stories written, top is RA-123.
