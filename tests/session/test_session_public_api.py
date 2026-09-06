"""ADR-0195 P1-03..05: lca.session.* public API re-exports."""

from __future__ import annotations

import lca.plugins.session.runtime.bind as plugin_bind
import lca.plugins.session.runtime.event_catalog as plugin_catalog
import lca.plugins.session.runtime.session as plugin_session
from lca.session import (
    BoundRunEventSession,
    EventSessionBinder,
    RunEventSessionBridge,
    Session,
    UnknownSessionEventTypeError,
    bind_run_event_session,
    bind_run_event_session_from_store,
    event_session_binder_from_scope,
    known_session_event_types,
    unbind_run_event_session,
    validate_event_type_for_read,
)
from lca.session import append as session_append
from lca.session import bind as session_bind
from lca.session import catalog as session_catalog


def test_append_reexport_is_plugin_session() -> None:
    assert Session is plugin_session.Session
    assert session_append.Session is plugin_session.Session


def test_catalog_reexports_match_plugin_module() -> None:
    assert UnknownSessionEventTypeError is plugin_catalog.UnknownSessionEventTypeError
    assert known_session_event_types is plugin_catalog.known_session_event_types
    assert validate_event_type_for_read is plugin_catalog.validate_event_type_for_read
    assert session_catalog.known_session_event_types() is not None
    assert "turn.started.v1" in session_catalog.known_session_event_types()


def test_bind_reexports_match_plugin_module() -> None:
    assert BoundRunEventSession is plugin_bind.BoundRunEventSession
    assert EventSessionBinder is plugin_bind.EventSessionBinder
    assert RunEventSessionBridge is plugin_bind.RunEventSessionBridge
    assert bind_run_event_session is plugin_bind.bind_run_event_session
    assert bind_run_event_session_from_store is plugin_bind.bind_run_event_session_from_store
    assert event_session_binder_from_scope is plugin_bind.event_session_binder_from_scope
    assert unbind_run_event_session is plugin_bind.unbind_run_event_session
    assert (
        session_bind.bind_run_event_session_from_store
        is plugin_bind.bind_run_event_session_from_store
    )


def test_repair_reexport_matches_public_module() -> None:
    import lca.plugins.session.runtime.repair as plugin_repair
    import lca.session.repair as session_repair

    assert session_repair.repair_interrupted_turn is plugin_repair.repair_interrupted_turn


def test_recovery_reexport_matches_public_module() -> None:
    import lca.plugins.session.runtime.recovery as plugin_recovery
    import lca.session.recovery as session_recovery

    assert session_recovery.recover_live_agent is plugin_recovery.recover_live_agent


def test_session_append_roundtrip() -> None:
    session = Session("public-api-test")
    event = session.append("turn.started.v1", {"turn": 1})
    assert event.type == "turn.started.v1"
    assert event.seq == 0
