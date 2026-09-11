"""GateChainStrategy — runs a sequence of :class:`DecisionGate` instances.

The strategy consumes a list of gates (host-injected via
``config["gates"]``) and runs them sequentially on the current
``decision`` payload, threading the result through. Each gate may
rewrite the decision; the chain ends with the final decision emitted
on the ``decision`` port.

The strategy does NOT introduce a new gate protocol. It reuses the
existing :class:`lca.contracts.protocols.think.cognition.DecisionGate`
Protocol (the same one the existing pipeline calls). This keeps
``GateChainStrategy`` and the existing brain gate pipeline on a single
concept, and prevents drift between graph-level and pipeline-level
gate implementations.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy


class _DecisionLike(Protocol):
    """Structural shape the framework requires for 'decision' payloads.

    The framework never imports the cognition :class:`Decision` type.
    Cognition implements this protocol structurally; the framework
    enforces the shape at runtime via :func:`_looks_like_decision`.
    """

    decision_id: str


def _looks_like_decision(payload: Any) -> bool:
    """Structural check; the framework does not pin the cognition type."""
    return hasattr(payload, "decision_id")


@dataclass(frozen=True, slots=True)
class GateChainStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.GATE_CHAIN
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    gates: Sequence[Any] = ()

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        decision_payload = input.port_values.get("decision")
        if not _looks_like_decision(decision_payload):
            raise RuntimeError(
                f"GateChainStrategy at {context.node_id!r}: "
                f"port 'decision' must be a decision-like object, "
                f"got {type(decision_payload).__name__}"
            )
        current = decision_payload
        for gate in self.gates:
            current = await gate.enforce(current)
        return NodeOutput(
            port_values={"decision": current},
            producer_node=context.node_id,
        )


def _empty_chain() -> Sequence[DecisionGate]:
    return ()


register_strategy(GateChainStrategy(gates=_empty_chain()))


__all__ = ["GateChainStrategy"]