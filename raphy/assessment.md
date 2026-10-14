# Raphy Assessment — 2026-10-14 22:45 round (`raphy/arch-20261014-2245`)

Basis: main tip `5319d969d` (clean worktree). 3 hot areas read end-to-end;
runtime verification run on the clean worktree with `LLM_API_KEY=dummy`.
No code outside `raphy/` touched.

## Phase 1 — Explore

### Hot-spot scan (`git log --oneline -40`)

The last 40 commits are dominated by three lanes:
1. **raphy rounds** (RA-126–RA-141): `resolve_*` seam convergences
   (`resolve_runtime_state`, `resolve_runtime_brain`,
   `resolve_typed_port_or_runtime`, `resolve_assistant_binding`), private
   `_model` probe convergence, legacy `/answer` `is_rejection` gap (RA-138),
   approval `approved_tools` seam (RA-139), undeclared tools-port read
   (RA-140), `agt_* -> asst_*` binding convergence (RA-141).
2. **iter-quality / iter-tests**: capability drift-pin baseline regeneration,
   `GenericInMemoryRegistry` hygiene, lobehub mock auth recents fix,
   kernel-seeded tools/bindings in plan lift.
3. **In-flight uncommitted work on the main worktree** (not in this tip):
   `tool_wire_gate.py`, `tool_batch_executor.py`, `approval_engine.py`,
   `tool_defer/session.py`, `environment_awareness/__init__.py` — assessed
   against the tip; any OPTIMIZE on these files must rebase against whatever
   lands there first.

Hot areas chosen for the friction walk: (A) the approval seam
(`lca/infrastructure/runtime_plane/access/`), (B) the body tools gates
(`lca/cognition/body/tools/tool_wire_gate.py`,
`tool_batch_executor.py`), (C) the defer session
(`lca/infrastructure/tool_defer/session.py`).

### Organic friction walk

#### Area A — approval seam (`access/approval_engine.py` 300L,
`access/approved_tools.py` 66L, `access/classify.py` ~150L)

1. **Bouncing between small modules?** Yes. Answering "may this tool call
   run?" requires: `NamespaceApprovalStrategy` (engine) →
   `classify.decide_tool_call` / `machine_operation` / `call_paths` →
   `grant.default_access_scope` → `policy.decide_access` → the
   `approved_tools` ContextVar read in `act.authorize` (RA-140), plus the
   per-strategy `evaluate()` chain. The *authorization* question lives in two
   layers (approval engine strategies + `act.authorize` node); the engine's
   chain-of-responsibility shape is the right home, but the hand-rolled
   tool→namespace map inside `NamespaceApprovalStrategy.evaluate`
   (approval_engine.py:260-265) re-derives session internals instead of
   asking the session.
2. **Shallow modules?** `ApprovalPolicyRegistry` (register/list, ~15L) is
   thin but earns existence: deleting it moves the strategy-ordering
   contract into `build_default_approval_engine`, losing the "extensible
   rule injection" point. Not a candidate. `MachineAccessStrategy` is deep
   (reason/risk classification behind a 2-arg interface). No deletion-test
   failure found here.
3. **Pure functions hiding call-site bugs?** `classify.py` is exemplary:
   module docstring states "Pure. The plane is a parameter, not an ambient
   read, so the classification is testable without binding a run scope."
   Good locality. The counter-example is one directory away
   (see Area B).
4. **Leaky seams?** Yes — two places build the identical hand-rolled
   tool→namespace map from `session.namespaces`:
   - `approval_engine.py:262`: `for ns_obj in defer_session.namespaces:
     for tname in ns_obj.tool_names: session_tool_to_ns[tname] = ns_obj.name`
   - `tool_wire_gate.py:130`: `for ns_obj in session.namespaces:
     for tname in ns_obj.tool_names: tool_to_ns[tname] = ns_obj.name`
   
   Repo-wide grep confirms exactly these two occurrences ("two = real").
   The defer session's internal tuple shape leaks across the seam in both
   modules. → **RA-142**.
