"""LCA_FACT_GATEWAY rollback flag tests (ADR-0194 P1-09)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from lca.contracts.harness.tasks.session import session_event
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.state import AgentState
from lca.infrastructure.session.cognitive_emit import emit_gate_decided_from_policy
from lca.loop.fact_gateway import (
    append_catalog_bound,
    is_fact_gateway_enabled,
    publish_ep_bound,
    reset_fact_gateway_env,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
    ],
)
def test_is_fact_gateway_enabled(raw: str | None, expected: bool, monkeypatch) -> None:
    monkeypatch.delenv("LCA_FACT_GATEWAY", raising=False)
    if raw is not None:
        monkeypatch.setenv("LCA_FACT_GATEWAY", raw)
    assert is_fact_gateway_enabled() is expected


def test_append_catalog_bound_uses_gateway_when_enabled() -> None:
    reset_fact_gateway_env(enabled=True)
    session = Session("t-flag-gateway")
    token = set_publish_session(session)
    try:
        with (
            patch("lca.loop.fact_gateway.DefaultFactGateway.append_catalog") as gateway_append,
            patch("lca.loop.fact_gateway._legacy_append_catalog") as legacy_append,
        ):
            append_catalog_bound(_FlagCatalogPayload(kind="probe"), actor="gate")
        gateway_append.assert_called_once()
        legacy_append.assert_not_called()
    finally:
        reset_publish_session(token)
        reset_fact_gateway_env()


def test_append_catalog_bound_uses_legacy_when_disabled() -> None:
    reset_fact_gateway_env(enabled=False)
    session = Session("t-flag-legacy")
    token = set_publish_session(session)
    try:
        with (
            patch("lca.loop.fact_gateway.DefaultFactGateway.append_catalog") as gateway_append,
            patch("lca.loop.fact_gateway._legacy_append_catalog") as legacy_append,
        ):
            append_catalog_bound(_FlagCatalogPayload(kind="probe"), actor="gate")
        legacy_append.assert_called_once()
        gateway_append.assert_not_called()
    finally:
        reset_publish_session(token)
        reset_fact_gateway_env()


def test_append_catalog_legacy_path_appends_session_fact() -> None:
    reset_fact_gateway_env(enabled=False)
    session = Session("t-flag-legacy-write")
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
        reset_fact_gateway_env()


def test_publish_ep_bound_dual_path() -> None:
    session = Session("t-flag-ep")
    token = set_publish_session(session)
    try:
        reset_fact_gateway_env(enabled=True)
        with (
            patch("lca.loop.fact_gateway.DefaultFactGateway.publish_ep") as gateway_publish,
            patch("lca.loop.fact_gateway._legacy_publish_ep") as legacy_publish,
        ):
            publish_ep_bound("brain.perceive.start", {"source": "probe"}, actor="gate")
        gateway_publish.assert_called_once()
        legacy_publish.assert_not_called()

        reset_fact_gateway_env(enabled=False)
        with (
            patch("lca.loop.fact_gateway.DefaultFactGateway.publish_ep") as gateway_publish,
            patch("lca.loop.fact_gateway._legacy_publish_ep") as legacy_publish,
        ):
            publish_ep_bound("brain.perceive.start", {"source": "probe2"}, actor="gate")
        legacy_publish.assert_called_once()
        gateway_publish.assert_not_called()
    finally:
        reset_publish_session(token)
        reset_fact_gateway_env()


def test_cognitive_emit_honors_legacy_flag() -> None:
    reset_fact_gateway_env(enabled=False)
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
        reset_fact_gateway_env()
