"""PlanInterpreter - single visit state machine for one :class:`Plan`.

The kernel owns the visit loop:

```
while not traversal.terminated():
    node = plan.node(traversal.current_id)
    traversal.visit(node_id=node.id)
    strategy = registry.resolve(node.binding)
    input = port_registry.build_input(schema.required_inputs())
    output = await strategy.execute(strategy_context, input)
    port_registry.merge_output(output.port_values)

    if node.io_schema.terminal_predicate:
        reader = PortReader(source_node=node.id, registry=port_registry)
        if evaluate_predicate(node.io_schema.terminal_predicate, reader=reader):
            traversal.terminal = True
            break

    edge = select_edge(plan.edges, current_id, reader_factory=...)
    traversal.advance(edge=edge, dispatch_kind=...)
```

The kernel does not implement binding-specific logic. Each strategy
owns its own execute path. The kernel's job is:

1. Track visits (resume checkpoints replay them; no per-node cap).
2. Build :class:`NodeInput` from the port registry using the
   strategy's declared schema.
3. Dispatch to the resolved strategy.
4. Merge the output, advance, terminate.

D4 cutover: the legacy ``_ResultView`` and ``_result_discriminator``
have been deleted. Cross-node reads go through :class:`PortReader`
(typed port resolver). ``select_edge`` takes a reader factory and
evaluates structured :class:`Predicate` objects.

Observability
-------------
The kernel emits one :class:`GraphObservation` per lifecycle event
(visit start / visit end / edge / subgraph enter / subgraph exit)
through the configured :class:`GraphObserver`. The kernel does
not know EP names; :class:`GraphEpTable` is the only place that
maps observation kinds to execution points.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.node_io import NodeOutput
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.contracts.protocols.graph.visit import DispatchDecision, VisitRecord
from lca.framework.graph.observation import (
    KIND_EDGE,
    KIND_VISIT_END,
    KIND_VISIT_START,
    GraphObservation,
    GraphObserver,
    NullGraphObserver,
    inputs_of,
    metadata_of,
    phase_of,
)
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.predicate_evaluator import evaluate_predicate
from lca.framework.graph.recorder import VisitRecorder
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.framework.graph.traversal import PlanTraversal, select_edge

Clock = Callable[[], int]
"""Monotonic millisecond clock. Default is ``time.monotonic_ns // 1_000_000``."""


def _port_registry_seed_from_runtime_plane() -> dict[str, Any]:
    """Read kernel-owned typed ports from the typed ``RuntimePlane``.

    The kernel owns two typed ports that flow through every outer plan:

    - ``tools`` — the per-turn ``ToolsService`` published by the carrier
      via ``set_current_tools_service``.
    - ``bindings`` — the per-turn ``BindingsView`` published by the
      carrier via ``set_capability_bindings``.

    Either may be absent; the kernel only seeds what is bound.  Both
    lookups are local and idempotent, safe to call at every outer plan
    entry.  This is the canonical production seam — the
    ``PlanInterpreterAdapter`` falls back to the same reader after
    checking ``node_executor_runtime_scope`` for backwards compat with
    tests that bind a Cordis-style scope directly.
    """
    seed: dict[str, Any] = {}
    try:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
            current_tools_service,
        )
    except Exception:
        return seed
    tools_service = current_tools_service()
    if tools_service is not None:
        seed["tools"] = tools_service
    bindings_view = current_bindings_view()
    if bindings_view is not None:
        seed["bindings"] = bindings_view
    return seed


def _default_clock() -> int:
    return time.monotonic_ns() // 1_000_000


