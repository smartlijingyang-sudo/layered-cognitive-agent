"""spine_reflector_phase publisher 端到端测试（ADR-0181 PR-5 / ADR-0194 P2-12）。"""

from __future__ import annotations

from lca.loop.fact_gateway import reset_fact_gateway_env
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def test_emit_phase_all() -> None:
    from lca.plugins.events.publishers.spine_reflector_phase import plugin

    session = Session("phase-reflector")
    token = set_publish_session(session)
    reset_fact_gateway_env(enabled=True)
    try:
        plugin.emit_perceive_phase_fold(step=1, run_id="r1")
        plugin.emit_phase_perceive_fold(step=1, run_id="r1")
        plugin.emit_phase_think_fold(step=1, run_id="r1", decision_path="p1")
        plugin.emit_phase_remember_fold(step=1, run_id="r1")
        plugin.emit_phase_stop_fold(step=1, run_id="r1", outcome="success")
        plugin.emit_phase_reflect_fold(step=1, run_id="r1", lessons=0)
        plugin.emit_phase_act_fold_start(step=1, run_id="r1", tool_name="search")
        plugin.emit_phase_act_fold_end(
            step=1, run_id="r1", tool_name="search", outcome="success"
        )
        plugin.emit_phase_act_fold(step=1, run_id="r1", tool_name="search", outcome="success")
        plugin.emit_phase_tool_call_start(
            step=1, run_id="r1", tool_name="search", invocation_id="i1"
        )
        plugin.emit_phase_tool_call_end(
            step=1, run_id="r1", tool_name="search", invocation_id="i1", outcome="success"
        )
        plugin.emit_phase_tool_denied(step=1, run_id="r1", tool_name="search", reason="denied")

        types = {event.type for event in session.snapshot_events()}
        assert types >= {
            "spine.perceive.phase.fold",
            "spine.phase.perceive.fold",
            "spine.phase.think.fold",
            "spine.phase.remember.fold",
            "spine.phase.stop.fold",
            "spine.phase.reflect.fold",
            "spine.phase.act.fold.start",
            "spine.phase.act.fold.end",
            "spine.phase.act.fold",
            "spine.phase.tool.call.start",
            "spine.phase.tool.call.end",
            "spine.phase.tool.denied",
        }
    finally:
        reset_fact_gateway_env()
        reset_publish_session(token)
