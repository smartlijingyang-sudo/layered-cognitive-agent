"""Critic —— 事后自省与纠偏。"""

from __future__ import annotations

import uuid

from contracts.state import TypedState
from contracts.decision import Observation, Reflection
from contracts.protocols import Critic


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleCritic(Critic):
    """基于执行结果生成反思。"""

    async def critique(self, state: TypedState, observation: Observation) -> Reflection:
        if observation.success:
            return Reflection(
                reflection_id=_new_id("refl"),
                verdict="on_track",
                lesson=f"步骤{state.step}成功完成" if observation.payload is not None else None,
            )
        return Reflection(
            reflection_id=_new_id("refl"),
            verdict="needs_correction",
            lesson=f"步骤{state.step}失败: {observation.error}",
        )
