"""Act-subgraph tool-call spine EPs (ADR-0220 §3.3, ADR-0240).

The act subgraph emits these EPs through NodeGraphDriver's
``emit_on_enter`` / ``emit_on_exit`` config. Each helper below publishes
one SPINE_EXECUTION_POINTS entry via FactGateway so the observation
plane captures the act-phase lifecycle. ``state`` is the only required
arg because the driver dispatches with the outer-state handle; richer
payload (decision_id, tool_name, etc.) is intentionally left to dedicated
control-plane plugins that wire the typed Decision / EffectReceipt
boundary, not this helper.
"""

from __future__ import annotations

from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    AppendReceipt,
    publish_ep_bound,
)


def emit_phase_tool_call_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``phase.tool.call.start`` spine fact."""
    return publish_ep_bound(
        "phase.tool.call.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_tool_call_end_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``phase.tool.call.end`` spine fact.

    Pure lifecycle marker for the act-subgraph bracket: it carries no
    tool outcome (the authoritative outcome lives in
    ``step.tool_result.record``).
    """
    return publish_ep_bound(
        "phase.tool.call.end",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_think_gate_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``think.gate.start`` spine fact.

    The act-subgraph ``act.authorize`` node reuses the gate EP as its
    observation surface — it is the policy gate for tool dispatch.
    """
    return publish_ep_bound(
        "think.gate.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_think_gate_end_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "think",
) -> AppendReceipt | None:
    """Append one ``think.gate.end`` spine fact."""
    return publish_ep_bound(
        "think.gate.end",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_body_tool_execute_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``body.tool.execute.start`` spine fact."""
    return publish_ep_bound(
        "body.tool.execute.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_body_tool_execute_end_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``body.tool.execute.end`` spine fact.

    Pure lifecycle marker for the act-subgraph bracket: it carries no
    tool outcome (the authoritative outcome lives in
    ``step.tool_result.record``).
    """
    return publish_ep_bound(
        "body.tool.execute.end",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_act_fold_start_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``phase.act.fold.start`` spine fact."""
    return publish_ep_bound(
        "phase.act.fold.start",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_act_fold_end_for_state(
    state: AgentState,
    *,
    outcome: str = "success",
    session: object | None = None,
    actor: str = "act",
) -> AppendReceipt | None:
    """Append one ``phase.act.fold.end`` spine fact."""
    return publish_ep_bound(
        "phase.act.fold.end",
        {"state_id": state.trace_id, "outcome": outcome},
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_body_tool_execute_end_for_state",
    "emit_body_tool_execute_start_for_state",
    "emit_phase_act_fold_end_for_state",
    "emit_phase_act_fold_start_for_state",
    "emit_phase_tool_call_end_for_state",
    "emit_phase_tool_call_start_for_state",
    "emit_think_gate_end_for_state",
    "emit_think_gate_start_for_state",
]