@dataclass
class PlanInterpreter:
    """Single visit state machine. Stateless across runs."""

    registry: StrategyRegistry
    recorder: VisitRecorder = field(default_factory=VisitRecorder)
    artifacts: Mapping[str, object] = field(default_factory=dict)
    observer: GraphObserver = field(default_factory=NullGraphObserver)
    clock: Clock = field(default=_default_clock)
    # ADR-0219 §4 typed mirror: subgraph nodes that need to read prior
    # phase results get them through ``context.node_config["results_by_phase"]``
    # which is seeded from this field by the recursive runner. The
    # kernel carries it across subgraph boundaries so nested runs see
    # the same dict.
    results_by_phase: dict = field(default_factory=dict)

    async def run(
        self,
        plan: Plan,
        *,
        port_registry: PortRegistry | None = None,
        outer_state: Any = None,
        traversal: PlanTraversal | None = None,
        port_registry_seed: (
            Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None
        ) = None,
    ) -> InterpretationResult:
        """Execute ``plan`` and return the typed :class:`InterpretationResult`.

        ``port_registry_seed`` is the canonical seam by which the kernel
        publishes typed ports (``tools`` / ``bindings``) to every plan
        it interprets.  Mirrors :meth:`PlanInterpreterAdapter.run`:

        - ``Mapping`` → used directly (test injection).
        - ``Callable`` → invoked once at outer plan entry.
        - ``None`` → fall back to the production seam
          ``RuntimePlane.current_tools_service()`` +
          ``RuntimePlane.current_bindings_view()``.

        The seed runs **before** the visit loop; kernel-seeded ports
        are visible to every node that declares them.

        When ``traversal`` is provided, the kernel resumes from
        ``traversal.current_id`` instead of starting at the plan's
        declared entry node. Hosts use this path for checkpointed
        resume; the adapter exposes it via :class:`PhaseRunCursor`.
        """
        if traversal is None:
            traversal = PlanTraversal(plan=plan)
        ports = port_registry or PortRegistry()
        if port_registry_seed is None:
            seed = _port_registry_seed_from_runtime_plane()
        elif callable(port_registry_seed):
            seed = dict(port_registry_seed())
        else:
            seed = dict(port_registry_seed)
        if seed:
            ports.set_outer_input(seed)  # type: ignore[arg-type]
        visits: list[VisitRecord] = []
        facts: list = []
        terminal_node = traversal.current_id
        depth = _resolve_depth(outer_state)

        def _reader_factory(source_node: str) -> PortReader:
            return PortReader(source_node=source_node, registry=ports)

        while not traversal.terminated():
            node = plan.node(traversal.current_id)
            self.observer.observe(_visit_start_of(node, plan.id, traversal, depth, self.clock()))
            traversal.visit(node_id=node.id)
            # ADR-0225: per-node ``max_visits`` cap removed. The kernel
            # no longer flips ``terminal`` on a per-node visit ceiling —
            # termination is via ``Decision(action_type=respond)``,
            # ``should_terminate`` from act.observe, ``AgentState.budget``
            # (max_steps / max_wall_clock / max_tokens), or an explicit
            # ``terminal_predicate`` match below.
            strategy = self.registry.resolve(node.binding)
            schema = node.io_schema
            inputs = ports.build_input(schema.required_inputs(), consumer_node=node.id)
            # ADR-0219 §4 typed mirror of phase results: the runner closure
            # in adapter.py reads ``results_by_phase`` from node_config to
            # hand to ``_build_phase_context`` so phase executors can call
            # ``context.payload_of(phase, want)``. The same dict is mutated
            # by the strategy after each phase visit so subsequent phases
            # see prior phases' typed payloads (think → act → reflect →
            # remember → stop). Without this mirror, reflect/remember/stop
            # read None for prior phases and the stop policy never sees a
            # completed decision — the agent loops on stop → perceive.
            results_so_far = self.results_by_phase
            context = StrategyContext(
                plan_ref=plan.id,
                node_id=node.id,
                binding_kind=node.binding,
                node_config={
                    "agent_state": outer_state,
                    "results_by_phase": results_so_far,
                    # ADR-0241 §4: kernel exposes the outer plan's
                    # port registry to subgraph delegates via
                    # ``node_config`` so nested subgraph strategies can
                    # seed the inner ``PortRegistry`` with the full
                    # outer port set (kernel-seeded ``tools`` /
                    # ``bindings`` included). Subgraph strategies read
                    # this key — non-subgraph strategies ignore it.
                    "_port_registry": ports,
                    **dict(node.config),
                },
                subgraph_ref=node.subgraph_ref,
                chain=(),
                inner_io_schema=node.inner_io_schema,
            )
            visit_started = self.clock()
            try:
                output: NodeOutput = await strategy.execute(context, inputs)
            except BaseException as exc:
                self.observer.observe(
                    _visit_end_of(
                        node,
                        plan.id,
                        traversal.visit_counts.get(node.id, 1),
                        depth,
                        outcome="failure",
                        error=repr(exc),
                        elapsed_ms=self.clock() - visit_started,
                        inputs=dict(inputs.port_values),
                        outputs={},
                        occurred_at_ms=self.clock(),
                    )
                )
                raise
            ports.merge_output(
                output.port_values,
                payload_types={
                    spec.name: spec.payload_type
                    for spec in schema.outputs
                    if spec.payload_type is not None
                },
            )

            # D4: terminal_predicate evaluation before edge selection.
            if schema.terminal_predicate is not None:
                reader = _reader_factory(node.id)
                # Data-absence errors mean "not terminal yet" — the same
                # reading ``select_edge`` applies to edge predicates. A
                # malformed predicate (ValueError) is a plan defect and has
                # to surface instead of silently falling through to edges.
                with contextlib.suppress(UnsetPortError, UnknownFieldError):
                    if evaluate_predicate(schema.terminal_predicate, reader=reader):
                        traversal.terminal = True
                        traversal.terminal_reason = ("terminal_predicate", node.id, 0, 0)
                        self.observer.observe(
                            _visit_end_of(
                                node,
                                plan.id,
                                traversal.visit_counts.get(node.id, 1),
                                depth,
                                outcome="success",
                                error="",
                                elapsed_ms=self.clock() - visit_started,
                                inputs=inputs.port_values,
                                outputs=output.port_values,
                                dispatch="terminal",
                                occurred_at_ms=self.clock(),
                            )
                        )
                        visit = VisitRecord(
                            plan_ref=plan.id,
                            node_id=node.id,
                            binding_kind=node.binding,
                            inputs=dict(inputs.port_values),
                            outputs=dict(output.port_values),
                            dispatch=DispatchDecision(kind="terminal"),
                            error=None,
                        )
                        self.recorder.record(visit)
                        visits.append(visit)
                        facts.extend(output.port_values.get("facts", ()) or ())
                        terminal_node = node.id
                        break

            edge = select_edge(
                edges=plan.edges,
                current_id=node.id,
                reader_factory=_reader_factory,
            )
            dispatch = self._classify(edge, output)
            self.observer.observe(
                _visit_end_of(
                    node,
                    plan.id,
                    traversal.visit_counts.get(node.id, 1),
                    depth,
                    outcome="success",
                    error="",
                    elapsed_ms=self.clock() - visit_started,
                    inputs=inputs.port_values,
                    outputs=output.port_values,
                    dispatch=dispatch.kind,
                    occurred_at_ms=self.clock(),
                )
            )
            if edge is not None:
                self.observer.observe(_edge_of(plan.id, node.id, edge, depth, self.clock()))
            visit = VisitRecord(
                plan_ref=plan.id,
                node_id=node.id,
                binding_kind=node.binding,
                inputs=dict(inputs.port_values),
                outputs=dict(output.port_values),
                dispatch=dispatch,
                error=None,
            )
            self.recorder.record(visit)
            visits.append(visit)
            facts.extend(output.port_values.get("facts", ()) or ())
            terminal_node = node.id
            traversal.advance(edge=edge, dispatch_kind=dispatch.kind)
        return InterpretationResult(
            plan=plan,
            terminal_node=terminal_node,
            visits=tuple(visits),
            facts=tuple(facts),
            output=_terminal_port_values(ports, plan),
        )

    @staticmethod
    def _classify(edge: object | None, output: NodeOutput) -> DispatchDecision:
        if edge is None:
            return DispatchDecision(kind="terminal")
        return DispatchDecision(kind="next", next_node=getattr(edge, "target", None))


