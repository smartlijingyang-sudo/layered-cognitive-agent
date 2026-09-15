# Agent Note: `@graph_node` DSL + phase-helper graph-nodeification — PR3

Status: implemented

## Problem

After PR2, three think subgraph nodes (`think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`) are already typed — but each required a hand-written `NodeExecutor` dataclass plus a `@plugin(...)` setup carrier (boilerplate mirrored in `lca/plugins/concept/context_compose/collect.py:39-108` and `lca/plugins/think/history_assemble/execute.py:42-118`). The pattern is mechanical: a frozen dataclass with `semantic_name` / `region` / `declared_inputs` / `declared_outputs`, an `async node_execute(context, input)` that reads typed ports (with `context.runtime` fallback), and a `@plugin(...)` carrier whose `setup()` constructs the executor and calls `ctx.provide(f"{region}::{semantic_name}", executor)`. PR2 paid the boilerplate tax three times; PR3 will pay it at minimum eight more times (one per closed-set phase) plus body-loop and reasoner helpers. The user-stated scope in spec §K is "the real 图节点化 deliverable — making the graph a graph, not imperative while-loops over dataclass-of-everything." hermes-agent's anti-pattern is the explicit foil — a `_LoopState` dataclass with 30+ fields threaded through `_run_phase`-style introspection. LCA's current `lca/harness/workflow/engine.py:_run_phase` and the observability adapter helpers `_open_think_step` / `_advance_think_fold` (`lca/infrastructure/observability/adapters/adapters.py:364-386`) carry the same shape (mixed concerns, read-many-fields, dispatch by string).

## Decision

PR3 adds a `@graph_node` decorator in `lca/framework/graph/nodes/decorator.py` that produces the same artifact the hand-written `NodeExecutor` + `@plugin(...)` pair produces today, but from a single function definition. The decorator:

- Wraps an `async def fn(*, state, …) -> SomeTypedOutput` into a frozen `@dataclass(slots=True)` holding `semantic_name`, `region`, `declared_inputs`, `declared_outputs`, and a bound reference to the function.
- Implements `async def node_execute(self, context, input)` that resolves each declared input port from `input.port_values[name]` with `context.runtime[name]` fallback (mirrors `context_compose/collect.py:55-65` and `history_assemble/execute.py:62-79`), calls the function with resolved values as keyword arguments, and builds `NodeOutput(port_values=…)` keyed by `declared_outputs`.
- Evaluates the optional `terminal_predicate(output, state)` and stows the verdict ("continue" | "exit") in `NodeOutput.next_hint`; the runtime kernel reads `next_hint` to decide whether to advance the edge or short-circuit the phase loop.
- Returns a `@plugin(...)` carrier with the same `PluginContract` + `OwnershipDeclaration` shape used in PR2; the carrier's `setup()` registers under the composite key `f"{region}::{id}"`.
- Constrains `region` to the six-phase closed set (`perceive` | `think` | `act` | `remember` | `reflect` | `stop`); other values raise `ValueError` at decoration time (immediate feedback at module import).

The phase graph becomes a graph of typed `@graph_node`s. The conversion targets are:

- `lca/harness/workflow/engine.py:_run_phase` — split into per-phase `@graph_node`s (`perceive.fold`, `think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`, `act.body.dispatch`, `remember.memory.write`, `reflect.critique`, `stop.terminal_check`); the `_run_phase` while-loop driver is deleted.
- `lca/infrastructure/observability/adapters/adapters.py:_advance_think_fold` and `_open_think_step` — replaced by `terminal_predicate` on `think.decision.parse`; the imperative helpers that read `_LoopState.<ok>` and emit on success/failure are deleted.
- `lca/cognition/body/executor/simple_body.py:act()` body-loop helpers — split into per-step `@graph_node`s (`act.body.dispatch`, `act.observe`).
- `lca/cognition/brain/reasoner/reasoner.py:PromptReasoner` turn-iteration helpers — split into per-turn `@graph_node`s; the three PR2 nodes (`think.history.assemble`, `think.llm.dispatch`, `think.decision.parse`) are reused and re-decorated in T2-T3 as the canonical demonstration.

The `RunSessionWriter` plugin slot that ADR-0226 deferred to PR3 closes via the decorator's `inputs=("state", "writer")` keyword — no second Protocol is added; `RunSessionWriterProtocol` is the typed seam.

