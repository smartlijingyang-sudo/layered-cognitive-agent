"""cron 工具共享实现（ADR-0268 §4、§5、§9、§10）。

五个 cron 工具共用的参数 schema、观察构造与解析辅助函数。
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.cron.models import (
    AgentExecution,
    CronListItem,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    SpaceActionExecution,
    WeeklySchedule,
)
from lca.domain.cron.service import CronService

__all__ = [
    "CRON_NAMESPACE",
    "_CRON_JOB_PROPERTIES",
    "_error",
    "_find_list_item",
    "_parse_execution",
    "_parse_schedule",
    "_resolve_chat_id",
    "_resolve_timezone",
    "_success",
]

CRON_NAMESPACE = "cron"

_Schedule = OneShotSchedule | IntervalSchedule | HourlySchedule | DailySchedule | WeeklySchedule
_SCHEDULE_ADAPTER: TypeAdapter[_Schedule] = TypeAdapter(_Schedule)
_EXECUTION_ADAPTER = TypeAdapter(AgentExecution | SpaceActionExecution)

#: cron.add / cron.update 共享的参数属性（模型路径整份覆盖复用同一形状）。
_CRON_JOB_PROPERTIES: dict[str, Any] = {
    "id": {
        "type": "string",
        "description": "任务唯一 id。重复 id 的 cron.add 返回现有记录，不覆盖。",
    },
    "title": {"type": "string", "description": "任务标题。"},
    "schedule": {
        "type": "object",
        "description": "调度定义，由 kind 判别：oneshot 带 at（ISO 8601，aware）；"
        "interval 带 every_seconds；hourly 带 minute；daily 带 hour/minute；"
        "weekly 带 weekday（0=周一…6=周日）/hour/minute。",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["oneshot", "interval", "hourly", "daily", "weekly"],
            },
            "at": {"type": "string", "description": "oneshot 触发时刻（ISO 8601，带时区）。"},
            "every_seconds": {"type": "integer", "description": "interval 间隔秒数（>0）。"},
            "minute": {"type": "integer", "description": "hourly/daily/weekly 的分钟（0-59）。"},
            "hour": {"type": "integer", "description": "daily/weekly 的小时（0-23）。"},
            "weekday": {"type": "integer", "description": "weekly 的星期几（0=周一…6=周日）。"},
        },
        "required": ["kind"],
    },
    "timezone": {
        "type": "string",
        "description": "IANA 时区（如 Asia/Shanghai）。缺省取用户当前时区。",
    },
    "body": {"type": "string", "description": "cron worker 的指令正文。"},
    "execution": {
        "type": "object",
        "description": "执行方式。agent 需要 chat_id 作为投递目标；"
        "space_action 只更新 artifact，不产生 handoff。",
        "properties": {
            "kind": {"type": "string", "enum": ["agent", "space_action"]},
            "artifact_id": {"type": "string", "description": "space_action 要更新的 artifact id。"},
        },
        "required": ["kind"],
    },
    "report": {
        "type": "string",
        "enum": ["always", "anomalies_only"],
        "description": "报告策略，缺省 anomalies_only。",
    },
    "chat_id": {"type": "string", "description": "创建聊天 id；缺省从运行上下文取。"},
    "enabled": {"type": "boolean", "description": "是否启用，缺省 true。"},
    "max_retries": {"type": "integer", "description": "runtime 失败/超时的重试次数，>=0，缺省 0。"},
    "timeout_seconds": {
        "type": ["integer", "null"],
        "description": "worker 超时秒数；缺省按 ADR-0268 §7 推导。",
    },
}


def _error(message: str) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=message,
    )


def _success(payload: dict[str, Any]) -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
    )


def _current_chat_id() -> str:
    """从运行上下文解析当前 chat id（RunAmbit/session），无则返回空串。"""
    from lca.infrastructure.observability.facade.run.ambit import current_run_ambit

    with suppress(Exception):
        ambit = current_run_ambit()
        if ambit is not None:
            scope = getattr(ambit, "scope", None)
            for source in (ambit, scope):
                for attr in ("chat_id", "session_id", "conversation_id"):
                    value = getattr(source, attr, None)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return ""


def _current_timezone() -> str:
    """从运行上下文解析用户当前时区（client_timezone 同源），无则返回空串。"""
    from lca.infrastructure.observability.facade.run.ambit import current_run_ambit

    with suppress(Exception):
        ambit = current_run_ambit()
        if ambit is not None:
            scope = getattr(ambit, "scope", None)
            for source in (ambit, scope):
                for attr in ("timezone", "client_timezone"):
                    value = getattr(source, attr, None)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return ""


def _resolve_chat_id(args: Mapping[str, Any]) -> str:
    value = args.get("chat_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _current_chat_id()


def _resolve_timezone(args: Mapping[str, Any]) -> str:
    value = args.get("timezone")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _current_timezone()


def _parse_schedule(
    raw: object,
) -> OneShotSchedule | IntervalSchedule | HourlySchedule | DailySchedule | WeeklySchedule:
    try:
        return _SCHEDULE_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise ValueError(f"schedule 非法: {exc}") from exc


def _parse_execution(raw: object) -> AgentExecution | SpaceActionExecution:
    if raw is None:
        return AgentExecution()
    try:
        return _EXECUTION_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise ValueError(f"execution 非法: {exc}") from exc


def _find_list_item(
    service: CronService, owner: str, job_id: str, now: datetime
) -> CronListItem | None:
    return next(
        (item for item in service.list_items(owner=owner, now=now) if item.id == job_id), None
    )
