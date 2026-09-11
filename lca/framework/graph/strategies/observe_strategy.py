"""ObserveStrategy — passive observation; never advances or terminates.

The strategy calls a host-injected ``observer`` closure with the
current node's inputs and outputs, then emits the same ports through
to the next node. The kernel records the visit as a regular
:class:`VisitRecord`; the observer is the seam for telemetry.

The strategy is intentionally side-effect free: observers must not
mutate state directly. Mutation goes through the existing journal /
reducer seam (planned PR-7 wiring).
"""
from __future__ import annotations

from collections.abc import Callable
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

Observer = Callable[[StrategyContext, dict[str, Any], dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class ObserveStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.OBSERVE
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    observer: Observer | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        port_values = dict(input.port_values)
        if self.observer is not None:
            try:
                self.observer(context, port_values, port_values)
            except Exception:
                pass
        return NodeOutput(port_values=port_values, producer_node=context.node_id)


def _noop_observer(
    context: StrategyContext,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> None:
    return None


register_strategy(ObserveStrategy(observer=_noop_observer))


__all__ = ["ObserveStrategy", "Observer"]