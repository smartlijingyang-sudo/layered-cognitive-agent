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

The default terminator reads the schema-declared ``decision`` and
``act_outcome`` port inputs (with a ``"decision"`` / ``"act_outcome"``
fallback when the schema is empty) and emits a :class:`StopPayload`
on the schema-declared ``terminal_outcome`` output port (with the
same fallback). The outer driver maps the payload to a
:class:`StopDecision` and runs ``apply_stop`` then
``apply_terminal_outcome``. This strategy emits nothing itself: the
driver dispatches the node's declared ``emit_on_exit`` list, which is
how the outer plan's ``terminal.commit`` node produces
``spine.terminal.commit``.

Post-retirement (plan ``docs/plans/2026-09-14-stop-decision-retirement.md``):
the previous ``should_stop`` boolean and ``focus_converged`` flag are
gone. Termination is the terminal outcome itself, decided by the data
shape (``reason`` and ``final_output_ref`` presence), not by a separate
predicate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.models.cognition.boundary import StopPayload
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.framework.graph.strategy_registry import register_strategy

TerminateFn = Callable[[dict[str, Any], StrategyContext], dict[str, Any]]

# Fallback port names used only when the strategy's schema is empty
# (legacy / undeclared wiring). Hosts that declare an ``io_schema`` get
# the schema's own names; the framework does not encode cognition-layer
# port names.
_DEFAULT_DECISION_PORT: str = "decision"
_DEFAULT_ACT_OUTCOME_PORT: str = "act_outcome"
_DEFAULT_TERMINAL_OUTCOME_PORT: str = "terminal_outcome"


def _resolve_terminate_ports(schema: NodeIOSchema) -> tuple[str, str, str]:
    """Resolve ``(decision_in, act_outcome_in, terminal_outcome_out)``.

    Uses the schema's first two required inputs and first output when
    declared; falls back to the legacy default names otherwise.
    """
    required = schema.required_inputs()
    decision_port = required[0] if len(required) >= 1 else _DEFAULT_DECISION_PORT
    act_outcome_port = required[1] if len(required) >= 2 else _DEFAULT_ACT_OUTCOME_PORT
    terminal_port = schema.outputs[0].name if schema.outputs else _DEFAULT_TERMINAL_OUTCOME_PORT
    return decision_port, act_outcome_port, terminal_port


@dataclass(frozen=True, slots=True)
class TerminateStrategy(NodeStrategy):
    kind: BindingKind = BindingKind.TERMINATE
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)
    terminate: TerminateFn | None = None

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        if self.terminate is None:
            return NodeOutput(
                port_values=_default_terminate(self.schema, dict(input.port_values), context),
                producer_node=context.node_id,
            )
        return NodeOutput(
            port_values=self.terminate(dict(input.port_values), context),
            producer_node=context.node_id,
        )


def _default_terminate(
    schema: NodeIOSchema,
    port_values: dict[str, Any],
    context: StrategyContext,
) -> dict[str, Any]:
    """Build a :class:`StopPayload` from the schema-declared port inputs.

    Reads the ``decision`` and ``act_outcome`` ports (resolved from
    ``schema`` with a legacy fallback) and emits a :class:`StopPayload`
    on the schema-declared terminal output port. If the decision has
    a RESPOND-shaped ``response_text``, the terminator records the
    answer as ``final_output_ref``. If the act_outcome carries a typed
    failure, the terminator records ``reason="error"`` and the
    failure's error message. Otherwise the terminator falls back to
    ``reason="continue"``.
    """
    decision_port, act_outcome_port, terminal_port = _resolve_terminate_ports(schema)
    decision = port_values.get(decision_port)
    act_outcome = port_values.get(act_outcome_port)

    final_output_ref: str | None = None
    reason_value: str | None = "continue"

    response_text = getattr(decision, "response_text", None) if decision is not None else None
    if isinstance(response_text, str) and response_text.strip():
        final_output_ref = response_text
        reason_value = None

    if act_outcome is not None:
        success = getattr(act_outcome, "success", None)
        if success is False:
            error_message = getattr(act_outcome, "error", None) or ""
            if error_message.strip():
                final_output_ref = None
                reason_value = "error"

    payload = StopPayload(
        reason=reason_value,
        final_output_ref=final_output_ref,
    )
    return {terminal_port: payload}


register_strategy(TerminateStrategy())


__all__ = ["TerminateFn", "TerminateStrategy"]
