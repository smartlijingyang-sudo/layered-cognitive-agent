"""L1 Body / 行动执行协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.state import AgentState


@runtime_checkable
class Body(Protocol):
    """行动执行体：将 Decision 转化为 Observation。

    契约不变量：只分发已注册词表内的 ``action_type``。
    词表外的决策必须在防腐层（``DegradationPolicy``）完成改写，
    到达 Body 时仍是越界 action_type 属于契约违例。
    """

    async def act(self, decision: Decision, state: AgentState) -> Observation: ...
