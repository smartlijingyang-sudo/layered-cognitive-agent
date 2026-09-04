"""spine_reflector_writable publisher 端到端测试（ADR-0181 PR-5）。"""

from __future__ import annotations

from typing import Any


def test_emit_writable_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_writable import (
        plugin,
    )

    ref = plugin.emit_writable_step_start(step=1, run_id="r1")
    assert ref.category == "spine.writable.step.start"
    ref = plugin.emit_writable_step_end(step=1, run_id="r1")
    assert ref.category == "spine.writable.step.end"
    ref = plugin.emit_writable_segment_start(segment=0, step=1, run_id="r1")
    assert ref.category == "spine.writable.segment.start"
    ref = plugin.emit_writable_segment_end(segment=0, step=1, run_id="r1")
    assert ref.category == "spine.writable.segment.end"
    ref = plugin.emit_writable_iteration_halt(run_id="r1", reason="cancel")
    assert ref.category == "spine.writable.iteration.halt"
    ref = plugin.emit_writable_iteration_closing(run_id="r1")
    assert ref.category == "spine.writable.iteration.closing"
    ref = plugin.emit_writable_iteration_close(run_id="r1")
    assert ref.category == "spine.writable.iteration.close"
