"""Run lifecycle status —— 状态机唯一 enum（ADR-0183 I-FW-SSOT-2）。

webserver session 的 ``RunStatus``、Journal reducer 的 ``JournalRunStatus``
均为 ``RunLifecycleStatus`` 别名；禁止新增平行状态机 enum。
"""

from __future__ import annotations

from enum import Enum

from lca.contracts.atoms.enums import SpanStatus
from lca.contracts.models.core.lifecycle import TaskStatus


class RunLifecycleStatus(str, Enum):
    """LCA run 状态机唯一 enum（I-FW-SSOT-2）。

    所有权:状态机词表归本 enum;webserver session(``RunStatus`` 别名)、
    Journal reducer(``JournalRunStatus`` 别名)与未来 ``EnvelopeEmitter.
    emit_status_change`` 共用本 enum,不允许平行定义。

    成员语义:

    - PENDING: 已创建,未启动
    - RUNNING: 运行中
    - PAUSED: 暂停(等待用户输入 / 审批)
    - WAITING_INPUT: 等待用户输入;carrier wire 值 ``waiting_input``,
      语义上是 PAUSED 子态,保留以兼容现有 SSE / LobeHub 投影
    - COMPLETED: 正常完成
    - FAILED: 失败
    - CANCELLED: 用户取消;value 取 wire 值 ``canceled``——journal 终态事件、
      ``_TERMINAL_STATUS_VALUES``、doctor / web 投影均按 value 读取
    - TIMEOUT: 超时
    """

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "canceled"
    # COMPAT(delete-when: rg "\.CANCELED\b" 生产引用归零, tracking: ADR-0183 PR-11)
    CANCELED = CANCELLED
    TIMEOUT = "timeout"

    @classmethod
    def from_finish_status(cls, raw: str) -> RunLifecycleStatus:
        """把终态事件的 ``status`` 原始字符串投影到本 enum。

        precondition: ``raw`` 来自 ``TeamRunFinished`` / ``AgentRunFinished``
        的 status 字段,取 A2A 兼容的 TaskStatus / SpanStatus 词表
        (``lca/agent/team_handle.py`` 与 ``cognitive_agent.py`` 发射)。

        规则:

        - ``"error"`` (SpanStatus.ERROR) / ``"failed"`` (TaskStatus.FAILED) → FAILED
        - ``"canceled"`` (TaskStatus.CANCELED) → CANCELLED
        - 其余值(含 ``"completed"`` 与 ``"working"`` 等非终态值) → COMPLETED;
          根容器发射 Finished 事件本身即终止事实

        本方法是这些 raw 字符串的唯一收口路径
        (reducer 的 ``_map_finish_status`` 映射已删除)。
        """
        if raw in {SpanStatus.ERROR.value, TaskStatus.FAILED.value}:
            return cls.FAILED
        if raw == TaskStatus.CANCELED.value:
            return cls.CANCELLED
        return cls.COMPLETED


__all__ = ["RunLifecycleStatus"]
