"""spine_reflector_kernel_loop publisher 端到端测试（ADR-0181 PR-4）。

kernel.boot + loop.fork 全部 3 emit 在 EventBus 路径下能正常 publish +
鉴权通过。
"""

from __future__ import annotations

from typing import Any


def test_emit_kernel_loop_all(bound_session: Any) -> None:
    from lca.plugins.events.publishers.spine_reflector_kernel_loop import (
        plugin,
    )

    ref = plugin.emit_kernel_boot_start(profile="web-standard")
    assert ref.category == "spine.kernel.boot.start"
    ref = plugin.emit_kernel_boot_completed(profile="web-standard")
    assert ref.category == "spine.kernel.boot.completed"
    ref = plugin.emit_loop_fork(child_role="writer", parent_step=1)
    assert ref.category == "spine.loop.fork"
