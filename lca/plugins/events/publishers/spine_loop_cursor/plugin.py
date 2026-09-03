"""spine_loop_cursor plugin（ADR-0181 PR-10）。

# COMPAT(delete-when: cursor 完全切到 EventMechanism, tracking: ADR-0169)
# cursor phase.fold / step.record_* / writable.iteration.* EP 都从此
# EventMechanism 入口走；旧 self._spine.append 路径在 cursor worktree
# 改造 PR 中被替身（PR-10 仅引入入口骨架，不动 cursor 内部）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.mechanism import EventRef

log = logging.getLogger(__name__)


class LoopCursorPlugin:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""

    @staticmethod
    def send(
        *,
        execution_point: str,
        channel: str,
        payload: dict[str, Any],
    ) -> EventRef:
        """cursor 一行 EventMechanism 入口（PR-10 旧 _spine.append 替身）。"""
        from lca_kernel.events.mechanism import EventMechanism

        cat_str = _SPINE_EP_TO_CATEGORY.get(execution_point)
        if cat_str is None:
            raise ValueError(
                f"spine EP {execution_point!r} 未登记 category 映射（PR-10 cursor 切"
                " EventMechanism 时一并登记）"
            )
        sp = SpineEventPayload(
            category=Category(cat_str),
            execution_point=execution_point,
            channel=channel,
            payload=payload,
        )
        return EventMechanism.default().send(sp, plugin=LoopCursorPlugin)


__all__ = ["LoopCursorPlugin"]
