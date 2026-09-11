"""ParallelStrategy — fork-join across sibling plans.

The strategy fans out a single :class:`Plan` against each child
``plan_ref`` in ``config["children"]``, runs them sequentially (the
production engine may swap in an asyncio.gather in PR-7), and merges
the per-child outputs by host-supplied reducer.

This is the typed graph-level primitive for "do N things in parallel
then reduce". It deliberately does not know about agents (that's
:func:`AGENT_FANOUT` in PR-6).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy

ChildRunner = Callable[[str, dict[str, Any]], dict[str, Any]]
Reducer = Callable[[Iterable[dict[str, Any]]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ParallelStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.PARALLEL
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    child_runner: ChildRunner | None = None
    reducer: Reducer | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.child_runner is None or self.reducer is None:
            raise RuntimeError(
                "ParallelStrategy.execute called without child_runner or reducer"
            )
        children = context.node_config.get("children")
        if not isinstance(children, (list, tuple)) or len(children) == 0:
            raise RuntimeError(
                f"ParallelStrategy at {context.node_id!r}: "
                f"node_config['children'] must be a non-empty sequence of plan_refs"
            )
        per_child = [
            self.child_runner(str(ref), dict(input.port_values))
            for ref in children
        ]
        merged = self.reducer(per_child)
        return NodeOutput(port_values=merged, producer_node=context.node_id)


def _default_reducer(per_child_outputs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Last-write-wins reducer; deterministic given input order."""
    merged: dict[str, Any] = {}
    for output in per_child_outputs:
        for key, value in output.items():
            merged[key] = value
    return merged


def _stub_child_runner(plan_ref: str, port_values: dict[str, Any]) -> dict[str, Any]:
    """Default child runner; returns the input unchanged. Production
    code injects :class:`PlanInterpreter.run` here."""
    return dict(port_values)


register_strategy(
    ParallelStrategy(child_runner=_stub_child_runner, reducer=_default_reducer)
)


__all__ = [
    "ChildRunner",
    "ParallelStrategy",
    "Reducer",
    "_default_reducer",
    "_stub_child_runner",
]