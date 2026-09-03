"""Critic —— 事后自省与纠偏。"""

from __future__ import annotations

from typing import Any

from lca.cognition._spine_envelope import with_spine_envelope
from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
)
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Critic

_FAILURE_KIND_HINT: dict[str, str] = {
    FAILURE_KIND_VALIDATION: "参数不合法，请重复同一动作，须修正参数后重新调用",
    FAILURE_KIND_EXECUTION: "工具执行失败",
    FAILURE_KIND_TRANSIENT: "瞬时性错误，可重试",
}


class SimpleCritic(Critic):
    """基于执行结果生成反思。"""

    @with_spine_envelope("critic_eval", state_id_arg="state")
    async def critique(self, state: AgentState, observation: Observation) -> Reflection:
        # R3: spine envelope (start/end) lives in the decorator.
        return self._evaluate(state, observation)

    def _evaluate(self, state: AgentState, observation: Observation) -> Reflection:
        if observation.success:
            tool_name = self._last_tool_name(state)
            if tool_name:
                lesson = f"{tool_name} 执行成功"
            elif observation.payload is not None:
                lesson = f"步骤{state.step}成功完成"
            else:
                lesson = None
            return Reflection(
                reflection_id=new_id("refl"),
                verdict=ReflectionVerdict.ON_TRACK,
                lesson=lesson,
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
    def _last_tool_name(state: AgentState) -> str | None:
        if not state.history:
            return None
        last_decision = state.history[-1].decision
        if last_decision.tool_calls:
            return last_decision.tool_calls[0].tool_name
        return None

    @staticmethod
    def _extract_failure_kind(observation: Observation) -> str:
        kind: Any = observation.extra.get(FAILURE_KIND)
        if isinstance(kind, str) and kind in _FAILURE_KIND_HINT:
            return kind
        return FAILURE_KIND_EXECUTION
