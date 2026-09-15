"""GateChainStrategy — runs a sequence of :class:`DecisionGate` instances.

The strategy consumes a list of gates (host-injected via
``config["gates"]``) and runs them sequentially on the current
decision payload, threading the result through. Each gate may
rewrite the decision; the chain ends with the final decision emitted
on the schema-declared output port.

Port names are read from ``self.schema`` (set when the host registers
the strategy): the first required input declares where the decision
payload comes in, and the first output declares where the chain
result goes out. When the schema is empty (legacy / undeclared
wiring), the strategy falls back to ``"decision"`` so older plans
keep working without amendment.

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

# Fallback port names used only when ``self.schema`` is empty
# (legacy / undeclared). Hosts that declare an ``io_schema`` get the
# schema's own names; the framework does not encode cognition-layer
# port names.
_DEFAULT_DECISION_PORT: str = "decision"


class _DecisionLike(Protocol):
    """Structural shape the framework requires for decision payloads.

    The framework never imports the cognition :class:`Decision` type.
    Cognition implements this protocol structurally; the framework
    enforces the shape at runtime via :func:`_looks_like_decision`.
    """

    decision_id: str


def _looks_like_decision(payload: Any) -> bool:
    """Structural check; the framework does not pin the cognition type."""
    return hasattr(payload, "decision_id")


def _input_port_name(schema: NodeIOSchema) -> str:
    required = schema.required_inputs()
    return required[0] if required else _DEFAULT_DECISION_PORT


def _output_port_name(schema: NodeIOSchema) -> str:
    if schema.outputs:
        return schema.outputs[0].name
    return _DEFAULT_DECISION_PORT


@dataclass(frozen=True, slots=True)
class GateChainStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.GATE_CHAIN
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    gates: Sequence[Any] = ()

    async def execute(
        self, context: StrategyContext, input: NodeInput
    ) -> NodeOutput:
        in_port = _input_port_name(self.schema)
        out_port = _output_port_name(self.schema)
        decision_payload = input.port_values.get(in_port)
        if not _looks_like_decision(decision_payload):
            raise RuntimeError(
                f"GateChainStrategy at {context.node_id!r}: "
                f"port {in_port!r} must be a decision-like object, "
                f"got {type(decision_payload).__name__}"
            )
        current = decision_payload
        for gate in self.gates:
            current = await gate.enforce(current)
        return NodeOutput(
            port_values={out_port: current},
            producer_node=context.node_id,
        )


def _empty_chain() -> Sequence[Any]:
    """Gates are host-injected ``DecisionGate`` implementations.

    Typed ``Any`` rather than the Protocol: importing
    ``lca.contracts.protocols.think.cognition`` would pull cognition DTOs
    across the framework boundary that
    ``scripts/check_framework_cognition_boundary.py`` guards.
    """
    return ()


register_strategy(GateChainStrategy(gates=_empty_chain()))


__all__ = ["GateChainStrategy"]
