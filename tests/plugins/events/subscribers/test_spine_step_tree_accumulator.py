"""spine_step_tree_accumulator subscriber 端到端（ADR-0181 试点盖章条件 3: 防偷听）。"""
from __future__ import annotations

import pytest

from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
)
from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
    SpineStepTreeAccumulator,
)
from lca_kernel.events.errors import UnauthorizedSubscribeError
from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    from pathlib import Path

    SpineStepTreeAccumulator.reset()
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    m = EventMechanism(EventRegistry.load(config_dir))
    m.subscribe(
        plugin=SpineStepTreeAccumulator,
        category=__import__("lca.contracts.event", fromlist=["Category"]).Category(
            "spine.cognition.brain.perceive.start"
        ),
        callback=SpineStepTreeAccumulator(),
    )
    return m


def test_authorized_subscriber_receives(mechanism: EventMechanism) -> None:
    mechanism.send(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s1"},
        ),
        plugin=ReflectorClass,
    )
    assert len(SpineStepTreeAccumulator._state) == 1
    assert SpineStepTreeAccumulator._state[0]["state_id"] == "s1"


def test_unauthorized_subscriber_rejected(mechanism: EventMechanism) -> None:
    """盖章 3: 偷听 — 未在 yaml subscribers 白名单的 plugin 调 subscribe → raise。"""
    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedSubscribeError):
        mechanism.subscribe(
            plugin=NotInWhitelist,
            category=__import__("lca.contracts.event", fromlist=["Category"]).Category(
                "spine.cognition.brain.perceive.start"
            ),
            callback=lambda p, r: None,
        )
