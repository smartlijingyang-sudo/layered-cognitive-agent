"""Cron task card widget payload contract (Task 1).

用于在会话消息流中渲染原生可交互的定时任务卡片（In-Chat Task Card）。
包含任务元数据、当前状态以及可交互动作集合（推迟、编辑、删除、启停）。
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CronTaskCardAction(StrEnum):
    """卡片支持的原生交互动作。"""

    SNOOZE = "snooze"
    EDIT = "edit"
    DELETE = "delete"
    TOGGLE_PAUSE = "toggle_pause"
    VIEW_DETAILS = "view_details"


class CronTaskCardWidgetPayload(BaseModel):
    """对话流内可交互任务卡片的数据载荷契约（ADR-0268 交互增强）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    widget_name: Literal["cron_task_card"] = "cron_task_card"
    job_id: str = Field(..., description="底层 CronJob ID")
    title: str = Field(..., description="任务标题")
    body: str = Field(..., description="任务执行正文或提醒内容")
    schedule_label: str = Field(..., description="人类可读的周期/时间规则")
    next_run_local: str | None = Field(default=None, description="下次运行的本地墙钟时间")
    execution_kind: str = Field(default="agent", description="执行类型：agent / script / space_action")
    due: bool = Field(default=False, description="当前是否处于到期状态")
    enabled: bool = Field(default=True, description="任务是否处于启用状态")
    delayed_by_seconds: int | None = Field(
        default=None,
        description="由于关机/休眠/挂机导致的延迟秒数；None 或 <=0 表示准时触发",
    )
    delivery_status: Literal["delivered", "failed", "silent", "not_sent"] = Field(
        default="delivered",
        description="本次投递状态",
    )
    actions: tuple[str, ...] = Field(
        default=("snooze", "edit", "delete", "toggle_pause"),
        description="前端卡片允许的交互动作集合",
    )


_WIDGET_RE = re.compile(
    r"\[widget:cron_task_card\]\s*(\{.*?\})\s*\[/widget:cron_task_card\]",
    re.DOTALL,
)


def serialize_cron_task_card_widget(payload: CronTaskCardWidgetPayload) -> str:
    """将卡片契约序列化为会话消息中的挂载标签块。"""
    return f"\n[widget:cron_task_card]\n{payload.model_dump_json(indent=2)}\n[/widget:cron_task_card]\n"


def parse_cron_task_card_widget(text: str) -> CronTaskCardWidgetPayload | None:
    """从消息文本中解析卡片契约，未匹配或 JSON 非法返回 None。"""
    if not text:
        return None
    match = _WIDGET_RE.search(text)
    if not match:
        return None
    raw_json = match.group(1).strip()
    try:
        data = json.loads(raw_json)
        return CronTaskCardWidgetPayload.model_validate(data)
    except Exception:
        return None
