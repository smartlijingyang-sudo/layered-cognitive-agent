# ADR-0227: `@graph_node` DSL — typed-boundary decorator for phase helpers

## Status

Proposed → Implemented in the same PR (PR3 of the session-write-path redesign; PR2 introduced three typed graph nodes by hand, PR1 dropped `max_visits` per ADR-0225)

## Context

After PR1 + PR2, three think subgraph nodes are already typed — `think.history.assemble`, `think.llm.dispatch`, `think.decision.parse` — but each required a hand-written `NodeExecutor` dataclass plus a `@plugin(...)` setup carrier (the boilerplate lives in `lca/plugins/concept/context_compose/collect.py:39-108` and `lca/plugins/think/history_assemble/execute.py:42-118`). The pattern is mechanical:

1. A frozen `@dataclass(slots=True)` holding `semantic_name`, `region`, `declared_inputs`, `declared_outputs`.
2. An `async def node_execute(self, context, input)` that reads typed port values (with `context.runtime` fallback) and returns a `NodeOutput(port_values=…)`.
3. A `@plugin(id=…, provides=…, requires=(), layer=…, kind=…, effects=…, contract=…, ownership=…)` carrier whose `setup()` constructs the executor and calls `ctx.provide(f"{region}::{semantic_name}", executor)`.

The same shape is going to repeat for every phase helper (`perceive`, `think`, `act`, `remember`, `reflect`, `stop`) and every body / reasoner turn helper. PR2 already paid the boilerplate tax three times; PR3 will pay it at minimum eight more times (one per phase per closed-set phase) plus the body-loop and reasoner-loop helpers called out in the spec. The pattern is mechanical — it has no per-node variation beyond the port names, the function body, and an optional `terminal_predicate`. Hand-writing it each time violates AGENTS.md §3 modularity ("Plugin points are real only when at least two implementations exist…") in reverse: a recurring *implementation* pattern is a seam-without-an-abstraction, paid by every reader of every `execute.py`.

The user-stated scope in `docs/superpowers/specs/2026-09-15-session-write-path-design.md` §K is unambiguous: "**the real 图节点化 deliverable** — making the graph a graph, not imperative while-loops over dataclass-of-everything." hermes-agent's anti-pattern is the explicit foil — a `_LoopState` dataclass with 30+ fields threaded through `_run_phase`-style introspection, where the loop driver reads each field by name and dispatches on string-typed conditionals. LCA's current phase helpers in `lca/harness/workflow/engine.py:_run_phase` and the observability adapter helpers `_open_think_step` / `_advance_think_fold` carry the same shape (mixed concerns, read-many-fields, dispatch by string). The `NodeExecutor` Protocol at `lca/contracts/protocols/declarative/declarative_1/node_executor.py` is the typed-boundary primitive, but the boilerplate around it buries the contract.

This is closed-set-adjacent in two ways:

- AGENTS.md §3 C1 (cognitive closed set): adding a `@graph_node` decorator does **not** add a phase. It is a typed-boundary mechanism over the existing six-phase closed set. The closed-set integrity is preserved as long as `region` is constrained to the existing six values and `terminal_predicate` is the *only* way to short-circuit the runtime loop (no new event names, no new graph nodes beyond the per-phase ones already enumerated in the plan).
- AGENTS.md §3 C13 (information lineage closed): every typed-boundary decorator invocation must carry `declared_inputs` / `declared_outputs` typed at compile time. The decorator's `inputs: tuple[str, ...]` / `outputs: tuple[str, ...]` keyword arguments satisfy this; the runtime kernel reads them as `PortName` tuples the same way the hand-written `NodeExecutor` does.

AGENTS.md §1 (接任务前 7 问) requires an ADR for "改变闭集/层边界/SSOT/能力模型" and "改变已有契约, ADR/Protocol 可表达" — both apply here. The decorator is a typed-boundary DSL; the runtime kernel's contract with nodes is unchanged (still `NodeExecutor` Protocol, still `NodeContext` + `NodeInput` + `NodeOutput`); the plugin slot for `RunSessionWriter` that ADR-0226 deferred to PR3 also lands via this DSL.

## Decision

Add a `@graph_node` decorator in `lca/framework/graph/nodes/decorator.py` that produces the same artifact the hand-written `NodeExecutor` + `@plugin(...)` setup pair produces today, but from a single function definition. Convert the imperative phase helpers to `@graph_node`s in tasks 4-6 of this PR. **No COMPAT shim.** AGENTS.md §4: a COMPAT shim without a delete-when is 红灯; the imperative path is deleted in the same PR.

### 1. Decorator API

```python
@graph_node(
    id: str,                                 # semantic_name, e.g. "think.history.assemble"
    region: str,                             # "perceive" | "think" | "act" | "remember" | "reflect" | "stop"
    inputs: tuple[str, ...] = (),            # declared_inputs (PortName, ...)
    outputs: tuple[str, ...] = (),           # declared_outputs (PortName, ...)
    terminal: Callable | None = None,        # terminal_predicate; (output, state) -> ("continue" | "exit", state)
    effects: str = "none",                   # for PluginContract
    layer: str = "L2",                       # for PluginContract
)
async def my_node(*, state, ...) -> SomeTypedOutput:
    ...
```

