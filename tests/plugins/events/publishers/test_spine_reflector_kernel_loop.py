"""spine_reflector_kernel_loop publisher 端到端测试（ADR-0181 PR-4）。

kernel.boot + loop.fork 全部 3 emit 在 EventMechanism 路径下能正常 send +
鉴权通过。
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


def test_emit_kernel_loop_all(mechanism: EventMechanism) -> None:
    from lca.plugins.events.publishers.spine_reflector_kernel_loop import (
        plugin,
    )

    EventMechanism.set_default(mechanism)
    try:
        ref = plugin.emit_kernel_boot_start(profile="web-standard")
        assert ref.category == "spine.kernel.boot.start"
        ref = plugin.emit_kernel_boot_completed(profile="web-standard")
        assert ref.category == "spine.kernel.boot.completed"
        ref = plugin.emit_loop_fork(child_role="writer", parent_step=1)
        assert ref.category == "spine.loop.fork"
    finally:
        EventMechanism.set_default(None)
