"""AssistantJobs Protocol —— 助理域例行任务声明面（ADR-0187 §3 D10）。

Job = ADR-0093 持续执行控制面之上的**声明式配置**：调度 / lease / 去重 /
重试 / dead-letter 全部属于 0093 WorkQueue（``lca/contracts/harness/tasks/
continuous.py``）；本 Protocol 只做 ``{home}/routines/*.yaml`` JobSpec 的
收集与手动投递（Phase 1）。0187 不新建调度框架、线程或定时器（I-A12）。

:cls:`Trigger` / :cls:`WorkItem` / :cls:`WorkStatus` 复用 ADR-0093 既有
类型（``lca.contracts.harness.tasks.continuous``），不另造平行形状。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.harness.tasks.continuous import (
    Trigger,
    TriggerKind,
    WorkItem,
    WorkStatus,
)

__all__ = [
    "AssistantJobs",
    "JobNotRegistered",
    "JobRegistration",
    "JobSpec",
    "JobsCapabilityMissing",
    "Trigger",
    "TriggerKind",
    "WorkItem",
    "WorkItemHandle",
    "WorkStatus",
]


class JobsCapabilityMissing(RuntimeError):  # noqa: N818
    """profile 缺 ``continuous_control_plane_factory`` capability（fail-closed）。

    ADR-0187 §3 D10：缺 capability ⇒ jobs 注册拒收，**不**降级为隐式线程。
    """


class JobNotRegistered(RuntimeError):  # noqa: N818
    """``fire`` 的 job 未注册（本进程注册表与 0093 队列均无该 work item）。"""


@dataclass(frozen=True)
class JobSpec:
    """``{home}/routines/*.yaml`` 的声明式 JobSpec（0093 Trigger 的配置面）。

    ``schedule`` 是声明式 cron 字面量（用户本地时区解释）；timer 投递源
    在 ADR-0187.1 落地，Phase 1 仅人工 ``fire`` 投递。
    """

    job_id: str
    schedule: str
    prompt: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.job_id or not self.job_id.strip():
            raise ValueError("JobSpec.job_id 必须为非空字符串")
        if not self.schedule or not self.schedule.strip():
            raise ValueError("JobSpec.schedule 必须为非空 cron 字面量")
        if not self.prompt or not self.prompt.strip():
            raise ValueError("JobSpec.prompt 必须为非空字符串")


@dataclass(frozen=True)
class JobRegistration:
    """``register`` 的不可变回执 —— JobSpec 进 0093 WorkQueue 的登记结果。

    ``status`` 取值：``registered``（已进 0093，work_item_id 非空）/
    ``disabled``（JobSpec.enabled=False，未进 0093，work_item_id 为空）。
    """

    job_id: str
    assistant_id: str
    work_item_id: str
    status: str

    def __post_init__(self) -> None:
        if not self.job_id or not self.job_id.strip():
            raise ValueError("JobRegistration.job_id 必须为非空字符串")
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("JobRegistration.assistant_id 必须为非空字符串")
        if self.status not in {"registered", "disabled"}:
            raise ValueError(f"JobRegistration.status 非法: {self.status!r}")
        if self.status == "registered" and not self.work_item_id.strip():
            raise ValueError("registered 状态的 JobRegistration 必须携带 work_item_id")


@dataclass(frozen=True)
class WorkItemHandle:
    """``fire`` 的不可变回执 —— 指向已投递进 0093 的 work item。

    ``status`` 取 0093 :cls:`WorkStatus` 值（投递后通常为 ``pending``）。
    """

    work_id: str
    assistant_id: str
    job_id: str
    trigger_id: str
    status: str

    def __post_init__(self) -> None:
        for field_name in ("work_id", "assistant_id", "job_id", "trigger_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"WorkItemHandle.{field_name} 必须为非空字符串")
        if not self.status.strip():
            raise ValueError("WorkItemHandle.status 必须为非空 WorkStatus 值")


@runtime_checkable
class AssistantJobs(Protocol):
    """助理域例行任务收集面（capability ``assistant.jobs``，contribution=collect）。

    约束（ADR-0187 §3 D10 + §5 I-A12）：

    - register / fire 一律经 ``continuous_control_plane_factory`` 进 0093
      WorkQueue；缺 capability ⇒ :cls:`JobsCapabilityMissing`（fail-closed）；
    - 本面**无**线程 / 定时器 / 调度循环；投递源仅 ``actor="manual"``
      （Phase 1）；timer / webhook 投递源 = ADR-0187.1（0093 的 Trigger
      来源扩展，不是独立调度器）。
    """

    def register(self, assistant_id: str, job_spec: JobSpec) -> JobRegistration:
        """收 JobSpec → 注册 0093 WorkItem；发 ``assistant.job.registered`` EP。"""

    def list_jobs(self, assistant_id: str) -> tuple[JobRegistration, ...]:
        """列本助理已登记 job（按 job_id 排序）。"""

    def fire(self, assistant_id: str, job_id: str) -> WorkItemHandle:
        """人工投递一次 ``actor="manual"`` Trigger；发 ``assistant.job.fired`` EP。"""
