"""ADR-0256 §8:审批挂在 namespace 级.

全部 skip:DeferPolicy.namespace_approval 尚未实现.
去掉 skip 即验收 —— 新工具进入 shell 域自动继承 REQUIRE_APPROVAL,
无需逐个配置,这就是"审批边界与 namespace 同粒度"的价值.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="ADR-0256 §8 未落地:DeferPolicy.namespace_approval 不存在")
def test_d1_shell_namespace_requires_approval():
    """shell 域的 runCommand 触发用户审批(验收 5).

    动因:run_56ee6564e3ea 里截断的残缺命令被直接执行.
    """
    from lca.infrastructure.tool_defer.policy import DeferPolicy

    policy = DeferPolicy(namespace_approval={"shell": "require_approval"})
    # 意向 API,落地时对齐命名:
    assert policy.approval_for("shell") == "require_approval"


@pytest.mark.skip(reason="ADR-0256 §8 未落地:DeferPolicy.namespace_approval 不存在")
def test_d2_file_namespace_is_auto_by_default():
    """file 域默认 AUTO:writeFile 不触发审批直接执行."""
    from lca.infrastructure.tool_defer.policy import DeferPolicy

    policy = DeferPolicy(namespace_approval={"shell": "require_approval"})
    assert policy.approval_for("file") == "auto"


@pytest.mark.skip(reason="ADR-0256 §8 未落地:DeferPolicy.namespace_approval 不存在")
def test_d3_new_tool_in_shell_inherits_approval():
    """新工具进入 shell 域自动继承 REQUIRE_APPROVAL,无需逐个列名."""
    from lca.infrastructure.tool_defer.policy import DeferPolicy

    policy = DeferPolicy(namespace_approval={"shell": "require_approval"})
    # 注册一个全新的 shell 工具,审批策略按域解析,不按工具名:
    assert policy.approval_for("shell") == "require_approval"
