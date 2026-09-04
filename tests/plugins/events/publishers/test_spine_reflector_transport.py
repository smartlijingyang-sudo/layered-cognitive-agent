"""spine_reflector_transport publisher 端到端测试（ADR-0181 PR-4）。

transport / kernel.run 全部 6 emit（route.enter / .exit / sse.publish +
kernel.run.start / .stop / .cancelled）在 EventBus 路径下能正常 publish +
鉴权通过。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.bus import EventBus


def test_emit_transport_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_transport import (
        plugin,
    )

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


def test_unauthorized_publisher_rejected(bus: EventBus) -> None:
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineEventPayload(
                execution_point="transport.route.enter",
                channel="control",
                payload={"path": "/x", "method": "GET", "run_id": "r1"},
            ),
            producer=NotInWhitelist,
        )
