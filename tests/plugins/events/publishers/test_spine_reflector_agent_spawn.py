"""spine_reflector_agent_spawn publisher 端到端测试（ADR-0181 PR-4）。

agent_loop + agent 全部 5 emit 在 Session 路径下能正常 publish +
鉴权通过。
"""

from __future__ import annotations

from typing import Any


def test_emit_agent_spawn_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_agent_spawn import (
        plugin,
    )

    ref = plugin.emit_agent_loop_iteration_start(
        trace_id="t1", role="researcher", iteration_kind="fresh"
    )
    assert ref.category == "spine.agent_loop.iteration.start"
    ref = plugin.emit_agent_loop_iteration_end(
        trace_id="t1", role="researcher", iteration_kind="fresh", outcome="success"
    )
    assert ref.category == "spine.agent_loop.iteration.end"
    ref = plugin.emit_agent_spawn(trace_id="t1", role="researcher", agent_id="a1")
    assert ref.category == "spine.agent.spawn"
    ref = plugin.emit_agent_iteration(trace_id="t1", role="researcher", agent_id="a1", iteration=1)
    assert ref.category == "spine.agent.iteration"
    ref = plugin.emit_agent_final(
        trace_id="t1", role="researcher", agent_id="a1", outcome="success"
    )
    assert ref.category == "spine.agent.final"
