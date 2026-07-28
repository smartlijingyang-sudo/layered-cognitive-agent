"""Critic —— 事后自省与纠偏。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.decision import Observation, Reflection
from lca.contracts.protocols import Critic
from lca.contracts.state import TypedState


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


_FAILURE_KIND_HINT: dict[str, str] = {
    "validation": "参数不合法，请重复同一动作，须修正参数后重新调用",
    "execution": "工具执行失败",
    "transient": "瞬时性错误，可重试",
}


class SimpleCritic(Critic):
    """基于执行结果生成反思。"""

    async def critique(self, state: TypedState, observation: Observation) -> Reflection:
        if observation.success:
            return Reflection(
                reflection_id=_new_id("refl"),
                verdict="on_track",
                lesson=f"步骤{state.step}成功完成" if observation.payload is not None else None,
            )
        failure_kind = self._extract_failure_kind(observation)
        hint = _FAILURE_KIND_HINT.get(failure_kind, "步骤失败")
        lesson = f"步骤{state.step}失败({hint}): {observation.error}"
        return Reflection(
            reflection_id=_new_id("refl"),
            verdict="needs_correction",
            lesson=lesson,
            extra={"failure_kind": failure_kind},
        )

    @staticmethod
    def _extract_failure_kind(observation: Observation) -> str:
        kind: Any = observation.extra.get("failure_kind")
        if isinstance(kind, str) and kind in _FAILURE_KIND_HINT:
            return kind
        return "execution"
