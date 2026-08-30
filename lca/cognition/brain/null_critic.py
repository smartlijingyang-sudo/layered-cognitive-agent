"""NullCritic —— 宪法 §3.4 默认 no-op（ADR-0068）。

``NullCritic.critique`` 返回 ``Reflection(verdict=ON_TRACK, lesson=None)``。
不读 observation、不写 lesson、不发事件。Profile 不挂 standard-think bundle
时默认装载此实现。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ReflectionVerdict
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Critic


class NullCritic(Critic):
    """Default null Critic (ADR-0068 / 宪法 §3.4)."""

    async def critique(self, state: AgentState, observation: Observation) -> Reflection:
        return Reflection(
            reflection_id=new_id("refl"),
            verdict=ReflectionVerdict.ON_TRACK,
            lesson=None,
        )


__all__ = ["NullCritic"]
