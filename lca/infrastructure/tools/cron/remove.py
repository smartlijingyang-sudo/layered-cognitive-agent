"""``cron.remove`` 工具（ADR-0268 §4、§9）。

模型路径删除挂起：本工具绝不调用写函数，实际删除由卡片路径 HTTP
DELETE 完成。
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from lca.contracts.models.core.execution.decision import Observation
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.common import (
    CRON_NAMESPACE,
    _error,
)


class CronRemoveTool:
    """``cron.remove``：模型路径删除挂起，不调用写函数（ADR-0268 §9）。"""

    name: ClassVar[str] = "cron.remove"
    namespace: ClassVar[str] = CRON_NAMESPACE
    description: ClassVar[str] = (
        "删除一条 cron 任务定义与尚未注入的 handoff。该调用会挂起等待"
        "用户批准，批准回注后才删除。已结束的 run 记录不删除。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "要删除的任务 id。"}},
        "required": ["id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, *, service: CronService, owner: str) -> None:
        del owner
        self._service = service

    def validate(self, args: dict[str, Any]) -> str | None:
        if not isinstance(args.get("id"), str) or not args["id"].strip():
            return "'id' is required"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        error = self.validate(args)
        if error is not None:
            return _error(error)
        job_id = args["id"].strip()
        if self._service.get_job(job_id) is None:
            return _error(f"cron job {job_id!r} not found")
        return _error(
            "需要审批：cron.remove 写操作挂起，等待用户批准",
            extra={
                "approval_request": {
                    "type": "cron_remove",
                    "job_id": job_id,
                }
            },
        )
