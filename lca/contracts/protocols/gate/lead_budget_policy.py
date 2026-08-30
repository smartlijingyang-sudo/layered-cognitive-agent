"""Lead 预算策略的组合期解析接缝。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.gate.budget_policy import BudgetPolicy


@runtime_checkable
class LeadBudgetPolicyResolver(Protocol):
    """解析当前 profile 为 Lead 声明的预算策略。

    计划绑定代理只消费这个窄接口。策略的发现、选择与具体注册方式由
    profile-owned adapter 负责，避免将 ComponentRegistry 分类和名称泄漏到
    Agent 装配路径。
    """

    def resolve_policy(self) -> BudgetPolicy: ...


__all__ = ["LeadBudgetPolicyResolver"]
