"""spine_reflector_runtime publisher 端到端测试（ADR-0181 PR-3 / ADR-0183 PR-7 / ADR-0194 P2-10）。

Runtime envelope emits route through ``runtime_emit.publish_ep_bound``.
``exception.caught`` 不在本 plugin 的 helper 面。
"""

from __future__ import annotations

import pytest

from lca.loop.fact_gateway import reset_fact_gateway_env
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def _run(session: Session) -> None:
    from lca.plugins.events.publishers.spine_reflector_runtime import plugin

    assert not hasattr(plugin, "emit_exception_caught")
    plugin.emit_exception_finally(boundary="resume", trace_id="t1")
    plugin.emit_lifecycle_finally(boundary="resume", trace_id="t1")
    plugin.emit_runtime_reducer_apply_start(method="apply_x", run_id="r1")
    plugin.emit_runtime_reducer_apply_end(method="apply_x", outcome="success")
    plugin.emit_runtime_checkpoint_create(plan_ref="p1", state_ref="s1", node_id="n1")
    plugin.emit_runtime_resume_start(plan_ref="p1", state_ref="s1", node_id="n1")
    plugin.emit_runtime_resume_end(
        plan_ref="p1", state_ref="s1", node_id="n1", outcome="success"
    )
    plugin.emit_runtime_event_publisher_publish(event_type="TURN_STARTED", trace_id="t1")
    plugin.emit_runtime_observed(observed_at="checkpoint_persist", detail="x", run_id="r1")

    types = {event.type for event in session.snapshot_events()}
    assert types >= {
        "spine.exception.finally",
        "spine.lifecycle.finally",
        "spine.runtime.reducer.apply",
        "spine.runtime.checkpoint.create",
        "spine.runtime.resume.start",
        "spine.runtime.resume.end",
        "spine.runtime.event_publisher.publish",
        "spine.runtime.observed",
    }


def test_emit_runtime_all() -> None:
    session = Session("runtime-reflector")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        _run(session)
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)


def test_unauthorized_publisher_rejected(bus) -> None:
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.errors import UnauthorizedPublishError
    from lca_kernel.events.payloads import SpineEventPayload

    class NotInWhitelist:
        pass

    EventBus.set_default(bus)
    try:
        with pytest.raises(UnauthorizedPublishError):
            bus.publish(
                SpineEventPayload(
                    execution_point="exception.caught",
                    channel="error",
                    payload={"boundary": "x", "exc_type": "y", "message": "z", "trace_id": "t"},
                ),
                producer=NotInWhitelist,
            )
    finally:
        EventBus.set_default(None)
