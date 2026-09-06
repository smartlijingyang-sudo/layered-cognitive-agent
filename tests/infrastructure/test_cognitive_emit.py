"""Session cognitive emit tests (gate.decided.v1 / context.manifested.v1 / brain.think)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.contracts.harness.fold.perceive import (
    fold_context_manifest_from_events,
    fold_gate_decisions_from_events,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.infrastructure.session.cognitive_emit import (
    emit_brain_think_end_for_state,
    emit_brain_think_start_for_state,
    emit_context_manifested_for_state,
    emit_gate_decided_from_policy,
    run_brain_think_with_spine_facts,
)
from lca.loop.fact_gateway import publish_ep_bound, reset_fact_gateway_env
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def _state(*, step: int = 0) -> AgentState:
    return AgentState(
        trace_id="trace:cognitive-emit",
        task="test",
        budget=create_budget(max_steps=8),
        step=step,
    )


def test_emit_gate_decided_from_policy_appends_session_fact() -> None:
    session = Session("gate_emit")
    token = set_publish_session(session)
    try:
        state = _state(step=2)
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-1",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
                policy_fact=PolicyFact(
                    kind="repeat_tool_call",
                    message="warning",
                    source="repeat_tool_call",
                ),
            ),
        )
        events = [event for event in session.snapshot_events() if event.type == "gate.decided.v1"]
        assert len(events) == 1
        folded = fold_gate_decisions_from_events(session.snapshot_events(), step=2)
        assert len(folded) == 1
        assert folded[0].gate == "RepeatToolCallGate"
    finally:
        reset_publish_session(token)


def test_record_gate_decided_appends_session_fact() -> None:
    session = Session("gate_record")
    token = set_publish_session(session)
    try:
        state = _state(step=1)
        record_gate_decided(
            state,
            GateDecided(
                event_id="gate-2",
                gate="ToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name="runCommand",
                rationale="blocked",
                policy_fact=PolicyFact(
                    kind="tool_loop_break",
                    message="stopped",
                    source="tool_loop_breaker",
                ),
            ),
        )
        events = [event for event in session.snapshot_events() if event.type == "gate.decided.v1"]
        assert len(events) == 1
    finally:
        reset_publish_session(token)


def test_emit_gate_decided_noop_when_session_unbound() -> None:
    state = _state()
    assert (
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-3",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
            ),
        )
        is None
    )


@pytest.mark.asyncio
async def test_phase_fact_emitter_appends_context_manifested() -> None:
    from lca.contracts.models.core.budget import create_budget
    from lca.contracts.models.core.perception import ContextManifest
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        PhaseResult,
        SemanticPhase,
    )
    from lca.harness.declarative.lifecycle.phase_fact_emitter import emit_phase_catalog_facts
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )
    from lca.plugins.session.runtime.session import Session

    session = Session("manifest_emit")
    token = set_publish_session(session)
    try:
        state = AgentState(
            trace_id="trace:cognitive-emit",
            task="test",
            budget=create_budget(max_steps=8),
            step=3,
        )
        manifest = ContextManifest(items=(), digest="abc123")
        emit_phase_catalog_facts(
            semantic_phase=SemanticPhase.PERCEIVE,
            result=PhaseResult(result_kind="context", payload=manifest),
            state=state,
        )
        events = [
            event for event in session.snapshot_events() if event.type == "context.manifested.v1"
        ]
        assert len(events) == 1
        folded = fold_context_manifest_from_events(session.snapshot_events(), step=3)
        assert folded is not None
        assert folded.digest == manifest.digest
    finally:
        reset_publish_session(token)


def test_emit_context_manifested_for_state_serializes_items() -> None:
    session = Session("manifest_items")
    token = set_publish_session(session)
    try:
        state = _state(step=4)
        manifest = ContextManifest(
            items=(
                ContextItem(
                    kind="policy_fact",
                    payload="loop warning",
                    provenance="repeat_tool_call",
                    extra={"kind": "repeat_tool_call", "gate": "RepeatToolCallGate"},
                ),
            ),
            digest="abc123",
        )
        emit_context_manifested_for_state(state, manifest)
        folded = fold_context_manifest_from_events(session.snapshot_events(), step=4)
        assert folded is not None
        assert len(folded.items) == 1
        assert folded.items[0].kind == "policy_fact"
        assert folded.items[0].provenance == "repeat_tool_call"
    finally:
        reset_publish_session(token)


def test_emit_brain_think_start_routes_via_publish_ep_bound() -> None:
    session = Session("brain_think_start")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        state = _state()
        with patch(
            "lca.infrastructure.session.cognitive_emit.publish_ep_bound",
            wraps=publish_ep_bound,
        ) as publish:
            emit_brain_think_start_for_state(state)
        publish.assert_called_once()
        args, kwargs = publish.call_args
        assert args[0] == "brain.think.start"
        assert args[1]["state_id"] == state.trace_id
        assert kwargs["state"] is state
        assert kwargs["actor"] == "brain"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


def test_emit_brain_think_end_appends_spine_fact() -> None:
    session = Session("brain_think_end")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        state = _state()
        emit_brain_think_start_for_state(state)
        emit_brain_think_end_for_state(state, outcome="failure")
        events = [
            event
            for event in session.snapshot_events()
            if event.type.startswith("spine.cognition.brain.think.")
        ]
        assert len(events) == 2
        assert events[0].type == "spine.cognition.brain.think.start"
        assert events[1].type == "spine.cognition.brain.think.end"
        assert events[1].data["payload"]["outcome"] == "failure"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


@pytest.mark.asyncio
async def test_run_brain_think_with_spine_facts_envelopes_decision() -> None:
    session = Session("brain_think_envelope")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        state = _state()
        decision = Decision(
            decision_id="d-brain-think",
            action_type="respond",
            rationale="ok",
            confidence=1.0,
        )
        brain = AsyncMock()
        brain.think = AsyncMock(return_value=decision)
        result = await run_brain_think_with_spine_facts(brain, state)
        assert result is decision
        brain.think.assert_awaited_once_with(state)
        events = [
            event
            for event in session.snapshot_events()
            if event.type.startswith("spine.cognition.brain.think.")
        ]
        assert len(events) == 2
        assert events[1].data["payload"]["outcome"] == "success"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


@pytest.mark.asyncio
async def test_run_brain_think_with_spine_facts_emits_failure_on_error() -> None:
    session = Session("brain_think_failure")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        state = _state()
        brain = AsyncMock()
        brain.think = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await run_brain_think_with_spine_facts(brain, state)
        events = [
            event
            for event in session.snapshot_events()
            if event.type == "spine.cognition.brain.think.end"
        ]
        assert len(events) == 1
        assert events[0].data["payload"]["outcome"] == "failure"
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)
