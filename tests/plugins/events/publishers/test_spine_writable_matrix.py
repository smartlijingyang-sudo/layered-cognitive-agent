"""spine_writable_matrix publisher 端到端测试（ADR-0181 PR-10）。

writable_matrix 路径下 cursor 用 WritableMatrixPlugin.send 入口。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    from lca_kernel.events.test_catalog import build_test_bus
    return build_test_bus(config_dir)


def test_writable_matrix_send(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
        WritableMatrixPlugin,
    )

    EventBus.set_default(bus)
    try:
        ref = WritableMatrixPlugin.send(
            execution_point="writable.iteration.halt",
            channel="control",
            payload={"run_id": "r1", "reason": "test"},
        )
        assert ref.category == "spine.writable.iteration.halt"
    finally:
        EventBus.set_default(None)


def test_writable_matrix_send_unknown_ep(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
        WritableMatrixPlugin,
    )

    with pytest.raises(ValueError):
        WritableMatrixPlugin.send(
            execution_point="totally.unknown.ep",
            channel="control",
            payload={"x": 1},
        )


def test_writable_matrix_send_unauthorized(bus: EventBus) -> None:
    """未注册 plugin 类无法 send：WritableMatrixPlugin 类在 yaml publishers 中。"""
    from lca_kernel.events.payloads import SpineEventPayload

    EventBus.set_default(bus)
    try:
        with pytest.raises(Exception):
            bus.publish(
                SpineEventPayload(
                    execution_point="writable.iteration.halt",
                    channel="control",
                    payload={"run_id": "r1", "reason": "x"},
                ),
                plugin=int,  # int is not a plugin class
            )
    finally:
        EventBus.set_default(None)