5. **Testability gaps?** The approved-set is ContextVar-backed (RA-133
   pinned the inheritance); tests configure it via fixtures, which is the
   documented pattern. No new gap.

#### Area B — body tools gates (`tool_wire_gate.py` 200L,
`tool_batch_executor.py` 306L, `action_handlers.py` caller)

1. **Bouncing?** Moderate. The blocked-call concept spans `tool_wire_gate`
   (three gates), `action_handlers.UseToolOperation` (the single caller of
   `unexposed_tool_block_observation`, line 240), and `_journal_blocked_call`.
   The three gates share one Observation contract — except one of them
   doesn't use the shared constructor (see Q4).
2. **Shallow modules?** `_wire_block_observation` is a genuinely deep
   single-constructor seam: one entry owns the blocking-Observation text
   contract (guidance single-sourced so product text cannot drift).
   `unexposed_tool_block_observation` builds its Observation **by hand**,
   duplicating the `extra` key contract (`FAILURE_KIND`,
   `OBS_RESULT_KIND`, `TOOL_WIRE_STATUS`, `TOOL_WIRE_REASON`) instead of
   going through the seam that exists precisely for it. If the constructor
   gains a key (telemetry, new failure dimension), the unexposed gate
   silently diverges. → **RA-143**.
3. **Pure functions hiding call-site bugs?** The module docstring claims
   "纯函数模块" (pure-function module), but
   `unexposed_tool_block_observation` performs a lazy
   `from lca.infrastructure.tool_defer.session import current_defer_session`
   inside the function body and reads the ambient ContextVar. The real
   decision input (this turn's defer view) hides in the call, not in the
   interface — exactly the shape this question hunts. Tests
   (`tests/scenario/test_wire_gate_namespace.py`) can only exercise the
   gate through a ContextVar fixture, i.e. by reaching past the interface.
   → **RA-144**.
4. **Leaky seams?** The unexposed gate re-renders the turn
   (`session.render_turn()`) and parses wire-spec dicts
   (`spec.get("function").get("name")`) to recover the visible tool set.
   The wire-spec dict shape is owned by `session._tool_to_spec` (and,
   knowingly, by `think.history.assemble._tool_to_spec`); the gate is a
   third reader of that shape. The session should answer "what is visible
   this turn" itself. → folded into **RA-142**'s shape note as the adjacent
   deepening (single occurrence, so kept inside the same story rather than
   a standalone "one adapter" abstraction).
5. **Testability gaps?** Same as Q3: the gate's interface is
   `(decision) -> Observation | None`, but its behavior depends on ambient
   session state. "The interface is the test surface" fails here.

Additionally, `_canonicalise_tool_name` (private, batch executor) and
`canonical_tool_name` (public, approved_tools) are twin snake↔camel
name-normalizers. RA-132 was dropped because the canonicalization mangles
namespaced names (e.g. `mcp_corp.do_thing` → `mcpCorp.doThing`, which then
matches nothing). The need is real (two occurrences); the shape was wrong.
A namespace-aware seam — split the namespace separator *before* munging,
never canonicalize across it — resolves the dropped story's trap.
→ **RA-145**.

#### Area C — defer session (`tool_defer/session.py` 348L)

1. **Bouncing?** The session lifecycle spans the run entry (ContextVar
   publish), `concept.tool.fork` dispatch (`update_turn`), and
   `think.history.assemble` (`render_turn`) — but `ToolDeferSession`
   itself is the home module; the sprawl is lifecycle, not duplication.
2. **Shallow?** No. `resolve_namespace` (exact → MCP alias → difflib
   suggestions behind one arg) and `search_catalog` (token-ranked search)
   are deep: rich behavior behind narrow interfaces. Deletion test passes
   (deleting the session concentrates turn-view logic into every caller).
3. **Pure functions?** N/A — this is a stateful run-scoped module by
   design; `update_turn`'s fail-soft "unknown namespace" parking is
   documented with the 2026-10-01 incident reference. Locality is good.
4. **Leaky seams?** `MCP_NAMESPACE_PREFIX` handling (`_mcp_aliases`)
   stays inside the module. The *outward* leak is the reverse: callers
   iterate `session.namespaces` / `ns.tool_names` by hand (see Area A Q4).
5. **Testability?** The session is directly constructible
   (`ToolDeferSession(policy)`); no ambient state needed to test the
   module itself. Good.

### Runtime verification (mandatory, clean worktree, `LLM_API_KEY=dummy`)

Ran the three required scenarios plus the 2026-10-07 P0 repro:

| # | Scenario | Result |
|---|----------|--------|
| a | basic run to COMPLETED | ✅ `status=completed` |
| b | run with a tool call (mock emits `NativeToolCall`) | ✅ `status=completed`, tool executed |
| c | two sequential runs on one agent | ✅ `completed` / `completed` |
| d | non-converging run (`max_steps=5`, infinite tool-call mock) | ✅ returns `Result(status=failed)`, `max_steps=5` honored |

**The 2026-10-07 P0 is fixed on this tip**: the non-converging run no
longer raises `LoopObligationExceededError` out of `agent.run()`; the loop
driver converts it to a failed Result (`lifecycle_event=failed
max_steps=5`). No crashes, hangs, or silent failures this round → no P0
candidate from runtime.

### Duplication scan (secondary)

Repo-wide grep for the map-construction shape confirms exactly two
occurrences (approval_engine.py:262, tool_wire_gate.py:130). The
`_tool_to_spec` twin between `tool_defer/session.py` and
`think.history.assemble` is documented as intentional ("Kept local on
purpose: infrastructure must not import L2 nodes") — not a candidate.

## Phase 2 — Self-grilling

### RA-142 — Converge the two hand-rolled tool→namespace maps onto a session-owned seam

- **Files**: `lca/infrastructure/tool_defer/session.py`,
  `lca/infrastructure/runtime_plane/access/approval_engine.py`
  (`NamespaceApprovalStrategy.evaluate`, ~line 260),
  `lca/cognition/body/tools/tool_wire_gate.py`
  (`unexposed_tool_block_observation`, ~line 128).
- **Problem**: Two verbatim-shape loops derive `{tool_name: namespace}`
  from `session.namespaces` by hand ("two = real"). The session's internal
  tuple shape leaks across the seam into the approval strategy and the
  wire gate.
- **Solution**: Add a session-owned seam, e.g.
  `ToolDeferSession.namespace_of_tool(name) -> str | None` (backed by one
  internal map built in `update_turn`), and converge both call sites onto
  it. Adjacent: the unexposed gate's wire-spec dict parsing
  (`spec.get("function").get("name")` → visible set) also moves behind a
  session seam (e.g. `turn_visible_tool_names()`), since the session owns
  the wire shape.
- **Benefits**: locality — the namespaces-tuple traversal lives only in
  the module that owns the tuple; leverage — future callers ask the
  session instead of re-deriving; the lazy `current_defer_session` import
  inside `NamespaceApprovalStrategy.evaluate` stays as-is (import-cycle
  constraint, see below).
- **Strength**: Strong.
- **Constraints**: The lazy import of `current_defer_session` inside
  `NamespaceApprovalStrategy.evaluate` must stay lazy (engine ← session
  import direction would cycle). Behavior: unknown tool → `None`
  (namespace gate treats as unmapped, same as today's missing key).
  ADR-0246 §1.1 (authorization vs consent separate) untouched.
- **Dependencies**: callers of the seam = the two converged sites;
  `update_turn` becomes the single place the map is rebuilt.
  `render_turn()` semantics unchanged.
- **Shape of the deepened module**: `ToolDeferSession` gains
  `namespace_of_tool()` (+ optionally `turn_visible_tool_names()`); the
  map is derived from `self._namespaces` in `update_turn`.
- **Test survival**: `tests/scenario/test_wire_gate_namespace.py` (C1–C4)
  pins the unexposed gate behavior; `test_namespace_approval_strategy.py`
  pins the namespace strategy. New seam-level test: map hit/miss/unknown.
- **Deletion test verdict**: concentrates — deleting the seam moves the
  traversal back into two modules; the seam earns its existence.

### RA-143 — Route `unexposed_tool_block_observation` through the `_wire_block_observation` constructor seam

- **Files**: `lca/cognition/body/tools/tool_wire_gate.py`.
- **Problem**: The module's own docstring for `_wire_block_observation`
  says "Single constructor seam for wire-gate blocking Observations…
  the guidance text is single-sourced here so the product text cannot
  drift between gates." The unexposed gate bypasses it, hand-building the
  Observation and duplicating the `extra` key contract.
- **Solution**: Build the unexposed block via `_wire_block_observation`
  with `status=TOOL_WIRE_INVALID`, `reason="namespace_not_loaded"`,
  the namespace message as `middle_parts`, and the
  "Call tool_search for its namespace before using it." instruction as the
  `guidance` argument (the constructor already accepts a per-call
  guidance override — the shorten/split default is wrong for this gate).
- **Benefits**: locality — the blocked-Observation `extra` contract has
  one owner; leverage — future gates inherit the contract; text cannot
  drift between gates.
- **Strength**: Strong.
- **Constraints**: The model-facing message must stay byte-equivalent
  (memory/history pins it; `test_wire_gate_namespace.py` C1 asserts the
  block). The `finish_reason`/`raw_preview` passthrough stays as-is.
- **Dependencies**: only the two existing constructor callers
  (`tool_wire_block_observation`, `missing_arguments_block_observation`);
  no caller of the unexposed gate changes.
- **Shape of the deepened module**: the gate becomes condition + names;
  all Observation construction flows through one seam.
- **Test survival**: `tests/scenario/test_wire_gate_namespace.py`
  (C1–C4, F2–F3) must stay green; new assertion: unexposed block carries
  the same `extra` key set as the other gates.
- **Deletion test verdict**: concentrates — the constructor already
  exists; the bypass is pure drift surface.

### RA-144 — Make the defer-session dependency of the unexposed gate explicit (restore the pure-function contract)

- **Files**: `lca/cognition/body/tools/tool_wire_gate.py`,
  `lca/cognition/body/actions/action_handlers.py` (sole caller, ~line 240),
  `tests/scenario/test_wire_gate_namespace.py`.
- **Problem**: The module docstring claims "纯函数模块", but
  `unexposed_tool_block_observation` lazily imports and reads the ambient
  `current_defer_session()` ContextVar inside its body. The interface
  `(decision) -> Observation | None` lies about its inputs; "the
  interface is the test surface" fails — the gate is only testable via a
  ContextVar fixture.
- **Solution**: Accept the session (or the turn view) as an explicit
  parameter, e.g. `unexposed_tool_block_observation(decision, defer_session=None)`
  with `None` falling back to the ambient read (keeps the single caller
  compiling; the fallback keeps the legacy no-session path). The sole
  caller in `action_handlers.py` reads the ContextVar once at the
  boundary and passes it in.
- **Benefits**: locality — the ambient read moves to the action
  boundary; leverage — the gate becomes unit-testable through its
  interface without ContextVar plumbing; the "pure-function module"
  claim becomes true again.
- **Strength**: Worth exploring.
- **Constraints**: The `session is None or not policy.enabled or not
  namespaces` early-return semantics must be preserved exactly (legacy
  full-list path). No behavior change for callers that pass nothing.
- **Dependencies**: one caller (`action_handlers.py:240`); the lazy
  import moves to the caller boundary.
- **Shape of the deepened module**: gate = pure function of
  `(decision, session)`; ambient state lives at the action layer.
- **Test survival**: `tests/scenario/test_wire_gate_namespace.py` C1–C4
  must pass with the session passed explicitly (fixture can drop the
  ContextVar and construct the assertion directly — that is the point).
- **Deletion test verdict**: concentrates — the boundary owns "where
  does the turn view come from"; the gate owns "is this call exposed".

### RA-145 — One namespace-aware tool-name canonicalization seam (resolves RA-132's trap)

- **Files**: `lca/cognition/body/tools/tool_batch_executor.py`
  (`_canonicalise_tool_name`), `lca/infrastructure/runtime_plane/access/approved_tools.py`
  (`canonical_tool_name`).
- **Problem**: Two snake↔camel name normalizers exist for the same reason
  (the LLM emits either case style; the registry keeps one). RA-132 was
  dropped because canonicalization mangles namespaced names
  (`mcp_corp.do_thing` → `mcpCorp.doThing`, matching nothing — silent
  lookup/match failure). Both current implementations cross the namespace
  separator.
- **Solution**: One shared seam that splits the namespace separator
  *first* and canonicalizes only the bare tool name, never crossing the
  separator (e.g. `mcp_corp.do_thing` → separator-aware
  `mcp_corp.doThing`, or documented no-match). Converge both call sites
  onto it.
- **Benefits**: locality — the "where does the namespace end" rule lives
  in one place; leverage — fixes the silent-failure class RA-132
  discovered, for both approval matching and registry fallback lookup.
- **Strength**: Worth exploring.
- **Constraints**: must not re-litigate RA-132's dropped assessment —
  the new story's acceptance criteria must pin namespaced names as
  preserved (the exact trap). `cron.update`-style dotted names and
  `mcp_` prefixed namespaces are the regression cases.
- **Dependencies**: callers = batch executor's tolerant fallback and the
  approval-set matching path; registry naming convention (camelCase per
  LobeHub wire) unchanged.
- **Shape of the deepened module**: a single `canonical_tool_name`-family
  function with separator awareness; the private twin is deleted.
- **Test survival**: existing approval/batch tests stay green; new tests:
  namespaced snake/camel pairs round-trip, bare names behave as today.
- **Deletion test verdict**: concentrates — the separator rule is the
  subtle part; two copies would re-diverge on it.

## Phase 3 — Candidate table & recommendation

| ID | Files | Problem | Solution | Benefits (locality+leverage) | Strength |
|----|-------|---------|----------|------------------------------|----------|
| RA-142 | session.py, approval_engine.py, tool_wire_gate.py | two hand-rolled tool→namespace maps leak session internals | session-owned `namespace_of_tool()` (+ visible-set) seam | traversal locality in the owning module; future callers ask, not re-derive | Strong |
| RA-143 | tool_wire_gate.py | unexposed gate bypasses the single Observation constructor | route through `_wire_block_observation` with per-gate guidance | `extra` contract has one owner; text cannot drift | Strong |
| RA-144 | tool_wire_gate.py, action_handlers.py | gate reads ambient ContextVar despite "pure-function module" claim | explicit session parameter, ambient read at boundary | testable through the interface; claim becomes true | Worth exploring |
| RA-145 | tool_batch_executor.py, approved_tools.py | twin snake↔camel normalizers; both mangle namespaced names (RA-132's trap) | one separator-aware canonicalization seam | separator rule in one place; fixes silent-failure class | Worth exploring |

**Top recommendation**: RA-142 first. It is the cleanest "two = real"
in this round — two verbatim-shape loops, one owning module, zero
behavioral risk, and it deepens the session module that RA-144 will build
on. RA-143 is the natural second: same file, same gate, mechanical once
the message contract is pinned.

**Diversity quota**: satisfied — all four stories come from the friction
walk (leaky seams ×2, shallow/bypassed constructor, testability gap);
none is pure mechanical duplication.

## Runtime verification record

Environment: clean worktree at main tip `5319d969d`,
`PYTHONPATH=<worktree>`, `LLM_API_KEY=dummy`. Scenarios a–d all green
(see table above). The 2026-10-07 P0 (non-converging run raising
`LoopObligationExceededError` out of `agent.run()`) is **verified fixed**
on this tip: the loop driver now converts it to `Result(status=failed)`
with `max_steps` honored. No P0 candidate this round.