@dataclass
class InterpretationResult:
    """The typed return value of :meth:`PlanInterpreter.run`.

    ADR-0221 P3: ``state`` / ``outcome`` / ``cursor`` are not yet
    produced by the v2 interpreter — they live on the v0
    ``_LegacyResultShim``. Callers that need them must derive them from
    ``output`` and the ``AgentState`` they passed in. The kernel
    driver wraps the result with the appropriate shim at the
    composition boundary; this dataclass stays narrow.
    """

    plan: Plan
    terminal_node: str
    visits: tuple[VisitRecord, ...]
    facts: tuple[Any, ...]
    output: dict[str, Any] = field(default_factory=dict)


def _terminal_port_values(ports: PortRegistry, plan: Plan) -> dict[str, Any]:
    """Project the terminal port set onto the plan's declared outputs.

    Falls back to the full snapshot when the plan declares no outputs.
    """
    if not plan.declared_inputs:
        return dict(ports.snapshot())
    return ports.exit_subgraph(plan.declared_inputs)


def _resolve_depth(outer_state: Any) -> int:
    """Read ``graph_depth`` off an AgentState-shaped outer state, default 1."""
    depth = getattr(outer_state, "graph_depth", None)
    if isinstance(depth, int) and depth > 0:
        return depth
    return 1


