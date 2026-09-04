"""spine_writable_matrix publisher 端到端测试（ADR-0181 PR-10）。

writable_matrix 路径下 cursor 用 WritableMatrixPlugin.send 入口。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.bus import EventBus


def test_writable_matrix_send(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_writable_matrix.plugin import (
        WritableMatrixPlugin,
    )

    ref = WritableMatrixPlugin.send(
        execution_point="writable.iteration.halt",
        channel="control",
        payload={"run_id": "r1", "reason": "test"},
    )
    assert ref.category == "spine.writable.iteration.halt"


def test_writable_matrix_send_unknown_ep() -> None:
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
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineEventPayload(
                execution_point="writable.iteration.halt",
                channel="control",
                payload={"run_id": "r1", "reason": "x"},
            ),
            producer=int,  # int is not a plugin class
        )