The decorator:

1. Wraps `my_node` into a frozen `@dataclass(slots=True)` (`MyNodeExecutor`) holding `semantic_name`, `region`, `declared_inputs`, `declared_outputs`, and a bound reference to the original function.
2. Implements `async def node_execute(self, context, input)`:
   - Resolves each declared input port by reading `input.port_values[name]`; on miss, falls back to `context.runtime[name]` (mirrors `context_compose/collect.py:55-65` and `history_assemble/execute.py:62-79`).
   - Calls the original function with the resolved values as keyword arguments.
   - Builds `NodeOutput(port_values={name: value for name, value in zip(declared_outputs, return_value_or_tuple)})`.
   - If `terminal` is set, evaluates `terminal(output, state)` and stows the verdict in `NodeOutput.next_hint` ("continue" | "exit"); the runtime kernel reads `next_hint` to decide whether to advance to the next edge or short-circuit the phase loop.
3. Returns a `@plugin(id="phase.<region>.<id>", Config=None, provides=(f"{region}::{id}",), requires=(), layer=layer, kind=PluginKind.PRIMITIVE, effects=effects, contract=PluginContract(...), ownership=OwnershipDeclaration(...))` carrier.
4. The carrier's `setup(ctx, config=None)` constructs the dataclass and calls `ctx.provide(f"{region}::{semantic_name}", executor)` — identical to the hand-written `setup()` in `context_compose/collect.py:103-108` and `history_assemble/execute.py:113-118`.

### 2. `terminal_predicate` as the only loop-exit mechanism

Per spec §E, `terminal_predicate` is a function from `(node_output, state) -> ("continue" | "exit", state)` evaluated after each node invocation. The runtime kernel reads `NodeOutput.next_hint` and either advances to the next edge (`continue`) or breaks the phase loop (`exit`). This replaces the imperative `_run_phase` `if/elif` ladder on `_LoopState.<field>` and the `_advance_think_fold` / `_open_think_step` observability helpers.

The decorator does **not** add a new event or phase. The runtime kernel already supports edge-driven traversal; `terminal_predicate` is a per-node exit-condition expression, not a control-flow primitive.

### 3. Region constraint

`region` is constrained to the six-phase closed set: `perceive`, `think`, `act`, `remember`, `reflect`, `stop`. Any other value raises `ValueError` at decoration time. This is enforced by a runtime check in the decorator body, not a `Literal` type, so plugin authors get a clear error at module import (where `@plugin` runs) rather than at runtime invocation.

### 4. Conversion targets

The PR converts the following imperative phase helpers to `@graph_node`s:

