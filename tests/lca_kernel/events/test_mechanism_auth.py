"""ADR-0180 试点：EventMechanism 鉴权测试（plugin class 形态）。"""

from __future__ import annotations

import pytest

from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca.plugins.events.sinks.journal.sink import JournalSink
from lca.plugins.events.subscribers.console_projector.subscriber import (
    ConsoleProjectorSubscriber,
)
from lca_kernel.events import Category, EventMechanism, EventRef, TeamDelegationCacheHit
from lca_kernel.events.errors import (
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)


def test_authorized_send_returns_event_ref(mechanism: EventMechanism) -> None:
    ref = mechanism.send(
        TeamDelegationCacheHit(callee_role="analyst", subtask="汇总", step=3),
        plugin=DelegationCachePlugin,
    )
    assert isinstance(ref, EventRef)
    assert ref.category == Category.TEAM_DELEGATION_CACHE_HIT.value


def test_unauthorized_publish_raises(mechanism: EventMechanism) -> None:
    class _RoguePlugin:
        pass

    with pytest.raises(UnauthorizedPublishError) as exc_info:
        mechanism.send(
            TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
            plugin=_RoguePlugin,
        )
    assert exc_info.value.plugin_id.endswith("_RoguePlugin")


def test_authorized_subscribe_receives_events(mechanism: EventMechanism) -> None:
    received: list = []
    mechanism.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        callback=lambda p, r: received.append((p, r)),
    )
    mechanism.send(
        TeamDelegationCacheHit(callee_role="a", subtask="b", step=1),
        plugin=DelegationCachePlugin,
    )
    assert len(received) == 1
    payload, _ = received[0]
    assert payload.callee_role == "a"


def test_unauthorized_subscribe_raises(mechanism: EventMechanism) -> None:
    class _RogueSubscriber:
        pass

    with pytest.raises(UnauthorizedSubscribeError):
        mechanism.subscribe(
            plugin=_RogueSubscriber,
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            callback=lambda p, r: None,
        )


def test_send_requires_plugin(mechanism: EventMechanism) -> None:
    with pytest.raises(MissingPluginIdentityError, match="send"):
        mechanism.send(
            TeamDelegationCacheHit(callee_role="x", subtask="y", step=0),
            plugin=None,  # type: ignore[arg-type]
        )


def test_subscribe_requires_plugin(mechanism: EventMechanism) -> None:
    with pytest.raises(MissingPluginIdentityError, match="subscribe"):
        mechanism.subscribe(
            plugin=None,  # type: ignore[arg-type]
            category=Category.TEAM_DELEGATION_CACHE_HIT,
            callback=lambda p, r: None,
        )


def test_consumer_exception_does_not_propagate(mechanism: EventMechanism) -> None:
    def boom(_p, _r):
        raise RuntimeError("boom")

    mechanism.subscribe(
        plugin=ConsoleProjectorSubscriber,
        category=Category.TEAM_DELEGATION_CACHE_HIT,
        callback=boom,
    )
    ref = mechanism.send(
        TeamDelegationCacheHit(callee_role="a", subtask="b", step=1),
        plugin=DelegationCachePlugin,
    )
    assert isinstance(ref, EventRef)


def test_journal_sink_in_registry(mechanism: EventMechanism) -> None:
    """JournalSink 在 yaml subscribers 白名单 → can_subscribe 通过。"""
    cat = Category.TEAM_DELEGATION_CACHE_HIT
    assert mechanism.registry.can_subscribe(JournalSink, cat) is True
    assert mechanism.registry.can_subscribe(ConsoleProjectorSubscriber, cat) is True
    assert mechanism.registry.can_publish(DelegationCachePlugin, cat) is True
