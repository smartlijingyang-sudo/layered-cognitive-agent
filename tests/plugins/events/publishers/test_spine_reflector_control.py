"""spine_reflector_control publisher 端到端测试（ADR-0181 PR-6）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventBus(EventRegistry.load(config_dir))


def test_emit_control_all(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_control import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
        ref = plugin.emit_control_dispatch(run_id="r1", target="t", intent="i")
        assert ref.category == "spine.control.dispatch"
        ref = plugin.emit_control_invoke(run_id="r1", target="t", args={"a": 1})
        assert ref.category == "spine.control.invoke"
        ref = plugin.emit_control_signal(run_id="r1", name="n", payload={"p": 1})
        assert ref.category == "spine.control.signal"
        ref = plugin.emit_control_approve_request(run_id="r1", request_id="q", intent="i")
        assert ref.category == "spine.control.approve.request"
        ref = plugin.emit_control_approve_response(run_id="r1", request_id="q", verdict="ok", actor="me")
        assert ref.category == "spine.control.approve.response"
        ref = plugin.emit_control_deny(run_id="r1", request_id="q", reason="r")
        assert ref.category == "spine.control.deny"
        ref = plugin.emit_control_revoke(run_id="r1", target="t")
        assert ref.category == "spine.control.revoke"
        ref = plugin.emit_control_pause(run_id="r1", reason="r")
        assert ref.category == "spine.control.pause"
        ref = plugin.emit_control_resume(run_id="r1")
        assert ref.category == "spine.control.resume"
        ref = plugin.emit_control_stop(run_id="r1")
        assert ref.category == "spine.control.stop"
        ref = plugin.emit_control_accept(run_id="r1", request_id="q")
        assert ref.category == "spine.control.accept"
    finally:
        EventBus.set_default(None)
