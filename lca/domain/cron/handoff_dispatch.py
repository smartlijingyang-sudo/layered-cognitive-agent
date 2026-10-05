"""The seam between a fired cron job and the parent turn that delivers it.

ADR-0268 §6 makes the parent's reply the visible bubble, so the scheduler cannot
deliver anything itself. It hands a :class:`ScheduledHandoff` to a dispatcher,
which starts a run bound to the target conversation and returns that run's id.

Lives in the domain layer because it crosses the scheduler-to-transport seam and
neither side may import the other, which is also why ``CronWorkerResult`` lives
here.
"""

from __future__ import annotations

from typing import Literal, Protocol

from lca.contracts.models.cron.models import ChatDelivery, ScheduledHandoff

__all__ = ["ReceiptState", "ScheduledHandoffDispatcher", "render_handoff_text"]

#: What one handoff turn delivered, a subset of ``TargetReceipt.state``.
#: ``not_sent`` is absent because it means no parent turn existed at all.
ReceiptState = Literal["delivered", "silent", "failed"]


def render_handoff_text(handoff: ScheduledHandoff) -> str:
    """Compose the developer message the parent turn reads.

    Carries the decision rule from ADR-0268 §6 in the text itself, because §1
    makes context the only bus the model has. The ``report`` value comes from the
    definition snapshot taken at fire time, so a later edit cannot change what
    this occurrence was asked to do.
    """
    job = handoff.task_context
    return (
        f"[cron handoff] job_id={handoff.job_id} occurrence={handoff.run_id} "
        f"outcome={handoff.outcome} report={job.report}\n"
        f"任务标题：{job.title}\n"
        f"worker 报告：\n{handoff.worker_message}\n"
        f"决定规则（ADR-0268 §6）：report=always，或报告里有新的失败、变化、"
        f"需要人处理的事，就写出回复。例行无异常且 report=anomalies_only，"
        f"调用 lca.nothing_to_do 结束本轮，不写气泡。"
    )


class ScheduledHandoffDispatcher(Protocol):
    """Starts one handoff run for one delivery target and reports how it ended."""

    async def dispatch(self, handoff: ScheduledHandoff, *, target: ChatDelivery) -> str:
        """Start a handoff run bound to ``target.chat_id`` and return its run id.

        Raise if no run could be started. The caller records the returned id
        before it awaits the turn, so a crash cannot make recovery dispatch the
        same occurrence twice.
        """
        ...

    async def await_receipt(self, run_id: str) -> ReceiptState:
        """Wait for the handoff turn to end and report what it delivered.

        ``delivered`` when the turn produced a visible reply, ``silent`` when it
        ended on ``lca.nothing_to_do``, ``failed`` when it ended with neither.
        Reading an absent reply as silent would merge "the model chose silence"
        with "the model produced nothing", so the two stay distinct.
        """
        ...
