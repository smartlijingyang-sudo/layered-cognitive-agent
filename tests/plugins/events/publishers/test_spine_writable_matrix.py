"""spine_writable_matrix publisher 端到端测试（ADR-0181 PR-10）。

writable_matrix 路径下 cursor 用 WritableMatrixPlugin.send 入口。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_writable_matrix_send(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
        WritableMatrixPlugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = WritableMatrixPlugin.send(
            execution_point="writable.iteration.halt",
            channel="control",
            payload={"run_id": "r1", "reason": "test"},
        )
        assert ref.category == "spine.writable.iteration.halt"
    finally:
        EventMechanism.set_default(None)


def test_writable_matrix_send_unknown_ep(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
        WritableMatrixPlugin,
    )

    with pytest.raises(ValueError):
        WritableMatrixPlugin.send(
            execution_point="totally.unknown.ep",
            channel="control",
            payload={"x": 1},
        )


def test_writable_matrix_send_unauthorized(mechanism: EventMechanism) -> None:
    """未注册 plugin 类无法 send：WritableMatrixPlugin 类在 yaml publishers 中。"""
    from lca_kernel.events.payloads import SpineEventPayload

    EventMechanism.set_default(mechanism)
    try:
        with pytest.raises(Exception):
            mechanism.send(
                SpineEventPayload(
                    execution_point="writable.iteration.halt",
                    channel="control",
                    payload={"run_id": "r1", "reason": "x"},
                ),
                plugin=int,  # int is not a plugin class
            )
    finally:
        EventMechanism.set_default(None)