- `lca/harness/workflow/engine.py:_run_phase` — split into per-phase `@graph_node`s (`perceive.fold`, `think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`, `act.body.dispatch`, `remember.memory.write`, `reflect.critique`, `stop.terminal_check`); the `_run_phase` while-loop driver is deleted.
- `lca/infrastructure/observability/adapters/adapters.py:_advance_think_fold` and `_open_think_step` — replaced by the `terminal_predicate` on `think.decision.parse`; the imperative helpers that read `_LoopState.<ok>` and emit on success/failure are deleted.
- `lca/cognition/body/executor/simple_body.py:act()` body-loop helpers — split into per-step `@graph_node`s (`act.body.dispatch`, `act.observe`).
- `lca/cognition/brain/reasoner/reasoner.py:PromptReasoner` turn-iteration helpers — split into per-turn `@graph_node`s (`think.history.assemble` reuses PR2's; `think.llm.dispatch` reuses PR2's; `think.decision.parse` reuses PR2's).

Each conversion lands as a separate task (T2-T7 of the plan). The existing PR2 typed nodes (`think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`) are converted from their hand-written `execute.py` to the `@graph_node` decorator in T2-T3 as the canonical demonstration.

### 5. Plugin slot for `RunSessionWriter` (deferred from ADR-0226)

ADR-0226 §Consequences deferred the `RunSessionWriter` plugin slot to PR3 "once the `@graph_node` DSL provides a typed way to express the seam". PR3 closes that loop: the `inputs=("state", "writer")` keyword argument becomes the typed seam; plugin authors type the `writer` parameter as `RunSessionWriterProtocol`; the runtime kernel's port-resolution layer injects the bound writer at `node_execute` time. No second Protocol is added; the existing `RunSessionWriterProtocol` is the seam.

### 6. Tests

- `tests/unit/framework/graph/nodes/test_graph_node_decorator.py` — pins the decorator's contract: (a) `semantic_name` / `region` / `declared_inputs` / `declared_outputs` are exposed as attributes on the resulting dataclass; (b) `terminal_predicate` is evaluated and its verdict appears in `NodeOutput.next_hint`; (c) the result is a `@plugin(...)` carrier whose `setup()` registers under `f"{region}::{semantic_name}"`.
- `tests/unit/plugins/think/test_history_assemble_plugin.py` — the existing PR2 test continues to pass against the `@graph_node`-decorated version (the surface is identical).
- `tests/unit/agent/test_conversation_loop_graph_node.py` — new test that asserts each phase helper is now a `@graph_node` and registers under the expected composite key.
- `tests/integration/test_run_with_tool_use.py` (PR2) — re-run the `run_cc39610072bf` regression end to end; no change to expected behavior.
- `tests/integration/test_persist_before_execute.py` (PR2) — no change.
- `tests/integration/test_orphan_tool_result_drop.py` (PR2) — no change.

### 7. What this PR does **not** do

- **YAML-driven codegen** — reading a yaml bundle and generating `@graph_node` invocations is a follow-up PR.
- **Conversion of plugin manifests outside the plan's enumerated files** — every plugin gets `@graph_node`'d in a separate batch once PR3 lands.
- **Cross-region edge wiring** — the runtime kernel already supports edges; PR3 doesn't add new edge types.
- **Removing all hand-written `NodeExecutor` patterns outside this PR's scope** — plugins outside the conversion targets keep their existing shape until they're individually converted in follow-up PRs (explicitly scoped out per the plan's "Out of scope" section).

## Consequences

- The phase graph becomes a graph of typed `@graph_node`s; `_run_phase`-style introspection (which reads dataclass-of-everything fields like `_LoopState`) is deleted. The runtime kernel reads `declared_inputs` / `declared_outputs` from each `@graph_node` to validate the bundle composition.
- Plugin authors write one function definition per node instead of three (dataclass + `node_execute` + `@plugin(...)` setup). The function body is the only per-node variation; everything else is declarative at the decorator call site.
- New typed-boundary edges replace string-typed conditionals (`if _LoopState.ok: …`). The terminal-exit mechanism is `terminal_predicate`, evaluated by the runtime kernel, not a private field read.
- The closed-set integrity of the six-phase set is preserved: `region` is constrained at decoration time; no new phases are added.
- AGENTS.md §3 C13 (information lineage closed) is satisfied: every `@graph_node` carries `declared_inputs` / `declared_outputs` typed as `tuple[PortName, ...]` at the decorator call site; the runtime kernel reads them the same way the hand-written `NodeExecutor` does.
- `RunSessionWriter` becomes a typed seam via the decorator's `inputs=("state", "writer")` keyword, closing the ADR-0226 deferred plugin slot.
- Tests added in `tests/unit/`: `test_graph_node_decorator.py` (decorator contract), `test_conversation_loop_graph_node.py` (phase helpers are `@graph_node`s). Existing PR2 integration tests continue to pass without modification.

## Alternatives considered

- **Keep the hand-written `NodeExecutor` pattern.** Rejected: the pattern is mechanical, repeated 3× in PR2 alone (and PR2 itself noted it as debt to be generalized), and PR3 will repeat it at minimum 8 more times. Per AGENTS.md §3 modularity, a recurring implementation pattern is a seam-without-an-abstraction paid by every reader of every `execute.py`. Two is a coincidence; three is an abstraction. PR2 was the third.
- **Use a different DSL (e.g. LangGraph `@entry` / `@task`, Temporal `@workflow.defn`).** Rejected: LCA already has `NodeExecutor` + `NodeContext` + `NodeInput` + `NodeOutput`; building a parallel DSL would violate AGENTS.md §4 (no parallel mechanism) and re-implement the typed-boundary contract that the existing Protocol already enforces. The `@graph_node` decorator produces a `NodeExecutor`-shaped dataclass; it does not replace the Protocol.
- **Compile-time code-gen from yaml.** Rejected: PR3's scope is the runtime decorator + first batch of conversions. yaml-driven codegen is a follow-up PR per the plan's "Out of scope" section. The decorator is the runtime primitive; codegen sits above it.
- **Make `terminal_predicate` a yaml expression.** Rejected: the predicate reads `(output, state)` and returns a tuple; yaml expressions would require re-implementing a Python eval sandbox or shipping a new mini-language. A Python callable is the smallest mechanism that fits (per AGENTS.md §3: "Prefer the simplest standard-library or framework primitive that fits").
- **Constraint `region` via `typing.Literal` only.** Rejected: `Literal` errors are deferred to the call site; a runtime check at decoration time fails at module import (where `@plugin(...)` runs), giving plugin authors immediate feedback when they mistype a region.
- **Convert all plugin `NodeExecutor` instances in this PR.** Rejected: AGENTS.md §5 (change closed loop) requires that every converted plugin update its consumers + tests in the same PR; converting the entire plugin surface in one PR would explode review surface and block the follow-up batch. The plan scopes T2-T6 to the phase helpers and the per-step body / reasoner helpers called out in spec §K.
- **Add a Protocol for the decorator's output dataclass.** Rejected: one implementation (the decorator itself); a Protocol-with-one-impl is speculative abstraction per AGENTS.md §3 modularity. The existing `NodeExecutor` Protocol is the seam; the decorator produces a `NodeExecutor`-conforming dataclass.
