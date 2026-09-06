"""Session cognitive emit tests (gate.decided.v1 / context.manifested.v1)."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.cognition.perceive_hub import SequentialPerceiveHub
from lca.cognition.perceive_sink import NullSink
from lca.contracts.harness.fold.perceive import (
    fold_context_manifest_from_events,
    fold_gate_decisions_from_events,
)
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.infrastructure.session.cognitive_emit import (
    emit_context_manifested_for_state,
    emit_gate_decided_from_policy,
)
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
async def test_perceive_hub_appends_context_manifested() -> None:
    session = Session("manifest_emit")
    token = set_publish_session(session)
    try:
        state = _state(step=3)
        hub = SequentialPerceiveHub(sensors=[], memory=None, sink=NullSink())
        manifest = await hub.perceive(state)
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
