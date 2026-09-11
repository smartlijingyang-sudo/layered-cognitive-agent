"""PlanInterpreter - single visit state machine for one :class:`Plan`.

The kernel owns the visit loop:

```
while not traversal.terminated():
    node = plan.node(traversal.current_id)
    traversal.visit(node_id=node.id, max_visits=node.max_visits)
    strategy = registry.resolve(node.binding)
10→    input = port_registry.build_input(schema.required_inputs())
    output = await strategy.execute(strategy_context, input)
    port_registry.merge_output(output.port_values)
    recorder.record(VisitRecord(...))
    edge = select_edge(plan.edges, current_id, output, artifacts)
    traversal.advance(edge=edge, dispatch_kind=...)
```

The kernel does not implement binding-specific logic. Each strategy
owns its own execute path. The kernel's job is:
20→
1. Track visits and enforce ``max_visits``.
2. Build :class:`NodeInput` from the port registry using the
   strategy's declared schema.
3. Dispatch to the resolved strategy.
4. Merge the output, advance, terminate.

Replaces the visit loops in the legacy interpreter classes deleted
in the act-subgraph seam cutover (note 2026-09-11).

30→Existing fixtures can opt in by calling
:meth:`PlanInterpreter.run` instead of the legacy ``run`` /
``_drive`` entry points. PR-7 deletes the legacy entry points.

Observability
-------------
The kernel emits one :class:`GraphObservation` per lifecycle event
(visit start / visit end / edge / subgraph enter / subgraph exit)
through the configured :class:`GraphObserver`. The kernel does
not know EP names; :class:`GraphEpTable` is the only place that
maps observation kinds to execution points.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

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
)
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.recorder import VisitRecorder
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.framework.graph.traversal import PlanTraversal, select_edge

Clock = Callable[[], int]
"""Monotonic millisecond clock. Default is ``time.monotonic_ns // 1_000_000``."""


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

    async def run(
        self,
        plan: Plan,
        *,
        port_registry: PortRegistry | None = None,
        outer_state: Any = None,
        traversal: PlanTraversal | None = None,
    ) -> InterpretationResult:
        """Execute ``plan`` and return the typed :class:`InterpretationResult`.

        When ``traversal`` is provided, the kernel resumes from
        ``traversal.current_id`` instead of starting at the plan's
        declared entry node. Hosts use this path for checkpointed
        resume; the adapter exposes it via :class:`PhaseRunCursor`.
        """
        if traversal is None:
            traversal = PlanTraversal(plan=plan)
        ports = port_registry or PortRegistry()
        visits: list[VisitRecord] = []
        facts: list = []
        terminal_node = traversal.current_id
        depth = _resolve_depth(outer_state)
        while not traversal.terminated():
            node = plan.node(traversal.current_id)
            self.observer.observe(_visit_start_of(node, plan.id, traversal, depth, self.clock()))
            traversal.visit(node_id=node.id, max_visits=node.max_visits)
            strategy = self.registry.resolve(node.binding)
            schema = node.io_schema
            inputs = ports.build_input(schema.required_inputs(), consumer_node=node.id)
            context = StrategyContext(
                plan_ref=plan.id,
                node_id=node.id,
                binding_kind=node.binding,
                node_config={"agent_state": outer_state, **dict(node.config)},
                subgraph_ref=node.subgraph_ref,
                chain=(),
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
            ports.merge_output(output.port_values)
            edge = select_edge(
                edges=plan.edges,
                current_id=node.id,
                result=_result_discriminator(output),
                artifacts=self.artifacts,
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
                    inputs=dict(inputs.port_values),
                    outputs=dict(output.port_values),
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
    """The typed return value of :meth:`PlanInterpreter.run`."""

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


class _ResultView:
    """Duck-typed view of a ``PhaseResult`` for the edge DSL predicate.

    The legacy ``evaluate_restricted_predicate`` expects a result object
    with ``result_kind`` and ``next_hints``. The new kernel carries that
    data on :class:`NodeOutput`. ``_ResultView`` lets the interpreter
    pass the kernel's typed output into the legacy predicate without
    rebuilding a full ``PhaseResult``.
    """

    __slots__ = ("_output",)

    def __init__(self, output: NodeOutput) -> None:
        self._output = output

    @property
    def result_kind(self) -> str:
        return self._output.result_kind or ""

    @property
    def next_hints(self) -> Mapping[str, Any]:
        return self._output.next_hints or {}

    def __getattr__(self, name: str) -> Any:
        # Kernel ``NodeOutput`` does not carry every PhaseResult field
        # (``payload`` lives on the legacy result shape). Treat missing
        # attributes as ``None`` so legacy edge predicates like
        # ``result.payload == None`` resolve cleanly.
        try:
            return getattr(self._output, name)
        except AttributeError:
            return None


def _result_discriminator(output: NodeOutput) -> Any:
    """Return a value the legacy edge predicate can read ``.result_kind`` on.

    Always returns a :class:`_ResultView` so the predicate never
    escapes with an AttributeError on missing fields like ``payload``.
    The view's ``__getattr__`` returns ``None`` for fields the kernel
    ``NodeOutput`` doesn't carry (``payload`` lives on the legacy
    ``PhaseResult``, not on the kernel's typed output), which keeps
    predicates like ``result.payload == None`` working.
    """
    return _ResultView(output)


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
        metadata=metadata_of(
            binding=node.binding,
            purpose=str(node.config.get("purpose", "")),
            region=str(node.config.get("region", "")),
            max_visits=node.max_visits,
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
            max_visits=node.max_visits,
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
        metadata=(("when", edge.when),),
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
