"""ADR-0195 P1-03..05: lca.session.* public API."""

from __future__ import annotations

from lca.session import (
    BoundRunEventSession,
    EventSessionBinder,
    RunEventSessionBridge,
    Session,
    SessionRecoveryError,
    SessionRepairError,
    UnknownSessionEventTypeError,
    bind_run_event_session,
    bind_run_event_session_from_store,
    event_session_binder_from_scope,
    known_session_event_types,
    recover_live_agent,
    repair_interrupted_turn,
    unbind_run_event_session,
    validate_event_type_for_read,
)
from lca.session import append as session_append
from lca.session import bind as session_bind
from lca.session import catalog as session_catalog
from lca.session import recovery as session_recovery
from lca.session import repair as session_repair


def test_append_public_api() -> None:
    assert Session is session_append.Session


def test_catalog_public_api() -> None:
    assert UnknownSessionEventTypeError is session_catalog.UnknownSessionEventTypeError
    assert known_session_event_types is session_catalog.known_session_event_types
    assert validate_event_type_for_read is session_catalog.validate_event_type_for_read
    assert session_catalog.known_session_event_types() is not None
    assert "turn.started.v1" in session_catalog.known_session_event_types()


def test_bind_public_api() -> None:
    assert BoundRunEventSession is session_bind.BoundRunEventSession
    assert EventSessionBinder is session_bind.EventSessionBinder
    assert RunEventSessionBridge is session_bind.RunEventSessionBridge
    assert bind_run_event_session is session_bind.bind_run_event_session
    assert bind_run_event_session_from_store is session_bind.bind_run_event_session_from_store
    assert event_session_binder_from_scope is session_bind.event_session_binder_from_scope
    assert unbind_run_event_session is session_bind.unbind_run_event_session


def test_repair_public_api() -> None:
    assert repair_interrupted_turn is session_repair.repair_interrupted_turn
    assert SessionRepairError is session_repair.SessionRepairError


def test_recovery_public_api() -> None:
    assert recover_live_agent is session_recovery.recover_live_agent
    assert SessionRecoveryError is session_recovery.SessionRecoveryError


def test_session_append_roundtrip() -> None:
    session = Session("public-api-test")
    event = session.append("turn.started.v1", {"turn": 1})
    assert event.type == "turn.started.v1"
    assert event.seq == 0
