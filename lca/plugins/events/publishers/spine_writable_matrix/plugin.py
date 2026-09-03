"""spine_writable_matrix plugin（ADR-0181 PR-10）。

# COMPAT(delete-when: cursor 完全切到 EventMechanism, tracking: ADR-0181)
# cursor 旧 self._spine.append(execution_point=..., payload=...) 路径仍
# 是 EventSpine 接口。PR-10 提供 EventMechanism 入口骨架；cursor 改造
# 在 spine-writable-matrix worktree 中分批做（cursor 内部 5+ 处 append
# 需逐个适配；本 PR 不动 cursor 内部代码）。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.mechanism import EventRef

log = logging.getLogger(__name__)


class WritableMatrixPlugin:
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
        return EventMechanism.default().send(sp, plugin=WritableMatrixPlugin)


__all__ = ["WritableMatrixPlugin"]