def _visit_start_of(
    node: PlanNode,
    plan_ref: str,
    traversal: PlanTraversal,
    depth: int,
    occurred_at_ms: int,
) -> GraphObservation:
    node_index = traversal.visit_counts.get(node.id, 0) + 1
    return GraphObservation(
        kind=KIND_VISIT_START,
        plan_ref=plan_ref,
        occurred_at_ms=occurred_at_ms,
        node_id=node.id,
        node_index=node_index,
        depth=depth,
        binding=node.binding.value,
        phase=phase_of(node.id),
        metadata=metadata_of(
            binding=node.binding,
            purpose=str(node.config.get("purpose", "")),
            region=str(node.config.get("region", "")),
            subgraph_plan_ref=(node.subgraph_ref.plan_ref if node.subgraph_ref else ""),
        ),
    )


def _visit_end_of(
    node: PlanNode,
    plan_ref: str,
    node_index: int,
    depth: int,
    *,
    outcome: str,
    error: str,
    elapsed_ms: int,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    dispatch: str = "",
    occurred_at_ms: int = 0,
) -> GraphObservation:
    return GraphObservation(
        kind=KIND_VISIT_END,
        plan_ref=plan_ref,
        occurred_at_ms=occurred_at_ms,
        node_id=node.id,
        node_index=node_index,
        depth=depth,
        binding=node.binding.value,
        dispatch=dispatch,
        outcome=outcome,
        error=error,
        elapsed_ms=elapsed_ms,
        inputs=inputs_of(inputs),
        outputs=inputs_of(outputs),
        metadata=metadata_of(
            binding=node.binding,
            purpose=str(node.config.get("purpose", "")),
            region=str(node.config.get("region", "")),
            subgraph_plan_ref=(node.subgraph_ref.plan_ref if node.subgraph_ref else ""),
        ),
    )


def _edge_of(
    plan_ref: str,
    from_node: str,
    edge: PlanEdge,
    depth: int,
    occurred_at_ms: int,
) -> GraphObservation:
    edge_id = f"{from_node}->{edge.target}"
    return GraphObservation(
        kind=KIND_EDGE,
        plan_ref=plan_ref,
        occurred_at_ms=occurred_at_ms,
        depth=depth,
        edge_id=edge_id,
        from_node=from_node,
        to_node=edge.target,
        metadata=(("when", str(edge.when)),),
    )


__all__ = [
    "Clock",
    "InterpretationResult",
    "PlanInterpreter",
    "_default_clock",
    "_edge_of",
    "_visit_end_of",
    "_visit_start_of",
]
