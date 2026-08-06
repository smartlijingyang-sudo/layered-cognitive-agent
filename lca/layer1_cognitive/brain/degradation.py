"""GracefulDegradation —— 越界 action_type 的归一化策略。

L1 防腐层职责：
    LLM "发明"词表外的 action_type 是常态而非异常。本策略按
    "决策携带了什么内容"把越界决策改写为词表内的等价行动，
    并通过 ``Decision.degraded_from`` 记录降级轨迹。
    降级在执行前完成——Body 永远只见词表内的 action_type。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import ClassVar

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.protocols import DegradationPolicy
from lca.contracts.protocols.action import ActionRegistryProtocol


def _carries_response(decision: Decision) -> bool:
    return bool(decision.response_text)


def _carries_tool_calls(decision: Decision) -> bool:
    return bool(decision.tool_calls)


class GracefulDegradation(DegradationPolicy):
    """按内容优先级把越界 action_type 改写为词表内的等价行动。

    优先级是声明式表——扩展降级路径只需增加一行，不改动分发逻辑：

    1. 携带 response_text → respond
    2. 携带 tool_calls    → use_tool

    所有候选目标均未注册、或决策无任何可承载内容时原样返回，
    交由 Body 以 ``UnregisteredActionError`` 明确拒绝。
    """

    _PRIORITY: ClassVar[tuple[tuple[ActionType, Callable[[Decision], bool]], ...]] = (
        (ActionType.RESPOND, _carries_response),
        (ActionType.USE_TOOL, _carries_tool_calls),
    )

    def degrade(self, decision: Decision, action_registry: ActionRegistryProtocol) -> Decision:
        for target, carries_content in self._PRIORITY:
            if carries_content(decision) and action_registry.is_registered(target):
                return replace(
                    decision,
                    action_type=target,
                    degraded_from=decision.action_type,
                    extra=dict(decision.extra),
                )
        return decision
