"""``cron.add`` 工具（ADR-0268 §4、§5）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.cron.models import ChatDelivery
from lca.domain.cron.service import CronService
from lca.infrastructure.tools.cron.common import (
    _CRON_JOB_PROPERTIES,
    CRON_NAMESPACE,
    _error,
    _find_list_item,
    _parse_execution,
    _parse_schedule,
    _resolve_chat_id,
    _resolve_timezone,
    _success,
)


class CronAddTool:
    """``cron.add``：新建任务。重复 id 返回现有记录，不覆盖（ADR-0268 §4、§5）。"""

    name: ClassVar[str] = "cron.add"
    namespace: ClassVar[str] = CRON_NAMESPACE
    description: ClassVar[str] = (
        "新建一个 cron 任务。id 已存在时返回现有记录，不修改。"
        "用户只给一个时刻时传 oneshot；给出重复规则时传对应周期。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": _CRON_JOB_PROPERTIES,
        "required": ["id", "title", "schedule", "body"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = "persistent"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, *, service: CronService, owner: str) -> None:
        self._service = service
        self._owner = owner

    def validate(self, args: dict[str, Any]) -> str | None:
        for field in ("id", "title", "schedule", "body"):
            value = args.get(field)
            if field == "schedule":
                if not isinstance(value, dict):
                    return "'schedule' must be an object"
                continue
            if not isinstance(value, str) or not value.strip():
                return f"'{field}' is required"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        error = self.validate(args)
        if error is not None:
            return _error(error)
        try:
            chat_id = _resolve_chat_id(args)
            if not chat_id:
                return _error("chat_id 必填：未能从参数或运行上下文解析当前 chat id")
            timezone = _resolve_timezone(args)
            if not timezone:
                return _error("timezone 必填：未能从参数或运行上下文解析用户时区")
            ZoneInfo(timezone)
            schedule = _parse_schedule(args["schedule"])
            execution = _parse_execution(args.get("execution"))
            now = datetime.now(UTC)
            delivery_targets = (ChatDelivery(chat_id=chat_id),) if execution.kind == "agent" else ()
            created = self._service.add_job(
                id=args["id"].strip(),
                title=args["title"].strip(),
                schedule=schedule,
                timezone=timezone,
                body=args["body"].strip(),
                execution=execution,
                delivery_targets=delivery_targets,
                report=args.get("report", "anomalies_only"),
                owner=self._owner,
                created_chat_id=chat_id,
                now=now,
                enabled=args.get("enabled", True),
                max_retries=int(args.get("max_retries", 0)),
                timeout_seconds=args.get("timeout_seconds"),
            )
        except ValueError as exc:
            return _error(str(exc))

        item = _find_list_item(self._service, self._owner, created.id, datetime.now(UTC))
        if item is not None:
            return _success({"job": item.model_dump()})
        # 已完成 oneshot 不在「即将到来」投影里；返回定义本身。
        return _success({"job": created.model_dump()})
