"""spine_reflector_transport publisher 端到端测试（ADR-0181 PR-4）。

transport / kernel.run 全部 6 emit（route.enter / .exit / sse.publish +
kernel.run.start / .stop / .cancelled）在 EventMechanism 路径下能正常 send +
鉴权通过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    """用工作区 lca_kernel/events/config 构造机制。"""
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_emit_transport_all(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_transport import (
        plugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = plugin.emit_transport_route_enter(path="/runs", method="POST", run_id="r1")
        assert ref.category == "spine.transport.route.enter"
        ref = plugin.emit_transport_route_exit(path="/runs", method="POST", run_id="r1")
        assert ref.category == "spine.transport.route.exit"
        ref = plugin.emit_transport_sse_publish(path="/events", run_id="r1")
        assert ref.category == "spine.transport.sse.publish"
        ref = plugin.emit_kernel_run_start(run_id="r1", trace_id="t1")
        assert ref.category == "spine.kernel.run.start"
        ref = plugin.emit_kernel_run_stop(run_id="r1", outcome="success")
        assert ref.category == "spine.kernel.run.stop"
        ref = plugin.emit_kernel_run_cancelled(run_id="r1")
        assert ref.category == "spine.kernel.run.cancelled"
    finally:
        EventMechanism.set_default(None)


def test_unauthorized_publisher_rejected(mechanism: EventMechanism) -> None:
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        mechanism.send(
            SpineEventPayload(
                execution_point="transport.route.enter",
                channel="control",
                payload={"path": "/x", "method": "GET", "run_id": "r1"},
            ),
            plugin=NotInWhitelist,
        )
