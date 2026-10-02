"""``cron.update`` 工具（ADR-0268 §4、§9）。

模型路径整份覆盖语义，但写被审批门挂起：本工具绝不调用写函数，
实际写由卡片路径 HTTP PUT 完成。
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.common import (
    _CRON_JOB_PROPERTIES,
    CRON_NAMESPACE,
    _error,
)


class CronUpdateTool:
    """``cron.update``：模型路径整份覆盖，写操作挂起等审批（ADR-0268 §9）。"""

    name: ClassVar[str] = "cron.update"
    namespace: ClassVar[str] = CRON_NAMESPACE
    description: ClassVar[str] = (
        "整份覆盖一条 cron 任务定义。模型路径会先 cron.view 再覆盖；"
        "该调用会挂起等待用户批准，批准回注后才落盘。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": _CRON_JOB_PROPERTIES,
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
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error="需要审批：cron.update 写操作挂起，等待用户批准",
            extra={
                "approval_request": {
                    "type": "cron_update",
                    "job_id": job_id,
                    "requested": dict(args),
                }
            },
        )
