"""FactGateway bound-session path tests (ADR-0194 P5-01)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from lca.contracts.harness.tasks.session import session_event
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.policy.gate_policy import GateDecided
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit import emit_gate_decided_from_policy
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


@session_event("test.gateway.flag.catalog.v1")
@dataclass(frozen=True)
class _FlagCatalogPayload:
    kind: str


def _state(*, step: int = 0) -> AgentState:
    return AgentState(
        trace_id="trace:flag",
        task="test",
        budget=create_budget(max_steps=4),
        step=step,
    )


def test_append_catalog_bound_uses_gateway() -> None:
    session = Session("t-flag-gateway")
    token = set_publish_session(session)
    try:
        with patch("lca.loop.fact_gateway.DefaultFactGateway.append_catalog") as gateway_append:
            append_catalog_bound(_FlagCatalogPayload(kind="probe"), actor="gate")
        gateway_append.assert_called_once()
    finally:
        reset_publish_session(token)


def test_append_catalog_bound_writes_session_fact() -> None:
    session = Session("t-flag-write")
    token = set_publish_session(session)
    try:
        receipt = append_catalog_bound(_FlagCatalogPayload(kind="legacy"), actor="perceive")
        assert receipt is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "test.gateway.flag.catalog.v1"
        assert event.actor == "perceive"
    finally:
        reset_publish_session(token)


def test_publish_ep_bound_uses_gateway() -> None:
    session = Session("t-flag-ep")
    token = set_publish_session(session)
    try:
        with patch("lca.loop.fact_gateway.DefaultFactGateway.publish_ep") as gateway_publish:
            publish_ep_bound("brain.perceive.start", {"source": "probe"}, actor="gate")
        gateway_publish.assert_called_once()
    finally:
        reset_publish_session(token)


def test_cognitive_emit_uses_gateway() -> None:
    session = Session("t-flag-cognitive")
    token = set_publish_session(session)
    try:
        state = _state(step=2)
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-flag",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
            ),
        )
        events = [event for event in session.snapshot_events() if event.type == "gate.decided.v1"]
        assert len(events) == 1
    finally:
        reset_publish_session(token)
