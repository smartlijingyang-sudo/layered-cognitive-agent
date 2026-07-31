"""DelegationTool —— 把团队成员包装为标准 Tool，实现 delegation-as-tool-call。"""

from __future__ import annotations

from typing import Any

from lca.contracts.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.run_context import RunContext
from lca.layer3_agent.simple_agent import CognitiveAgent

_DELEGATE_TIMEOUT_S = 300


class DelegationTool(Tool):
    """将一个 CognitiveAgent 成员包装为标准 Tool。

    Supervisor 的 LLM 可以像调用普通工具一样调用 ``delegate_to_<role>``,
    无需专门的 ``action_type="delegate"`` 和 Transport 路由层。
    """

    is_idempotent: bool = False
    default_timeout_s: int = _DELEGATE_TIMEOUT_S

    def __init__(self, member: CognitiveAgent, from_role: str = "") -> None:
        self._member = member
        self._from_role = from_role
        self.name = f"delegate_to_{member.role_profile.role}"

    def validate(self, args: dict[str, Any]) -> str | None:
        subtask = args.get("subtask")
        if not subtask or not isinstance(subtask, str):
            return "subtask 参数必填且必须为字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        subtask = args.get("subtask", "")
        result = await self._member.run(
            subtask,
            RunContext(from_role=self._from_role),
        )
        return Observation.from_result(result)
