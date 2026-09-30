"""Barrel coverage for the split ``cognitive_emit`` package.

Every event-family emitter must stay importable from the original public
path (``lca.infrastructure.session.emit.cognitive_emit``) after the package
split, and each extracted family must keep producing spine facts through
the barrel.
"""

from __future__ import annotations

from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit import (
    emit_body_tool_execute_end_for_state,
    emit_body_tool_execute_start_for_state,
    emit_phase_perceive_fold_for_state,
    emit_phase_tool_call_start_for_state,
    emit_terminal_commit_for_state,
    emit_think_gate_start_for_state,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def _state() -> AgentState:
    return AgentState(
        trace_id="trace:barrel",
        task="test",
        budget=create_budget(max_steps=8),
        step=0,
    )


def test_barrel_exposes_each_event_family() -> None:
    """All event-family emitters resolve from the original public path."""
    from lca.infrastructure.session.emit.cognitive_emit import (
        emit_context_manifested,
        emit_critic_eval_start_for_state,
        emit_gate_decided,
        emit_prompt_assembler_start_for_state,
        emit_reasoner_reason_start_for_state,
        emit_skill_router_route_for_state,
        emit_synthesizer_merge_for_state,
        run_reasoner_generate_thoughts_with_spine_facts,
    )

    assert callable(emit_context_manifested)
    assert callable(emit_critic_eval_start_for_state)
    assert callable(emit_gate_decided)
    assert callable(emit_prompt_assembler_start_for_state)
    assert callable(emit_reasoner_reason_start_for_state)
    assert callable(emit_skill_router_route_for_state)
    assert callable(emit_synthesizer_merge_for_state)
    assert callable(run_reasoner_generate_thoughts_with_spine_facts)


def test_tool_event_family_emits_through_barrel() -> None:
    """Tool-call family emitters produce spine facts via the barrel."""
    session = Session("tool_barrel")
    token = set_publish_session(session)
    try:
        state = _state()
        emit_phase_tool_call_start_for_state(state)
        emit_body_tool_execute_start_for_state(state)
        emit_body_tool_execute_end_for_state(state)
        emit_think_gate_start_for_state(state)
        types = [event.type for event in session.snapshot_events()]
        assert "spine.phase.tool.call.start" in types
        assert "spine.body.tool.execute.start" in types
        assert "spine.body.tool.execute.end" in types
        assert "spine.cognition.think.gate.start" in types
    finally:
        reset_publish_session(token)


def test_step_event_family_emits_through_barrel() -> None:
    """Step/fold family emitters produce spine facts via the barrel."""
    session = Session("step_barrel")
    token = set_publish_session(session)
    try:
        state = _state()
        emit_terminal_commit_for_state(state)
        emit_phase_perceive_fold_for_state(state)
        types = [event.type for event in session.snapshot_events()]
        assert "spine.terminal.commit" in types
        assert "spine.phase.perceive.fold" in types
    finally:
        reset_publish_session(token)
