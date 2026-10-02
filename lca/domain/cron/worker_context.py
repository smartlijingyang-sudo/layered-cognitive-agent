"""Cron worker context assembly (ADR-0268 §3.4).

调度器到点后用这个函数组装 worker 的初始上下文。函数参数只有
``body`` 和产品上下文，**没有**父 transcript、父工具结果或
birth 之后的父消息。签名测试钉住这个结构：参数集合不得扩展出
父轮可读的通道。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.cron.models import ChatDelivery

__all__ = ["WorkerProductContext", "assemble_worker_context"]


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
