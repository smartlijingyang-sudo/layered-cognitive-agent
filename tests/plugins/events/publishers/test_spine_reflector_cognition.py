"""spine_reflector_cognition publisher 端到端（ADR-0181 试点盖章条件 1+2）。"""
from __future__ import annotations

import pytest

from lca_kernel.events.errors import UnauthorizedPublishError
from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism(tmp_path) -> EventMechanism:
    """用工作区 lca_kernel/events/config 构造机制；tmp_path 透传给 sink 落盘。"""
    from pathlib import Path

    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_authorized_publisher_sends(monkeypatch, mechanism: EventMechanism) -> None:
    """盖章 1: 业务方只调一行 + typed payload + 鉴权声明通过。"""
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = mechanism.send(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            plugin=ReflectorClass,
        )
        assert ref.category == "spine.cognition.brain.perceive.start"
        assert ref.event_id
    finally:
        EventMechanism.set_default(None)


def test_unauthorized_publisher_rejected(mechanism: EventMechanism) -> None:
    """盖章 2: 未在 yaml publishers 白名单的 plugin 调 send → UnauthorizedPublish。"""
    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        mechanism.send(
            SpineEventPayload(
                execution_point="brain.perceive.start",
                channel="fact",
                payload={"state_id": "s1"},
            ),
            plugin=NotInWhitelist,
        )
