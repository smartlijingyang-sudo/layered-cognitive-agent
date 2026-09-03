"""spine_reflector_runtime publisher 端到端测试（ADR-0181 PR-3）。

旧 runtime reflector 全部 8 emit（exception.caught + exception.finally +
lifecycle.finally + runtime.reducer.apply/start + checkpoint.create +
resume.start/end + event_publisher.publish）在 EventMechanism 路径下能正常
send + 鉴权通过。
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


def _run(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_runtime import (
        plugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        # exception
        ref = plugin.emit_exception_caught(
            boundary="resume", exc_type="ValueError", message="boom", trace_id="t1"
        )
        assert ref.category == "spine.exception.caught"
        ref = plugin.emit_exception_finally(boundary="resume", trace_id="t1")
        assert ref.category == "spine.exception.finally"
        ref = plugin.emit_lifecycle_finally(boundary="resume", trace_id="t1")
        assert ref.category == "spine.lifecycle.finally"
        # runtime.observed
        ref = plugin.emit_runtime_reducer_apply_start(method="apply_x", run_id="r1")
        assert ref.category == "spine.runtime.reducer.apply"
        ref = plugin.emit_runtime_reducer_apply_end(method="apply_x", outcome="success")
        assert ref.category == "spine.runtime.reducer.apply"
        ref = plugin.emit_runtime_checkpoint_create(
            plan_ref="p1", state_ref="s1", node_id="n1"
        )
        assert ref.category == "spine.runtime.checkpoint.create"
        ref = plugin.emit_runtime_resume_start(plan_ref="p1", state_ref="s1", node_id="n1")
        assert ref.category == "spine.runtime.resume.start"
        ref = plugin.emit_runtime_resume_end(
            plan_ref="p1", state_ref="s1", node_id="n1", outcome="success"
        )
        assert ref.category == "spine.runtime.resume.end"
        ref = plugin.emit_runtime_event_publisher_publish(
            event_type="TURN_STARTED", trace_id="t1"
        )
        assert ref.category == "spine.runtime.event_publisher.publish"
        # PR-6 runtime.observed marker
        ref = plugin.emit_runtime_observed(
            observed_at="checkpoint_persist", detail="x", run_id="r1"
        )
        assert ref.category == "spine.runtime.observed"
    finally:
        EventMechanism.set_default(None)


def test_emit_runtime_all(mechanism: EventMechanism) -> None:
    _run(mechanism)


def test_unauthorized_publisher_rejected(mechanism: EventMechanism) -> None:
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    with pytest.raises(UnauthorizedPublishError):
        mechanism.send(
            SpineEventPayload(
                execution_point="exception.caught",
                channel="error",
                payload={"boundary": "x", "exc_type": "y", "message": "z", "trace_id": "t"},
            ),
            plugin=NotInWhitelist,
        )
