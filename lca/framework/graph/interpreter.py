"""PlanInterpreter — single visit state machine for one :class:`Plan`.

The kernel owns the visit loop:

```
while not traversal.terminated():
    node = plan.node(traversal.current_id)
    traversal.visit(node_id=node.id, max_visits=node.max_visits)
    strategy = registry.resolve(node.binding)
    input = port_registry.build_input(schema.required_inputs())
    output = await strategy.execute(strategy_context, input)
    port_registry.merge_output(output.port_values)
    recorder.record(VisitRecord(...))
    edge = select_edge(plan.edges, current_id, output, artifacts)
    traversal.advance(edge=edge, dispatch_kind=...)
```

The kernel does not implement binding-specific logic. Each strategy
owns its own execute path. The kernel's job is:

1. Track visits and enforce ``max_visits``.
2. Build :class:`NodeInput` from the port registry using the
   strategy's declared schema.
3. Dispatch to the resolved strategy.
4. Merge the output, advance, terminate.

Replaces the visit loops in the legacy interpreter classes deleted
in the act-subgraph seam cutover (note 2026-09-11).

Existing fixtures can opt in by calling
:meth:`PlanInterpreter.run` instead of the legacy ``run`` /
``_drive`` entry points. PR-7 deletes the legacy entry points.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.node_io import NodeOutput
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.contracts.protocols.graph.visit import DispatchDecision, VisitRecord
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.recorder import VisitRecorder
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.framework.graph.traversal import PlanTraversal, select_edge


@dataclass
class PlanInterpreter:
    """Single visit state machine. Stateless across runs."""

    registry: StrategyRegistry
    recorder: VisitRecorder = field(default_factory=VisitRecorder)
    artifacts: Mapping[str, object] = field(default_factory=dict)

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
        while not traversal.terminated():
            node = plan.node(traversal.current_id)
            traversal.visit(node_id=node.id, max_visits=node.max_visits)
            strategy = self.registry.resolve(node.binding)
            schema = node.io_schema
            inputs = ports.build_input(
                schema.required_inputs(), consumer_node=node.id
            )
            context = StrategyContext(
                plan_ref=plan.id,
                node_id=node.id,
                binding_kind=node.binding,
                node_config={"agent_state": outer_state, **dict(node.config)},
                subgraph_ref=node.subgraph_ref,
                chain=(),
            )
            output: NodeOutput = await strategy.execute(context, inputs)
            ports.merge_output(output.port_values)
            edge = select_edge(
                edges=plan.edges,
                current_id=node.id,
                result=output,
                artifacts=self.artifacts,
            )
            dispatch = self._classify(edge, output)
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


def _terminal_port_values(
    ports: PortRegistry, plan: Plan
) -> dict[str, Any]:
    """Project the terminal port set onto the plan's declared outputs.

    Falls back to the full snapshot when the plan declares no outputs.
    """
    if not plan.declared_inputs:
        return dict(ports.snapshot())
    return ports.exit_subgraph(plan.declared_inputs)


__all__ = ["InterpretationResult", "PlanInterpreter"]
