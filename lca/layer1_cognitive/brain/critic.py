"""Critic —— 事后自省与纠偏。"""

from __future__ import annotations

from typing import Any

from lca.contracts.decision import Observation, Reflection
from lca.contracts.enums import ReflectionVerdict
from lca.contracts.ids import new_id
from lca.contracts.protocols import Critic
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.state import AgentState

_FAILURE_KIND_HINT: dict[str, str] = {
    FAILURE_KIND_VALIDATION: "参数不合法，请重复同一动作，须修正参数后重新调用",
    FAILURE_KIND_EXECUTION: "工具执行失败",
    FAILURE_KIND_TRANSIENT: "瞬时性错误，可重试",
}


class SimpleCritic(Critic):
    """基于执行结果生成反思。"""

    async def critique(self, state: AgentState, observation: Observation) -> Reflection:
        if observation.success:
            return Reflection(
                reflection_id=new_id("refl"),
                verdict=ReflectionVerdict.ON_TRACK,
                lesson=f"步骤{state.step}成功完成" if observation.payload is not None else None,
            )
        failure_kind = self._extract_failure_kind(observation)
        hint = _FAILURE_KIND_HINT.get(failure_kind, "步骤失败")
        lesson = f"步骤{state.step}失败({hint}): {observation.error}"
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.NEEDS_CORRECTION,
            lesson=lesson,
            extra={FAILURE_KIND: failure_kind},
        )

    @staticmethod
    def _extract_failure_kind(observation: Observation) -> str:
        kind: Any = observation.extra.get(FAILURE_KIND)
        if isinstance(kind, str) and kind in _FAILURE_KIND_HINT:
            return kind
        return FAILURE_KIND_EXECUTION
