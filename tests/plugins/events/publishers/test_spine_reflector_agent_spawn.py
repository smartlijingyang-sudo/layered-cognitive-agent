"""spine_reflector_agent_spawn publisher 端到端测试（ADR-0181 PR-4）。

agent_loop + agent 全部 5 emit 在 EventBus 路径下能正常 publish +
鉴权通过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.bus import EventBus
from lca_kernel.events.registry import EventRegistry


@pytest.fixture
def bus() -> EventBus:
    """用工作区 lca_kernel/events/config 构造机制。"""
    config_dir = Path(__file__).resolve().parents[4] / "lca_kernel" / "events" / "config"
    return EventBus(EventRegistry.load(config_dir))


def test_emit_agent_spawn_all(bus: EventBus) -> None:
    from lca.plugins.events.publishers.spine_reflector_agent_spawn import (
        plugin,
    )

    EventBus.set_default(bus)
    try:
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
        ref = plugin.emit_agent_final(trace_id="t1", role="researcher", agent_id="a1", outcome="success")
        assert ref.category == "spine.agent.final"
    finally:
        EventBus.set_default(None)
