"""cron 命名空间工具（ADR-0268 §4、§5、§9、§10）。

``cron.add`` 直接写入；``cron.view`` / ``cron.list`` 只读；``cron.update``
/ ``cron.remove`` 是模型发起的写操作，由 ``CronMutationApprovalStrategy``
使 ``Decision.needs_approval`` 为 True，``act.approve.gate`` 在工具执行前
挂起（ADR-0268 §2.1、§9）。本包里的 ``cron.update`` / ``cron.remove``
实现因此绝不调用写函数，实际写由卡片路径 HTTP PUT/DELETE 完成。
"""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.add import CronAddTool
from lca.infrastructure.tools.cron.list import CronListTool
from lca.infrastructure.tools.cron.remove import CronRemoveTool
from lca.infrastructure.tools.cron.update import CronUpdateTool
from lca.infrastructure.tools.cron.view import CronViewTool

__all__ = [
    "CronAddTool",
    "CronListTool",
    "CronRemoveTool",
    "CronUpdateTool",
    "CronViewTool",
    "build_cron_tools",
]


def build_cron_tools(*, service: CronService, owner: str) -> list[Tool]:
    """构造 ``cron`` 命名空间下的五个工具（ADR-0268 §4）。"""
    return [
        CronAddTool(service=service, owner=owner),
        CronViewTool(service=service, owner=owner),
        CronListTool(service=service, owner=owner),
        CronUpdateTool(service=service, owner=owner),
        CronRemoveTool(service=service, owner=owner),
    ]
