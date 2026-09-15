# Agent Note: node-level emit dispatch wired to driver

Status: implemented

## Problem

BundleGraphSpec v2 schema (`docs/specs/2026-09-10-nested-bundle-graph-spec.md` + ADR-0217) declares two per-node fields, `emit_on_enter` and `emit_on_exit`, under `node.config`. The schema allowed them, the boot-time validator `NodeEventEmissionCheck` read them at lift, and the dispatcher `lca/loop/emit/node_emitter.py` mapped EP IDs to `emit_*_for_state` helpers. The runtime driver did not call the dispatcher at node enter / exit, so the values were validated for type and non-emptiness and otherwise inert.

The two surfaces that published spine EPs in production (`lca/infrastructure/session/emit/cognitive_emit.py` + `lca/loop/commit/tool_journal.py`) were reached through explicit `publish_ep_bound` calls from executor code, not through the dispatcher. act subgraph's five `emit_on_enter` / `emit_on_exit` entries (`bundles/act/act_subgraph.yaml`) advertised the same EPs that the act executor commits imperatively — the yaml field was documentation of intent, not the trigger.

The remaining gap was concrete:

- `lca/loop/emit/node_emitter.py:43` `emit_for_node(ep_id, state, **kwargs)` existed and dispatched to a 10-entry `_EP_DISPATCH` table.
- No import of `emit_for_node` existed in any driver path. The closest plan reference was `docs/superpowers/plans/2026-09-10-nested-bundle-graph-v1.md` PR-2, described but not implemented.
- The validator (`lca_kernel/boot/plan_validation/checks/node_event_emission.py`) was **commented out** of `DEFAULT_CHECKS` (`lca_kernel/boot/plan_validation/__init__.py:585`). When re-enabled, it checked `node.config["emit_on_enter"]` / `node.config["emit_on_exit"]`, but the lifter (`lca/framework/graph/lifter.py:131`) sets `node.config = dict(raw)` where `raw` is the entire node mapping. The validator therefore read from `raw["emit_on_enter"]`, while yaml declarations lived at `raw["config"]["emit_on_enter"]` — the path was off by one level and the check never found values declared in the conventional shape.

## Decision

The node-graph driver (`lca/framework/graph/strategies/node_executor_strategy.py:NodeExecutorStrategy.execute`) now reads `emit_on_enter` / `emit_on_exit` from `context.node_config["config"][...]` before and after the executor call, falling back to `context.node_config[...]` for hand-built plans, and forwards each entry to `emit_for_node`. Dispatcher failures are contained with `contextlib.suppress(Exception)` so a misconfigured EP does not abort the graph.

`NodeEventEmissionCheck._read_emits` probes both `node.config[key]` and `node.config["config"][key]` before declaring absence; malformed-type detection survives the two-path probe (top-level wins when both are well-typed).

The `_EP_DISPATCH` table in `lca/loop/emit/node_emitter.py` was extended from 11 to 21 entries covering 10 new EPs (ADR-0240 §Decision: `terminal.commit`, `phase.{perceive,think,reflect,remember,stop}.fold`, `phase.act.fold.start`, `think.gate.end`, `phase_graph.subgraph.{enter,exit}`). Each new entry maps to a thin `emit_*_for_state` helper in `lca/infrastructure/session/emit/cognitive_emit.py` that calls `publish_ep_bound` with a minimal payload (`{"state_id": state.trace_id}`).

The validator remains commented out of `DEFAULT_CHECKS` for now; re-enabling is deferred until the kernel cutover evidence accumulates production runs that exercise the new EP flow.

## Verification

