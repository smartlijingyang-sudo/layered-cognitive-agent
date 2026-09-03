"""spine_step_tree_accumulator plugin 实现（ADR-0181 试点 + PR-2 复审）。

试点只累积 state；完整 deriver 逻辑（含 step_tree 写 model_visible/）
按 PR-8 迁移。

PR-2 复审：用 :func:`is_spine_event` 替换散落的 ``hasattr`` 守卫。
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from lca_kernel.events.mechanism import EventRef
from lca_kernel.events.spine_runtime import is_spine_event

log = logging.getLogger(__name__)


class SpineStepTreeAccumulator:
    """subscriber plugin（FD-2 contained 由机制保证）。"""

    _state: ClassVar[list[dict[str, Any]]] = []

    @classmethod
    def reset(cls) -> None:
        cls._state = []

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """subscriber callback（FD-2：抛错被机制 try/except contained）。"""
        if not is_spine_event(payload):
            raise TypeError(
                f"SpineStepTreeAccumulator 只接 SpineEventPayload；got {type(payload).__name__}"
            )
        record = {
            "event_id": ref.event_id,
            "execution_point": payload.execution_point,
            "state_id": payload.payload.get("state_id"),
        }
        self._state.append(record)
        log.debug("step_tree.append ep=%s state_id=%s", payload.execution_point, record["state_id"])


__all__ = ["SpineStepTreeAccumulator"]
