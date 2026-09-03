"""spine_reflector_cognition plugin（ADR-0181 试点 1 个 EP）。

迁移自 ``lca/plugins/observability/spine/reflectors/cognition.py`` 的
``emit_brain_perceive_start``。其余 39 emit 留给 PR-2（按 0181 §迁移 PR 切分）。
"""
from __future__ import annotations

import logging
from typing import Any

from lca_kernel.events.mechanism import EventMechanism
from lca_kernel.events.payloads import SpineEventPayload

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def emit_brain_perceive_start(*, state_id: str) -> Any:
    """试点 EP：spine.cognition.brain.perceive.start。

    业务方一行调：EventMechanism.send(SpineEventPayload(...), plugin=ReflectorClass)。
    返回 EventRef（机制填充），调用方可忽略。
    """
    payload = SpineEventPayload(
        execution_point="brain.perceive.start",
        channel="fact",
        payload={"state_id": state_id},
    )
    return EventMechanism.default().send(payload, plugin=ReflectorClass)


__all__ = ["ReflectorClass", "emit_brain_perceive_start"]
