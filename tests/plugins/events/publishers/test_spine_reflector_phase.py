"""spine_reflector_phase publisher 端到端测试（ADR-0181 PR-5）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def mechanism() -> EventMechanism:
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventMechanism(EventRegistry.load(config_dir))


def test_emit_phase_all(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_phase import (
        plugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = plugin.emit_perceive_phase_fold(step=1, run_id="r1")
        assert ref.category == "spine.perceive.phase.fold"
        ref = plugin.emit_phase_perceive_fold(step=1, run_id="r1")
        assert ref.category == "spine.phase.perceive.fold"
        ref = plugin.emit_phase_think_fold(step=1, run_id="r1", decision_path="p1")
        assert ref.category == "spine.phase.think.fold"
        ref = plugin.emit_phase_gate_fold(step=1, run_id="r1", verdict="allow")
        assert ref.category == "spine.phase.gate.fold"
        ref = plugin.emit_phase_remember_fold(step=1, run_id="r1")
        assert ref.category == "spine.phase.remember.fold"
        ref = plugin.emit_phase_stop_fold(step=1, run_id="r1", outcome="success")
        assert ref.category == "spine.phase.stop.fold"
        ref = plugin.emit_phase_reflect_fold(step=1, run_id="r1", lessons=0)
        assert ref.category == "spine.phase.reflect.fold"
        ref = plugin.emit_phase_act_fold_start(step=1, run_id="r1", tool_name="search")
        assert ref.category == "spine.phase.act.fold.start"
        ref = plugin.emit_phase_act_fold_end(step=1, run_id="r1", tool_name="search", outcome="success")
        assert ref.category == "spine.phase.act.fold.end"
        ref = plugin.emit_phase_act_fold(step=1, run_id="r1", tool_name="search", outcome="success")
        assert ref.category == "spine.phase.act.fold"
        ref = plugin.emit_phase_tool_call_start(step=1, run_id="r1", tool_name="search", invocation_id="i1")
        assert ref.category == "spine.phase.tool.call.start"
        ref = plugin.emit_phase_tool_call_end(step=1, run_id="r1", tool_name="search", invocation_id="i1", outcome="success")
        assert ref.category == "spine.phase.tool.call.end"
        ref = plugin.emit_phase_tool_denied(step=1, run_id="r1", tool_name="search", reason="denied")
        assert ref.category == "spine.phase.tool.denied"
    finally:
        EventMechanism.set_default(None)
