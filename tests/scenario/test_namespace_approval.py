"""ADR-0256 §8:审批挂在 namespace 级.

skip 已于 2026-10-02 解除:DeferPolicy.namespace_approval 已落地
(DEFAULT_NAMESPACE_APPROVAL={"shell": "require_approval"}),
消费侧 NamespaceApprovalStrategy.evaluate() 按工具 namespace 查规则,
不再按工具名单逐个配置 —— 这就是"审批边界与 namespace 同粒度"的价值.
"""
from __future__ import annotations

from lca.contracts.models.core.execution.approval import ApprovalRequirement
from lca.contracts.models.core.execution.decision import ToolCall
from lca.infrastructure.runtime_plane.access.approval_engine import (
    NamespaceApprovalStrategy,
)
from lca.infrastructure.tool_defer.policy import (
    DEFAULT_NAMESPACE_APPROVAL,
    DeferPolicy,
)


def _call(name: str) -> ToolCall:
    return ToolCall(call_id="c1", tool_name=name, arguments={})


def test_d1_shell_namespace_requires_approval():
    """shell 域的 runCommand 触发用户审批(验收 5).

    动因:run_56ee6564e3ea 里截断的残缺命令被直接执行.
    """
    assert DEFAULT_NAMESPACE_APPROVAL["shell"] == "require_approval"
    assert DeferPolicy().namespace_approval["shell"] == "require_approval"
    strategy = NamespaceApprovalStrategy(approval_mapping={"shell": "require_approval"})
    req = strategy.evaluate([_call("runCommand")])
    assert isinstance(req, ApprovalRequirement) and req.required
    assert req.details["namespace"] == "shell"


def test_d2_file_namespace_is_auto_by_default():
    """file 域默认无审批:writeFile 不触发审批直接执行."""
    strategy = NamespaceApprovalStrategy(approval_mapping={"shell": "require_approval"})
    assert strategy.evaluate([_call("writeFile")]) is None


def test_d3_new_tool_in_shell_inherits_approval():
    """新工具进入 shell 域自动继承 REQUIRE_APPROVAL,无需逐个列名."""
    strategy = NamespaceApprovalStrategy(
        tool_namespaces={"myNewShellTool": "shell"},
        approval_mapping={"shell": "require_approval"},
    )
    req = strategy.evaluate([_call("myNewShellTool")])
    assert req is not None and req.required
    assert req.details["namespace"] == "shell"
