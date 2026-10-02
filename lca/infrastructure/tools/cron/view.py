"""``cron.view`` 工具（ADR-0268 §4）。"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.cron.models import CronRun
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.common import (
    CRON_NAMESPACE,
    _error,
    _success,
)


class CronViewTool:
    """``cron.view``：按 id 返回完整定义与只追加的 run 记录（ADR-0268 §4）。"""

    name: ClassVar[str] = "cron.view"
    namespace: ClassVar[str] = CRON_NAMESPACE
    description: ClassVar[str] = (
        "按 id 返回一条 cron 任务的全量定义和它的 run 记录。"
        "模型在 cron.update 前应先 view 再整份覆盖。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "任务 id。"}},
        "required": ["id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
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
        job = self._service.get_job(job_id)
        if job is None:
            return _error(f"cron job {job_id!r} not found")
        runs: list[CronRun] = self._service.get_run_records(job_id)
        return _success(
            {
                "job": job.model_dump(),
                "runs": [run.model_dump() for run in runs],
            }
        )
