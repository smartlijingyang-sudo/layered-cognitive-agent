"""``cron.list`` 工具（ADR-0268 §4、§10）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from lca.contracts.models.core.execution.decision import Observation
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.common import (
    CRON_NAMESPACE,
    _success,
)


class CronListTool:
    """``cron.list``：返回该 owner 的「即将到来」投影闭集（ADR-0268 §4、§10）。"""

    name: ClassVar[str] = "cron.list"
    namespace: ClassVar[str] = CRON_NAMESPACE
    description: ClassVar[str] = (
        "返回当前用户的「即将到来」cron 任务列表。只含投影字段"
        "（id/title/schedule_label/next_run_local/due/enabled/last_run_local/last_delivery），"
        "不含 schedule 原字段。"
    )
    parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}, "required": []}
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, *, service: CronService, owner: str) -> None:
        self._service = service
        self._owner = owner

    def validate(self, args: dict[str, Any]) -> str | None:
        del args
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        del args
        items = self._service.list_items(owner=self._owner, now=datetime.now(UTC))
        return _success({"items": [item.model_dump() for item in items]})
