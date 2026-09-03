"""ADR-0183 PR-7 EventBus 鉴权测试。"""

from __future__ import annotations

import pytest

from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca.plugins.events.sinks.journal.sink import JournalSink
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca_kernel.events import Category, EventRef, TeamDelegationCacheHit
from lca_kernel.events.bus import EventBus, FailureSemantics
from lca_kernel.events.errors import (
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)


def _make_bus() -> EventBus:
    from lca_kernel.events.test_catalog import build_test_bus
    return build_test_bus()


@pytest.fixture
def bus() -> EventBus:
    return _make_bus()


def test_authorized_publish_returns_event_ref(bus: EventBus) -> None:
    ref = bus.publish(
        TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3),
        producer=DelegationCachePlugin,
    )
    assert isinstance(ref, EventRef)
    assert ref.category == Category.TEAM_DELEGATION_CACHE_HIT.value


def test_unauthorized_publish_raises(bus: EventBus) -> None:
    class _RoguePlugin:
        pass

    with pytest.raises(UnauthorizedPublishError) as exc_info:
        bus.publish(
            TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
            producer=_RoguePlugin,
        )
    assert exc_info.value.plugin_id.endswith("_RoguePlugin")


def test_authorized_subscribe_receives_events(bus: EventBus) -> None:
    received: list = []
    bus.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=lambda p, r: received.append((p, r)),
    )
    bus.publish(
        TeamDelegationCacheHit(callee_role="a", subtask="b", step=1),
        producer=DelegationCachePlugin,
    )
    assert len(received) == 1
    payload, _ = received[0]
    assert payload.callee_role == "a"


def test_unauthorized_subscribe_raises(bus: EventBus) -> None:
    class _RogueSubscriber:
        pass

    with pytest.raises(UnauthorizedSubscribeError):
        bus.subscribe(
            plugin=_RogueSubscriber,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )


def test_publish_requires_plugin(bus: EventBus) -> None:
    with pytest.raises(MissingPluginIdentityError, match="publish"):
        bus.publish(
            TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
            producer=None,  # type: ignore[arg-type]
        )


def test_subscribe_requires_plugin(bus: EventBus) -> None:
    with pytest.raises(MissingPluginIdentityError, match="subscribe"):
        bus.subscribe(
            plugin=None,  # type: ignore[arg-type]
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            on_event=lambda _p, _r: None,
        )


def test_consumer_exception_does_not_propagate(bus: EventBus) -> None:
    def boom(_p, _r):
        raise RuntimeError("boom")

    bus.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        on_event=boom,
        failure=FailureSemantics.CONTAINED,
    )
    ref = bus.publish(
        TeamDelegationCacheHit(callee_role="a", subtask="b", step=1),
        producer=DelegationCachePlugin,
    )
    assert isinstance(ref, EventRef)


def test_journal_sink_in_registry(bus: EventBus) -> None:
    """JournalSink 在 yaml subscribers 白名单 → can_subscribe 通过。"""
    cat = Category.TEAM_DELEGATION_CACHE_HIT
    assert bus.registry.can_subscribe(JournalSink, cat) is True
    assert bus.registry.can_subscribe(ConsoleProjectorSubscriber, cat) is True
    assert bus.registry.can_publish(DelegationCachePlugin, cat) is True
