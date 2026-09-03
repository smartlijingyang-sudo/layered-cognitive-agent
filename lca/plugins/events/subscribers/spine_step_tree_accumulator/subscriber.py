"""spine_step_tree_accumulator plugin 实现（ADR-0181 试点）。

试点仅 1 个 EP（spine.cognition.brain.perceive.start）处理：累积到 step_tree。
完整 deriver 逻辑（含 step_tree_accumulator 写 model_visible/）按 PR-8 迁移。
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from lca_kernel.events.mechanism import EventRef

log = logging.getLogger(__name__)


class SpineStepTreeAccumulator:
    """subscriber plugin（FD-2 contained 由机制保证）。"""

    _state: ClassVar[list[dict[str, Any]]] = []

    @classmethod
    def reset(cls) -> None:
        cls._state = []

    def __call__(self, payload: Any, ref: EventRef) -> None:
        """subscriber callback（FD-2：抛错被机制 try/except contained）。"""
        if not hasattr(payload, "execution_point"):
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
