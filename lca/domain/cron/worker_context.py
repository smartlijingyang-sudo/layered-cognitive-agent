"""Cron worker context assembly (ADR-0268 §3.4).

调度器到点后用这个函数组装 worker 的初始上下文。函数参数只有
``body`` 和产品上下文，**没有**父 transcript、父工具结果或
birth 之后的父消息。签名测试钉住这个结构：参数集合不得扩展出
父轮可读的通道。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.cron.models import ChatDelivery, CronRunOutcome, TargetReceipt

__all__ = ["CronWorkerResult", "WorkerProductContext", "assemble_worker_context"]


@dataclass(frozen=True, slots=True)
class CronWorkerResult:
    """One worker execution: its outcome, its report, and any receipts it owns.

    ``worker_message`` is the report the parent turn receives inside a
    :class:`~lca.contracts.models.cron.models.ScheduledHandoff` (ADR-0268 §6).
    The worker never writes a chat bubble; the visible bubble is the parent's
    reply, so the worker cannot know a delivery outcome.

    ``receipts`` therefore stays empty for an ``agent`` handoff. Empty means
    pending, and the handoff turn closes it. The two cases with no parent turn
    are the exceptions and write ``not_sent`` here: a successful
    ``space_action``, and a worker that could not resolve its job at all.

    Lives in the domain layer because it crosses the worker-to-scheduler seam
    and neither side may import the other.
    """

    outcome: CronRunOutcome
    worker_message: str = ""
    receipts: tuple[TargetReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerProductContext:
    """cron worker 可见的产品上下文（ADR-0268 §3.4）。"""

    job_id: str
    owner: str
    workspace_path: str
    timezone: str
    report: str
    delivery_targets: tuple[ChatDelivery, ...]
    run_id: str


def assemble_worker_context(body: str, product: WorkerProductContext) -> str:
    """把存储里的 ``body`` 原文与产品上下文组装成 worker 初始文本。

    这里不读取父会话，也不附加父轮消息；``body`` 是存储里的原样内容。
    """
    targets = ", ".join(target.chat_id for target in product.delivery_targets)
    return (
        f"你是一次定时任务（cron worker）。\n"
        f"任务定义原文（body）：\n{body}\n"
        f"产品上下文：\n"
        f"- job_id: {product.job_id}\n"
        f"- owner: {product.owner}\n"
        f"- workspace_path: {product.workspace_path}\n"
        f"- timezone: {product.timezone}\n"
        f"- report: {product.report}\n"
        f"- delivery_targets: {targets}\n"
        f"- run_id: {product.run_id}\n"
    )