## Alternatives considered

- **Keep the hand-written `NodeExecutor` pattern.** Rejected: the pattern is mechanical, repeated 3× in PR2 alone, and PR3 will repeat it at minimum 8 more times. Two is a coincidence; three is an abstraction. PR2 was the third.
- **Use a different DSL (LangGraph `@entry` / `@task`, Temporal `@workflow.defn`).** Rejected: LCA already has `NodeExecutor` + `NodeContext`; building a parallel DSL violates AGENTS.md §4 (no parallel mechanism) and re-implements the typed-boundary contract that the existing Protocol already enforces.
- **Compile-time code-gen from yaml.** Rejected: PR3's scope is the runtime decorator + first batch of conversions; yaml-driven codegen is a follow-up PR. The decorator is the runtime primitive; codegen sits above it.
- **Make `terminal_predicate` a yaml expression.** Rejected: a Python callable is the smallest mechanism that fits (per AGENTS.md §3: prefer the simplest standard-library or framework primitive that fits). yaml expressions would require a Python eval sandbox or a new mini-language.
- **Convert all plugin `NodeExecutor` instances in this PR.** Rejected: AGENTS.md §5 requires every converted plugin to update its consumers + tests in the same PR; converting the entire plugin surface in one PR would explode review surface. The plan scopes T2-T6 to the phase helpers and the per-step body / reasoner helpers called out in spec §K.

## Consequences

- The phase graph becomes a graph of typed `@graph_node`s; `_run_phase`-style introspection (which reads dataclass-of-everything fields like `_LoopState`) is deleted.
- Plugin authors write one function definition per node instead of three (dataclass + `node_execute` + `@plugin(...)` setup). The function body is the only per-node variation; everything else is declarative at the decorator call site.
- New typed-boundary edges replace string-typed conditionals (`if _LoopState.ok: …`). The terminal-exit mechanism is `terminal_predicate`, evaluated by the runtime kernel, not a private field read.
- The six-phase closed-set integrity is preserved: `region` is constrained at decoration time; no new phases or event names are added. AGENTS.md §3 C1 closed-set requirement satisfied.
- AGENTS.md §3 C13 (information lineage closed) is satisfied: every `@graph_node` carries `declared_inputs` / `declared_outputs` typed as `tuple[PortName, ...]` at the decorator call site.
- The `RunSessionWriter` plugin slot from ADR-0226 lands via the decorator's `inputs=("state", "writer")` keyword; no second Protocol is added.
- Tests added in `tests/unit/`: `test_graph_node_decorator.py` (decorator contract), `test_conversation_loop_graph_node.py` (phase helpers are `@graph_node`s). Existing PR2 integration tests (`test_run_with_tool_use.py`, `test_persist_before_execute.py`, `test_orphan_tool_result_drop.py`) continue to pass without modification.
- Out of scope (follow-up PRs): yaml-driven codegen from `@graph_node` definitions; conversion of plugin manifests outside the plan's enumerated files; cross-region edge wiring; removing all hand-written `NodeExecutor` patterns outside this PR's scope.

## Cross-references

- ADR: [docs/adr/0227-graph-node-dsl.md](../../../adr/0227-graph-node-dsl.md)
- Spec: [docs/superpowers/specs/2026-09-15-session-write-path-design.md](../../../superpowers/specs/2026-09-15-session-write-path-design.md) §K
- Plan: [docs/superpowers/plans/2026-09-15-pr3-graph-node-dsl.md](../../../superpowers/plans/2026-09-15-pr3-graph-node-dsl.md)
- Prior ADR (PR2): [docs/adr/0226-session-write-path-collapse.md](../../../adr/0226-session-write-path-collapse.md) (deferred the `RunSessionWriter` plugin slot to PR3)
- Prior note (PR2): [docs/notes/implemented/seam/2026-09-15-pr2-write-path-refactor.md](../seam/2026-09-15-pr2-write-path-refactor.md)
- Prior ADR (PR1): [docs/adr/0225-drop-max-visits-graph-invariant.md](../../../adr/0225-drop-max-visits-graph-invariant.md)
- Prior note (PR1): [docs/notes/implemented/seam/2026-09-15-pr1-drop-max-visits.md](../seam/2026-09-15-pr1-drop-max-visits.md)
