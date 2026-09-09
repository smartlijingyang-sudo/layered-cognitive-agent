"""Critic —— 事后自省与纠偏。"""

from __future__ import annotations

from typing import Any

from lca.cognition.convergence.payload import payload_stdout
from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.cli_diagnostic import is_cli_diagnostic_output
from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
    OBS_TOOL_RESULTS,
)
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import Critic
from lca.infrastructure.session.commit.spine_envelope import with_spine_envelope

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
        partial = self._partial_batch_reflection(observation)
        if partial is not None:
            return partial
        if observation.success:
            if is_cli_diagnostic_output(payload_stdout(observation.payload)):
                return Reflection(
                    reflection_id=new_id("refl"),
                    verdict=ReflectionVerdict.NEEDS_CORRECTION,
                    lesson=f"步骤{state.step}失败(命令被拒绝或输出了 CLI 帮助文本，请修正子命令/参数)",
                    extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
                )
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
    def _partial_batch_reflection(observation: Observation) -> Reflection | None:
        """Parallel batch: partial success must not collapse to step-wide failure."""
        if observation.success:
            return None
        extra = observation.extra if isinstance(observation.extra, dict) else {}
        raw = extra.get(OBS_TOOL_RESULTS)
        if not isinstance(raw, list) or not raw:
            return None
        ok_names: list[str] = []
        fail_names: list[str] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("tool_name") or "tool")
            nested = entry.get("observation")
            if isinstance(nested, Observation) and nested.success:
                ok_names.append(name)
            elif isinstance(nested, Observation):
                fail_names.append(name)
        if not ok_names or not fail_names:
            return None
        lesson = (
            f"部分工具成功({', '.join(ok_names)}); "
            f"失败({', '.join(fail_names)}): {observation.error or 'see tool results'}"
        )
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=lesson,
            extra={FAILURE_KIND: FAILURE_KIND_EXECUTION},
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
