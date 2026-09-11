"""SubgraphStrategy — recursive entry into another :class:`Plan`.

A :class:`lca.contracts.protocols.graph.plan.SubgraphReference` on a node
points to another plan. The strategy delegates to a caller-provided
``sub_runner`` that takes ``(ref, outer_input, outer_state)`` and
returns ``(updated_state, merged_output)``. The default ``sub_runner``
is :class:`lca.framework.subgraph.plugins.runner.SubgraphRunner` (kept
in PR-7 until deletion). PR-4 replaces this with a kernel-internal
recursive :meth:`PlanInterpreter.run`.

The strategy enforces the recursion budget (default 4, per
``MAX_SUBGRAPH_DEPTH`` in :mod:`lca.framework.subgraph.plugins.interpreter`)
via the host-provided ``depth`` callable so the bound is the same
regardless of which interpreter is on top.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference as LegacySubgraphReference,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import SubgraphReference
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy

SubRunner = Callable[
    [LegacySubgraphReference, dict[str, Any], AgentState, int],
    tuple[AgentState, dict[str, Any]],
]


@dataclass(frozen=True, slots=True)
class SubgraphStrategy(NodeStrategy):
    """Recursive :class:`Plan` invocation.

    ``sub_runner`` is host-injected. ``depth_counter`` returns the next
    depth (current + 1) so the host enforces the recursion bound.
    """

    kind: BindingKind = BindingKind.SUBGRAPH
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    sub_runner: SubRunner | None = None
    max_depth: int = 4
    depth_counter: Callable[[], int] | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.sub_runner is None:
            raise RuntimeError(
                "SubgraphStrategy.execute called without sub_runner; "
                "the host must inject one (typically SubgraphRunner.run)"
            )
        ref = context.subgraph_ref
        if ref is None:
            raise RuntimeError(
                f"node {context.node_id!r} has binding=SUBGRAPH but no subgraph_ref"
            )
        outer_state = context.node_config.get("agent_state")
        if not isinstance(outer_state, AgentState):
            outer_state = AgentState(trace_id="", task="", budget=_empty_budget())
        depth = 1
        if self.depth_counter is not None:
            depth = self.depth_counter() + 1
        if depth > self.max_depth:
            raise RuntimeError(
                f"subgraph recursion exceeded max_depth={self.max_depth} at "
                f"plan_ref={context.plan_ref!r} node_id={context.node_id!r}"
            )
        updated_state, merged_output = self.sub_runner(
            ref, dict(input.port_values), outer_state, depth
        )
        return NodeOutput(
            port_values=merged_output,
            producer_node=context.node_id,
        )


register_strategy(SubgraphStrategy())


def _empty_budget() -> Budget:
    return Budget()


__all__ = ["SubgraphStrategy", "SubRunner"]