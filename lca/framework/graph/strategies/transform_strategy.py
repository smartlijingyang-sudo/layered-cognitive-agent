"""TransformStrategy — pure port→port projection.

The simplest strategy: takes ``port_values`` from the upstream
node(s), runs a host-injected pure function over them, and emits the
result on a declared output port. No state, no I/O, no clock.

Use cases:

- Shape coercion (Decision -> envelope).
- Aggregation in fan-in nodes.
- Cheap reducers (port_values -> single typed payload).
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

Transform = Callable[[dict[str, Any], StrategyContext], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TransformStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.TRANSFORM
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    transform: Transform | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.transform is None:
            raise RuntimeError(
                "TransformStrategy.execute called without transform"
            )
        produced = self.transform(dict(input.port_values), context)
        return NodeOutput(port_values=produced, producer_node=context.node_id)


def identity_transform(
    port_values: dict[str, Any], context: StrategyContext
) -> dict[str, Any]:
    """Default transform — pass inputs through to outputs unchanged."""
    return dict(port_values)


register_strategy(TransformStrategy(transform=identity_transform))


__all__ = ["TransformStrategy", "Transform", "identity_transform"]