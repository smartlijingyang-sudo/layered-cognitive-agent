"""ADR-0268 §2.1/§9/§14.1 结构保证：模型发起的 cron 写操作需要审批。

``decision_needs_approval`` 对 ``cron.update`` / ``cron.remove`` 返回
True，使 ``act.approve.gate`` 在工具执行前挂起（ADR-0228）；``cron.add``
/ ``cron.view`` / ``cron.list`` 不做结构门控。
"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.runtime_plane.access.approval_engine import (
    CronMutationApprovalStrategy,
    build_default_approval_engine,
)
from lca.infrastructure.runtime_plane.access.classify import decision_needs_approval


def _calls(*tool_names: str) -> list[ToolCall]:
    return [
        ToolCall(call_id=f"call-{i}", tool_name=name, arguments={})
        for i, name in enumerate(tool_names)
    ]


def test_cron_update_needs_approval() -> None:
    assert decision_needs_approval(_calls("cron.update")) is True


def test_cron_remove_needs_approval() -> None:
    assert decision_needs_approval(_calls("cron.remove")) is True


def test_cron_add_view_list_do_not_need_approval() -> None:
    assert decision_needs_approval(_calls("cron.add")) is False
    assert decision_needs_approval(_calls("cron.view")) is False
    assert decision_needs_approval(_calls("cron.list")) is False


def test_non_cron_tools_not_gated_by_cron_strategy() -> None:
    engine = build_default_approval_engine()
    req = engine.evaluate(_calls("cron.add"))
    assert req.required is False


def test_cron_mutation_strategy_returns_requirement() -> None:
    strategy = CronMutationApprovalStrategy()
    req = strategy.evaluate(_calls("cron.update"))
    assert req is not None
    assert req.required is True
    assert req.reason_kind.value == "policy_rule"
    assert req.target_resource == "cron.update"


def test_cron_mutation_strategy_ignores_reads() -> None:
    strategy = CronMutationApprovalStrategy()
    assert strategy.evaluate(_calls("cron.view")) is None
    assert strategy.evaluate(_calls("cron.list")) is None
