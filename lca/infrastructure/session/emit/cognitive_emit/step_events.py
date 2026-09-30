"""Node-level phase step/fold spine EPs (ADR-0240).

These helpers back the ``_EP_DISPATCH`` entries that the graph driver
(:class:`lca.framework.graph.interpreter.PlanInterpreter`) fires from
``emit_on_enter`` / ``emit_on_exit`` declarations on BundleGraphSpec
v2 nodes. Payload is intentionally minimal (``state_id``); richer
fields (decision_id, tool_name, error class) stay with the imperative
``publish_ep_bound`` call sites in tool_journal / safe_executor /
action_handlers — see Note `2026-09-15-node-emit-dispatcher-wiring` §Out
of scope.
"""

from __future__ import annotations

from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    AppendReceipt,
    publish_ep_bound,
)


def emit_terminal_commit_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "kernel",
) -> AppendReceipt | None:
    """Append one ``terminal.commit`` spine fact."""
    return publish_ep_bound(
        "terminal.commit",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_perceive_fold_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "perceive",
) -> AppendReceipt | None:
    """Append one ``phase.perceive.fold`` spine fact."""
    return publish_ep_bound(
        "phase.perceive.fold",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_think_fold_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "think",
) -> AppendReceipt | None:
    """Append one ``phase.think.fold`` spine fact."""
    return publish_ep_bound(
        "phase.think.fold",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_reflect_fold_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "reflect",
) -> AppendReceipt | None:
    """Append one ``phase.reflect.fold`` spine fact."""
    return publish_ep_bound(
        "phase.reflect.fold",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_remember_fold_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "remember",
) -> AppendReceipt | None:
    """Append one ``phase.remember.fold`` spine fact."""
    return publish_ep_bound(
        "phase.remember.fold",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_stop_fold_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "stop",
) -> AppendReceipt | None:
    """Append one ``phase.stop.fold`` spine fact."""
    return publish_ep_bound(
        "phase.stop.fold",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_graph_subgraph_enter_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "graph",
) -> AppendReceipt | None:
    """Append one ``phase_graph.subgraph.enter`` spine fact."""
    return publish_ep_bound(
        "phase_graph.subgraph.enter",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


def emit_phase_graph_subgraph_exit_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "graph",
) -> AppendReceipt | None:
    """Append one ``phase_graph.subgraph.exit`` spine fact."""
    return publish_ep_bound(
        "phase_graph.subgraph.exit",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )


__all__ = [
    "emit_phase_graph_subgraph_enter_for_state",
    "emit_phase_graph_subgraph_exit_for_state",
    "emit_phase_perceive_fold_for_state",
    "emit_phase_reflect_fold_for_state",
    "emit_phase_remember_fold_for_state",
    "emit_phase_stop_fold_for_state",
    "emit_phase_think_fold_for_state",
    "emit_terminal_commit_for_state",
]
