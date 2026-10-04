from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from lca.contracts.models.cron.card import (
    CronTaskCardWidgetPayload,
    serialize_cron_task_card_widget,
)
from lca.contracts.models.cron.models import (
    CronJob,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    OneShotSchedule,
    TargetReceipt,
    WeeklySchedule,
)
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import CronWorkerResult

_log = logging.getLogger(__name__)

SURFACE_ASSISTANT_MESSAGE = "surface/assistant_message"

_JOB_ID_RE = re.compile(r"- job_id:\s*([^\s\n]+)")


#: Returned when the worker cannot even resolve a job, so there is no target to
#: write a receipt for. ``chat_id=None`` matches ``_record_superseded``.
_UNDELIVERED = CronWorkerResult(
    outcome="runtime_failure",
    receipts=(TargetReceipt(chat_id=None, state="not_sent"),),
)


def _format_schedule_label(job: CronJob) -> str:
    """生成人类友好的任务调度规则描述。"""
    s = job.schedule
    if isinstance(s, OneShotSchedule):
        return f"一次性 {s.at.strftime('%Y-%m-%d %H:%M')}"
    if isinstance(s, IntervalSchedule):
        if s.every_seconds < 60:
            return f"每 {s.every_seconds} 秒"
        if s.every_seconds % 3600 == 0:
            return f"每 {s.every_seconds // 3600} 小时"
        if s.every_seconds % 60 == 0:
            return f"每 {s.every_seconds // 60} 分钟"
        return f"每 {s.every_seconds} 秒"
    if isinstance(s, HourlySchedule):
        return f"每小时第 {s.minute:02d} 分"
    if isinstance(s, DailySchedule):
        return f"每天 {s.hour:02d}:{s.minute:02d}"
    if isinstance(s, WeeklySchedule):
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        d = days[s.weekday] if 0 <= s.weekday < 7 else f"星期{s.weekday}"
        return f"每{d} {s.hour:02d}:{s.minute:02d}"
    return "自定义计划"


class CronWorkerRunner:
    """执行到期的 CronJob，渲染交互式任务卡片并追加投递至对应 Session。"""

    def __init__(
        self,
        *,
        store: CronStore,
        session_store: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        agent_runner: Callable[[str], Any] | None = None,
    ) -> None:
        self._store = store
        self._session_store = session_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._agent_runner = agent_runner

    async def __call__(self, arg: CronJob | str) -> CronWorkerResult:
        """支持直接传入 CronJob 或由 CronScheduler 传入组装好的上下文文本。"""
        if isinstance(arg, CronJob):
            job = arg
        else:
            match = _JOB_ID_RE.search(arg)
            if not match:
                _log.warning("cron.worker_runner: cannot extract job_id from text")
                return _UNDELIVERED
            job_id = match.group(1).strip()
            job = self._store.get_job(job_id)
            if not job:
                _log.warning("cron.worker_runner: job %s not found in store", job_id)
                return _UNDELIVERED

        return await self.execute_job(job)

    async def execute_job(self, job: CronJob) -> CronWorkerResult:
        now = self._clock()

        # 计算由于关机/挂机导致的延迟秒数（仅针对一次性任务）
        delayed_by_seconds: int | None = None
        if isinstance(job.schedule, OneShotSchedule):
            try:
                tz = ZoneInfo(job.timezone)
                at_local = job.schedule.at.astimezone(tz)
                now_local = now.astimezone(tz)
                diff_s = int((now_local - at_local).total_seconds())
                if diff_s >= 60:
                    delayed_by_seconds = diff_s
            except Exception:
                _log.warning("cron.worker_runner: error calculating delay for job %s", job.id)

        schedule_label = _format_schedule_label(job)
        execution_kind = getattr(job.execution, "kind", "agent")

        # 构造交互式任务卡片载荷
        # Resolve every target before building the card, because
        # delivery_status is embedded in the content being delivered. Sessions
        # are keyed by run_id (session/lifecycle/bind.py:178), so a topic id
        # never hits. Creating one here produced an orphan that no gateway
        # pump, no flush listener and no WebSocket ever read, while the run
        # record still said completed and the card still said delivered.
        reachable: list[tuple[str, Any]] = []
        unreachable: list[str] = []
        for target in job.delivery_targets:
            session = self._session_store.get(target.chat_id) if self._session_store else None
            if session is None:
                unreachable.append(target.chat_id)
            else:
                reachable.append((target.chat_id, session))

        if unreachable:
            _log.warning(
                "cron.worker_target_unreachable job_id=%s chat_ids=%s",
                job.id,
                ",".join(unreachable),
            )

        receipts: list[TargetReceipt] = [
            TargetReceipt(chat_id=chat_id, state="not_sent") for chat_id in unreachable
        ]

        # ADR-0268 §6: a successful space_action writes not_sent, since it
        # updates an artifact and produces no handoff into a chat.
        delivers_to_chat = execution_kind == "agent" and bool(reachable)
        delivery_status = "delivered" if delivers_to_chat else "not_sent"

        if delivers_to_chat:
            # 构造交互式任务卡片载荷
            card = CronTaskCardWidgetPayload(
                job_id=job.id,
                title=job.title,
                body=job.body,
                schedule_label=schedule_label,
                next_run_local=None,
                execution_kind=execution_kind,
                due=False,
                enabled=job.enabled,
                delayed_by_seconds=delayed_by_seconds,
                delivery_status=delivery_status,
                actions=("snooze", "edit", "delete", "toggle_pause"),
            )
            content = f"{job.body}\n{serialize_cron_task_card_widget(card)}"

            for chat_id, session in reachable:
                try:
                    session.append(
                        SURFACE_ASSISTANT_MESSAGE,
                        {
                            "role": "assistant",
                            "content": content,
                            "turn": -1,
                            "cron": True,
                        },
                    )
                except Exception:
                    _log.exception(
                        "cron.worker_delivery_failed job_id=%s chat_id=%s",
                        job.id,
                        chat_id,
                    )
                    receipts.append(TargetReceipt(chat_id=chat_id, state="failed"))
                    continue
                receipts.append(TargetReceipt(chat_id=chat_id, state="delivered"))
                _log.info(
                    "cron.worker_delivered job_id=%s chat_id=%s delayed_by=%s",
                    job.id,
                    chat_id,
                    delayed_by_seconds,
                )

        # 如果有注册真实的 agent runner，异步触发
        if self._agent_runner is not None and execution_kind == "agent":
            try:
                await self._agent_runner(job.body)
            except Exception:
                _log.exception("cron.worker_agent_runner_failed job_id=%s", job.id)

        return CronWorkerResult(outcome="completed", receipts=tuple(receipts))
