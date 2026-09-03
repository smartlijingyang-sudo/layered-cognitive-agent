"""spine_step_tree_accumulator subscriber 端到端（ADR-0181 试点盖章条件 3 / ADR-0183 PR-7）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.event import Category
from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
)
from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
    SpineStepTreeAccumulator,
)
from lca_kernel.events.bus import EventBus
from lca_kernel.events.errors import UnauthorizedSubscribeError
from lca_kernel.events import _DEFAULT_CONFIG_DIR
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    SpineStepTreeAccumulator.reset()
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    b = EventBus(EventRegistry.load(config_dir))
    b.subscribe(
        plugin=SpineStepTreeAccumulator,
        category=Category("spine.cognition.brain.perceive.start"),
        on_event=SpineStepTreeAccumulator(),
    )
    return b


def test_authorized_subscriber_receives(bus: EventBus) -> None:
    bus.publish(
        SpineEventPayload(
            execution_point="brain.perceive.start",
            channel="fact",
            payload={"state_id": "s1"},
        ),
        producer=ReflectorClass,
    )
    assert len(SpineStepTreeAccumulator._state) == 1
    assert SpineStepTreeAccumulator._state[0]["state_id"] == "s1"


def test_unauthorized_subscriber_rejected(bus: EventBus) -> None:
    """盖章 3: 偷听 — 未在 yaml subscribers 白名单的 plugin 调 subscribe → raise。"""

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedSubscribeError):
        bus.subscribe(
            plugin=NotInWhitelist,
            category=Category("spine.cognition.brain.perceive.start"),
            on_event=lambda p, r: None,
        )
