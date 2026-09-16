"""Node-level EP dispatcher for BundleGraphSpec v2 (ADR-0217 §3.3.2).

Maps ``emit_on_enter`` / ``emit_on_exit`` config keys to existing
FactGateway emit functions. Executor plugins MUST NOT import this
module — the dispatch is driven by the node graph driver so that
node executors stay free of EP coupling.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit import (
    emit_body_tool_execute_end_for_state,
    emit_body_tool_execute_start_for_state,
    emit_phase_act_fold_end_for_state,
    emit_phase_act_fold_start_for_state,
    emit_phase_graph_subgraph_enter_for_state,
    emit_phase_graph_subgraph_exit_for_state,
    emit_phase_perceive_fold_for_state,
    emit_phase_reflect_fold_for_state,
    emit_phase_remember_fold_for_state,
    emit_phase_stop_fold_for_state,
    emit_phase_think_fold_for_state,
    emit_phase_tool_call_end_for_state,
    emit_phase_tool_call_start_for_state,
    emit_prompt_assembler_end_for_state,
    emit_prompt_assembler_start_for_state,
    emit_reasoner_reason_end_for_state,
    emit_reasoner_reason_start_for_state,
    emit_terminal_commit_for_state,
    emit_think_gate_end_for_state,
    emit_think_gate_start_for_state,
)

_EP_DISPATCH: dict[str, Any] = {
    # Legacy underscore-form aliases (private to this dispatcher — not in
    # EXECUTION_POINTS). Kept so think_reason.yaml's declared emit lists
    # continue to fire once the driver is wired.
    "prompt_assembler_start": emit_prompt_assembler_start_for_state,
    "prompt_assembler_end": emit_prompt_assembler_end_for_state,
    "reasoner_meta": None,
    "reasoner_reason_start": emit_reasoner_reason_start_for_state,
    "reasoner_reason_end": emit_reasoner_reason_end_for_state,
    # Dot-form EPs from EXECUTION_POINTS (ADR-0240 §Decision).
    "think.gate.start": emit_think_gate_start_for_state,
    "think.gate.end": emit_think_gate_end_for_state,
    "body.tool.execute.start": emit_body_tool_execute_start_for_state,
    "body.tool.execute.end": emit_body_tool_execute_end_for_state,
    "phase.tool.call.start": emit_phase_tool_call_start_for_state,
    "phase.tool.call.end": emit_phase_tool_call_end_for_state,
    "phase.act.fold.end": emit_phase_act_fold_end_for_state,
    "phase.act.fold.start": emit_phase_act_fold_start_for_state,
    "phase.perceive.fold": emit_phase_perceive_fold_for_state,
    "phase.think.fold": emit_phase_think_fold_for_state,
    "phase.reflect.fold": emit_phase_reflect_fold_for_state,
    "phase.remember.fold": emit_phase_remember_fold_for_state,
    "phase.stop.fold": emit_phase_stop_fold_for_state,
    "phase_graph.subgraph.enter": emit_phase_graph_subgraph_enter_for_state,
    "phase_graph.subgraph.exit": emit_phase_graph_subgraph_exit_for_state,
    "terminal.commit": emit_terminal_commit_for_state,
}


def emit_for_node(ep_id: str, state: AgentState, **kwargs: Any) -> None:
    """Dispatch one EP by id with ``contextlib.suppress(Exception)``.

    Unknown ``ep_id`` (including the special ``reasoner_meta`` marker
    that is wired via :func:`emit_reasoner_meta_for_node`) is silently
    ignored — the driver does not maintain the EP vocabulary, the
    ``EXECUTION_POINTS`` whitelist does.
    """
    fn = _EP_DISPATCH.get(ep_id)
    if fn is None:
        return
    with contextlib.suppress(Exception):
        fn(state, **kwargs)


def dispatch_node_emits(node_config: Mapping[str, Any] | None, key: str, state: Any) -> None:
    """Fire one node's declared ``emit_on_enter`` / ``emit_on_exit`` list.

    Called by the graph driver around every ``strategy.execute`` so the
    declaration fires for *every* binding. Dispatch that lives in one
    strategy class silently skips the others: ``terminal.commit``
    declares ``emit_on_exit`` and binds to ``terminate``, so a
    strategy-local dispatcher never fired it and the anchor the
    ``node_event_emission`` boot check requires was never written.

    Reads the list from ``node_config["config"][key]`` (the yaml shape
    the lifter hands over), falling back to ``node_config[key]`` for
    hand-built plans. A non-list value is a no-op; per-EP failures are
    contained so a misconfigured EP does not abort the graph
    (ADR-0240 §Decision).
    """
    if not isinstance(node_config, Mapping):
        return
    emits: Any = None
    inner = node_config.get("config")
    if isinstance(inner, Mapping):
        emits = inner.get(key)
    if emits is None:
        emits = node_config.get(key)
    if not isinstance(emits, (list, tuple)):
        return
    for ep_id in emits:
        with contextlib.suppress(Exception):
            emit_for_node(ep_id, state)


def emit_reasoner_meta_for_node(state: AgentState, plan: Any, render: Any) -> None:
    """Special helper for the ``reasoner_meta`` EP.

    The private ``_emit_reasoner_meta_from_render`` takes ``plan`` and
    ``render`` positionally rather than ``state``, so it bypasses
    :func:`emit_for_node`. Errors are contained to match the rest of
    the dispatcher contract.
    """
    from lca.infrastructure.session.emit.cognitive_emit import (
        _emit_reasoner_meta_from_render,
    )

    del state  # accepted for signature symmetry with emit_for_node
    with contextlib.suppress(Exception):
        _emit_reasoner_meta_from_render(plan, render)


__all__ = ["dispatch_node_emits", "emit_for_node", "emit_reasoner_meta_for_node"]
