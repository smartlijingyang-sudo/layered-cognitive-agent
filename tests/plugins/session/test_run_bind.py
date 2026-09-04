"""Session run-boundary bind — Carrier 与 in-process 共用（ADR-0186）。"""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    publish_via_session,
)
from lca.plugins.session.runtime.bind import (
    EventSessionBinder,
    bind_run_event_session_from_store,
    unbind_run_event_session,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.bus import EventBus
from lca_kernel.events.errors import MissingPublishSessionError
from lca_kernel.events.test_catalog import build_test_bus


@pytest.fixture
def bus() -> EventBus:
    b = build_test_bus()
    EventBus.set_default(b)
    yield b
    EventBus.reset_singleton()


def _payload() -> Any:
    from lca_kernel.events.payloads import Category, SpineEventPayload

    return SpineEventPayload(
        category=Category("spine.cognition.brain.perceive.start"),
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


def test_bind_enables_publish_via_session(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "run_bind_1")
    try:
        assert current_publish_session() is bound.bridge
        ref = publish_via_session(_payload(), producer=ReflectorClass)
        assert ref is not None
    finally:
        unbind_run_event_session(bound)
    assert current_publish_session() is None
    with pytest.raises(MissingPublishSessionError):
        publish_via_session(_payload(), producer=ReflectorClass)


def test_binder_skips_when_already_bound(bus: EventBus) -> None:
    store = SessionStore()
    outer = bind_run_event_session_from_store(store, "run_outer")
    binder = EventSessionBinder(store)
    try:
        with binder.bound("run_inner") as inner:
            assert inner is None
            assert current_publish_session() is outer.bridge
    finally:
        unbind_run_event_session(outer)


def test_binder_binds_when_slot_empty(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    store = SessionStore()
    binder = EventSessionBinder(store)
    with binder.bound("run_agent") as bound:
        assert bound is not None
        publish_via_session(_payload(), producer=ReflectorClass)
    assert current_publish_session() is None
