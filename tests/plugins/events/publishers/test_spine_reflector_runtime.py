"""spine_reflector_runtime publisher 端到端测试（ADR-0181 PR-3 / ADR-0183 PR-7）。

Runtime envelope emits（exception.finally + lifecycle.finally +
runtime.reducer.apply/start + checkpoint.create + resume.start/end +
event_publisher.publish + runtime.observed）在 EventBus 路径下能正常
publish + 鉴权通过。``exception.caught`` 不在本 plugin 的 helper 面。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.bus import EventBus


def _run() -> None:
    from lca.plugins.events.publishers.spine_reflector_runtime import (
        plugin,
    )

    # exception envelope (caught is observability SSOT, not this plugin)
    assert not hasattr(plugin, "emit_exception_caught")
    ref = plugin.emit_exception_finally(boundary="resume", trace_id="t1")
    assert ref.category == "spine.exception.finally"
    ref = plugin.emit_lifecycle_finally(boundary="resume", trace_id="t1")
    assert ref.category == "spine.lifecycle.finally"
    # runtime.observed
    ref = plugin.emit_runtime_reducer_apply_start(method="apply_x", run_id="r1")
    assert ref.category == "spine.runtime.reducer.apply"
    ref = plugin.emit_runtime_reducer_apply_end(method="apply_x", outcome="success")
    assert ref.category == "spine.runtime.reducer.apply"
    ref = plugin.emit_runtime_checkpoint_create(plan_ref="p1", state_ref="s1", node_id="n1")
    assert ref.category == "spine.runtime.checkpoint.create"
    ref = plugin.emit_runtime_resume_start(plan_ref="p1", state_ref="s1", node_id="n1")
    assert ref.category == "spine.runtime.resume.start"
    ref = plugin.emit_runtime_resume_end(
        plan_ref="p1", state_ref="s1", node_id="n1", outcome="success"
    )
    assert ref.category == "spine.runtime.resume.end"
    ref = plugin.emit_runtime_event_publisher_publish(event_type="TURN_STARTED", trace_id="t1")
    assert ref.category == "spine.runtime.event_publisher.publish"
    # PR-6 runtime.observed marker
    ref = plugin.emit_runtime_observed(observed_at="checkpoint_persist", detail="x", run_id="r1")
    assert ref.category == "spine.runtime.observed"


def test_emit_runtime_all(bound_session: Any) -> None:
    _run()


def test_unauthorized_publisher_rejected(bus: EventBus) -> None:
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        bus.publish(
            SpineEventPayload(
                execution_point="exception.caught",
                channel="error",
                payload={"boundary": "x", "exc_type": "y", "message": "z", "trace_id": "t"},
            ),
            producer=NotInWhitelist,
        )
