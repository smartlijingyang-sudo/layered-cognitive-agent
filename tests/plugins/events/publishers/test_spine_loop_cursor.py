"""spine_loop_cursor publisher 端到端测试（ADR-0181 PR-10）。"""

from __future__ import annotations

from typing import Any


def test_loop_cursor_send(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_loop_cursor.plugin import (
        LoopCursorPlugin,
    )

    ref = LoopCursorPlugin.send(
        execution_point="phase.think.fold",
        channel="fact",
        payload={"step": 1, "run_id": "r1"},
    )
    assert ref.category == "spine.phase.think.fold"