- `pytest tests/framework/graph/test_node_executor_strategy_emit.py` — 6/6 pass (nested + flat path, empty list, dispatcher failure containment, multi-EP order).
- `pytest tests/lca_kernel/boot/test_node_event_emission_check.py` — 13/13 pass (10 original + 3 new for nested-shape, top-level-shape, malformed-nested).
- `pytest tests/framework/graph/ tests/lca_kernel/boot/` — 204 pass, 3 baseline failures pre-existing in `test_ports.py::TestDedupInvariantHolds` (verified via `git stash`).
- All 10 new EP names verified present in runtime `EXECUTION_POINTS` (loaded from `lca_kernel/events/payloads/spine.py:SPINE_EXECUTION_POINTS`, per ADR-0240 finding that `meta_event_taxonomy.py` is a partial duplicate, not the runtime SSOT).
- `python scripts/check_notes_tree.py` — note move from `proposed/seam/` to `implemented/seam/` introduces zero new findings (existing 18 findings are all pre-existing in unrelated notes).

## Consequences

- Production yaml's `emit_on_exit: [terminal.commit]` (now in `bundles/outer/phase_main.yaml`), `emit_on_exit: [phase.perceive.fold]` (`perceive_subgraph.yaml`), and `emit_on_exit: [think.gate.end]` (`think_subgraph.yaml`) fire at runtime when their nodes execute.
- The 10 new `_EP_DISPATCH` entries are the canonical mapping; future yaml declarations of these EPs land in the spine trace without further driver changes.
- Imperative `publish_ep_bound` calls in `tool_journal.py`, `safe_executor.py`, and `action_handlers.py` keep their richer payloads (decision_id, tool_name, error class); they remain the right path for control-plane observations that need typed-boundary arguments. Belt-and-braces with the dispatcher may cause double-counting on the spine trace for EPs that act executor also publishes imperatively — review once production runs surface the duplicate.
- The validator's two-path probe also exercises legacy hand-built plans that declare the field at top level. Both shapes now reach the check.

## Alternatives considered

### Wire the dispatcher without fixing the validator path

The dispatcher fires and debug tools start seeing new EPs; the validator stays broken and continues to never flag a missing `emit_on_exit`. Rejected because the validator is the only mechanism that prevents future yaml edits from silently dropping observability anchors — fixing the wiring without the validator leaves the same dead-config failure mode the field currently exhibits.

### Fix the validator path only, do not wire the dispatcher

The validator starts catching missing entries but nothing fires. Rejected because the field's value is then purely a static annotation with no runtime behavior; yaml authors and reviewers lose the direct mental model between "declared EP" and "spine event". The dispatcher table exists for a reason and is already partially wired (10 entries map to working helpers); leaving it unwired is permanent debt.

### Replace imperative `publish_ep_bound` calls with a single dispatcher-driven path

Cleaner long-term architecture, but the imperative calls live in `tool_journal.py`, `safe_executor.py`, and `action_handlers.py` — each with its own payload (decision_id, tool_name, error class). Folding them into the dispatcher loses payload richness and requires a parallel kwargs schema in `_EP_DISPATCH`. Out of scope for this Note; deferred to a separate seam proposal once the dispatcher-driven path is exercised in production.

### Move the EP table out of `node_emitter.py` into `meta_event_taxonomy.py`

The whitelist and the dispatch table are two views of the same closed set. Today they are not co-located — drift risk. Rejected because the meta taxonomy file currently exposes only `Final[tuple[str, ...]]` constants; making it the dispatch source requires a `dict[str, Callable]` constant pattern that is a wider refactor than the wiring itself. Track as a separate ADR if the seam stays.

## Out of scope

- Closed-set EP additions are recorded in [ADR-0240](../../../../adr/0240-node-emit-dispatch-whitelist-additions.md).
- Imperative `publish_ep_bound` calls in `cognitive_emit.py`, `tool_journal.py`, `safe_executor.py`, `action_handlers.py`. Their payloads (decision_id, tool_name, error class) are richer than the dispatcher's kwargs; folding them in is a separate seam proposal.
- `NodeEventEmissionCheck` re-enable in `DEFAULT_CHECKS`. Deferred to a follow-up PR after production runs accumulate kernel-cutover data.
- `NodeEventEmissionCheck` style and naming checks (`NodeIdNamingCheck`, `PortNamingConventionCheck`, `PlanIdAliasSuffixCheck`) — currently disabled in `DEFAULT_CHECKS` for production profiles; re-enable order is a separate runbook decision.