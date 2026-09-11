"""TerminateStrategy — plan terminator with reason.

The strategy consumes the current node's inputs and emits a terminal
:class:`VisitRecord` with ``dispatch.kind == "terminal"``. The kernel
honors this and stops the loop. The strategy also writes the host's
typed ``reason`` into the recorder via ``StrategyContext`` if the host
attached one.

Use cases:

- Stop after a successful Decision is committed.
- Hard-fail after a typed error condition.
- Soft-stop on budget exhaustion (paired with budget policy).
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

TerminateFn = Callable[[dict[str, Any], StrategyContext], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TerminateStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.TERMINATE
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    terminate: TerminateFn | None = None

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        if self.terminate is None:
            raise RuntimeError(
                "TerminateStrategy.execute called without terminate fn"
            )
        return NodeOutput(
            port_values=self.terminate(dict(input.port_values), context),
            producer_node=context.node_id,
        )


def _default_terminate(
    port_values: dict[str, Any], context: StrategyContext
) -> dict[str, Any]:
    """Default: pass through, let the kernel mark the visit terminal."""
    return dict(port_values)


register_strategy(TerminateStrategy(terminate=_default_terminate))


__all__ = ["TerminateStrategy", "TerminateFn"]