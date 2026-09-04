"""RunSessionBuilder binds session.store onto publish/observe slots.

Locks:
- session.store present → create Session(run_id), set_publish_session + set_session
- session.store missing → structlog warning, publishers stay on EventBus
- close() resets slots and disposes the Session
- step_tree EventSpine.subscribe stays in place (fold cut is a later PR)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import structlog

from lca.infrastructure.observability.backends.run_locator_fs import FilesystemRunLocator
from lca.plugins.events._session_observe import current_session, set_session
from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    publish_via_session,
)
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.transport.webserver.handlers.runs.execute import create_run_session
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry
from lca_kernel.events.bus import EventBus
from lca_kernel.events.test_catalog import build_test_bus


class _StubSpine:
    """EventSpine stub — records subscribe so step_tree wiring stays observable."""

    def __init__(self) -> None:
        self.subscribers: list[Any] = []

    def subscribe(self, fn: Any) -> Any:
        self.subscribers.append(fn)
        return lambda: None

    def append(self, **_: object) -> int:
        return 0

    def close(self) -> None:
        return None


@dataclass
class _SpyFactory:
    process: object = field(default=None)

    def create_run_components(self, *, spine_path: Path) -> Any:
        from dataclasses import dataclass as _dc

        from lca.contracts.observability.run_journal import RunJournalComponents
        from lca.infrastructure.observability.journal.stream.live_tail import LiveTail

        @_dc(frozen=True)
        class _StubBundle:
            deriver: object | None = None
            narrative_writer: object | None = None

        return RunJournalComponents(
            writer=LiveTail(),
            tail=LiveTail(),
            step_tree_writer=_StubBundle(narrative_writer=object()),
        )

    def create_process_journal(self) -> Any:
        from lca.infrastructure.observability.journal.engine.process import ProcessJournal

        if self.process is None:
            self.process = ProcessJournal()
        return self.process


class _Context:
    """cordis-style ctx with inject() for require_capability."""

    def __init__(
        self,
        *,
        factory: _SpyFactory,
        registry_obj: Any,
        spine: Any,
        session_store: SessionStore | None = None,
    ) -> None:
        self._services = {
            "run_ledger_factory": factory,
            "writable_face_registry": registry_obj,
            "event_spine": spine,
            "process_journal": object(),
        }
        if session_store is not None:
            self._services["session.store"] = session_store
        from lca.infrastructure.observability import NamedRegistry
        from lca.infrastructure.observability.loop_cursor.close_barrier_impl import (
            StdCloseBarrier,
        )
        from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
        from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
            StdModelVisibleCapture,
        )
        from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
            NullPersistenceCoordinator,
        )
        from lca.infrastructure.observability.loop_cursor.projection_host import (
            StdProjectionHost,
        )

        self._services["observability.loop_cursor"] = NamedRegistry()
        self._services["observability.projection_host"] = NamedRegistry()
        self._services["observability.model_visible"] = NamedRegistry()
        self._services["observability.close_barrier"] = NamedRegistry()
        self._services["observability.persistence"] = NamedRegistry()
        self._services["observability.loop_cursor"].register(
            "standard", LoopCursorFactory.from_profile
        )
        self._services["observability.projection_host"].register(
            "standard", lambda initial=None, **_: StdProjectionHost(initial=initial)
        )
        self._services["observability.model_visible"].register(
            "standard", lambda run_dir, **_: StdModelVisibleCapture(run_dir=run_dir)
        )
        self._services["observability.close_barrier"].register(
            "standard",
            lambda persistence, host, close_emitter, **_: StdCloseBarrier(
                persistence=persistence, host=host, close_emitter=close_emitter
            ),
        )
        self._services["observability.persistence"].register(
            "null", lambda **_: NullPersistenceCoordinator()
        )

    def inject(self, key: str, *, default: Any = ...) -> Any:
        if key in self._services:
            return self._services[key]
        if default is not ...:
            return default
        raise KeyError(key)


def _writable_registry() -> Any:
    from lca.infrastructure.observability.writable_matrix import (
        LineCoalescer,
        NdjsonSerializer,
        NullStorage,
        SpineEmitter,
        StandardDriver,
    )
    from lca.infrastructure.observability.writable_matrix.registry import (
        WritableFaceRegistry,
    )

    registry_obj = WritableFaceRegistry()
    registry_obj.register("emitter", SpineEmitter())
    registry_obj.register("driver", StandardDriver())
    registry_obj.register("coalescer", LineCoalescer())
    registry_obj.register("serializer", NdjsonSerializer())
    registry_obj.register("storage", NullStorage())
    return registry_obj


def _build_ctx(*, session_store: SessionStore | None = None) -> tuple[_Context, _StubSpine]:
    spine = _StubSpine()
    ctx = _Context(
        factory=_SpyFactory(),
        registry_obj=_writable_registry(),
        spine=spine,
        session_store=session_store,
    )
    return ctx, spine


def _teardown(session: Any) -> None:
    session.close("completed")


def _sp_payload() -> Any:
    from lca_kernel.events.payloads import Category, SpineEventPayload

    return SpineEventPayload(
        category=Category("spine.cognition.brain.perceive.start"),
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": "s1"},
    )


@pytest.fixture(autouse=True)
def _clear_observe_slot() -> Iterator[None]:
    set_session(None)
    yield
    set_session(None)


def test_builder_binds_session_store_to_publish_and_observe_slots(tmp_path: Path) -> None:
    store = SessionStore()
    ctx, spine = _build_ctx(session_store=store)
    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))

    session = create_run_session(registry, question="q", user_text="u", ctx=ctx)
    try:
        bound = session.event_session
        assert bound is not None
        assert bound.run_id == session.run_id
        assert store.get(session.run_id) is bound.bridge.inner
        assert current_publish_session() is bound.bridge
        assert current_session() is bound.bridge
        # ADR-0186 PR-3g: step_tree 走 fold，不再 EventSpine.subscribe
        assert not spine.subscribers
        assert session.thread_tree_writer is not None
        assert session.thread_tree_writer.__class__.__name__ == "StepTreeFoldDeriver"
    finally:
        _teardown(session)

    assert store.get(session.run_id) is None
    assert current_publish_session() is None
    assert current_session() is None


def test_builder_without_session_store_degrades_to_eventbus(tmp_path: Path) -> None:
    ctx, spine = _build_ctx(session_store=None)
    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))

    with structlog.testing.capture_logs() as logs:
        session = create_run_session(registry, question="q", user_text="u", ctx=ctx)
    try:
        assert session.event_session is None
        assert current_publish_session() is None
        assert current_session() is None
        assert not spine.subscribers
        assert any(item.get("event") == "session.store.missing" for item in logs)
    finally:
        _teardown(session)


def test_bound_session_append_records_log_and_dual_writes_eventbus(
    tmp_path: Path,
) -> None:
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    store = SessionStore()
    ctx, _spine = _build_ctx(session_store=store)
    registry = RunRegistry(locator=FilesystemRunLocator(root=tmp_path))
    bus = build_test_bus()
    EventBus.set_default(bus)
    session = create_run_session(registry, question="q", user_text="u", ctx=ctx)
    try:
        payload = _sp_payload()
        ref = publish_via_session(payload, producer=ReflectorClass)
        inner = session.event_session.bridge.inner
        assert inner.seq == 1
        event = inner.event_at(0)
        assert event is not None
        assert event.type == "spine.cognition.brain.perceive.start"
        assert event.data == {"state_id": "s1"}
        assert ref.category == "spine.cognition.brain.perceive.start"
        assert ref.event_id
    finally:
        EventBus.set_default(None)
        _teardown(session)
