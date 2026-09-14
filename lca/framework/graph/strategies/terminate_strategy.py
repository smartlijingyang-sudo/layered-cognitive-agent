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

The default terminator reads ``decision`` and ``act_outcome`` from the
port inputs. It builds a :class:`StopPayload` and emits it on the
``terminal_outcome`` output port. The outer driver maps the payload to
a :class:`StopDecision` and runs ``apply_stop`` then
``apply_terminal_outcome``. The driver also emits ``SPINE_TERMINAL_COMMIT``
to the spine.

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
    """Build a :class:`StopPayload` from the port inputs.

    Read ``decision`` (the model's last emission) and ``act_outcome``
    (the latest tool observation). If the decision has RESPOND with
    non-empty ``response_text``, the terminator records the answer as
    ``final_output_ref``. If the act_outcome carries a typed failure,
    the terminator records ``reason="error"`` and a journal pointer
    to the failure. Otherwise the terminator falls back to the legacy
    TASK_COMPLETED-shaped default of `final_output` from the decision's
    ``response_text`` and ``reason="continue"``.
    """
    decision = port_values.get("decision")
    act_outcome = port_values.get("act_outcome")

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
    return {"terminal_outcome": payload}


register_strategy(TerminateStrategy(terminate=_default_terminate))


__all__ = ["TerminateFn", "TerminateStrategy"]
