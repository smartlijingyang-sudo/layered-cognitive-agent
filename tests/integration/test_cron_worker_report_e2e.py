"""Cron worker report contract (ADR-0268 section 6).

Commit 1baa682f8 changed the worker's job: the worker reports, the handoff
turn delivers. ``CronWorkerRunner`` no longer takes a session store and never
writes a chat bubble; an agent job returns ``outcome="completed"`` with
``worker_message=job.body`` and empty receipts (empty means pending, closed by
the handoff turn). This file pins that report contract plus the cron task card
widget payload contract. The card's actual delivery now belongs to the handoff
turn and is covered at the contract level by
``tests/contracts/cron/test_task_card_payload.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lca.contracts.models.cron.card import (
    CronTaskCardWidgetPayload,
    parse_cron_task_card_widget,
    serialize_cron_task_card_widget,
)
from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    OneShotSchedule,
)
from lca.domain.cron.store import CronStore
from lca.infrastructure.cron.worker_runner import CronWorkerRunner

CHAT_ID = "e2e-test-chat-card"


def _make_job(job_id: str = "e2e-cron-card-001") -> CronJob:
    now = datetime.now(UTC)
    return CronJob(
        id=job_id,
        title="喝水提醒",
        schedule=OneShotSchedule(kind="oneshot", at=now + timedelta(seconds=5)),
        timezone="Asia/Shanghai",
        body="该喝水了",
        execution=AgentExecution(kind="agent"),
        delivery_targets=(ChatDelivery(chat_id=CHAT_ID),),
        owner="e2e",
        created_chat_id=CHAT_ID,
        anchor_at=now,
    )


async def test_worker_reports_without_delivering() -> None:
    # 1baa682f8：worker 不再投递，只上报；投递归 handoff turn。
    runner = CronWorkerRunner(store=None)  # type: ignore[arg-type]
    job = _make_job()

    result = await runner.execute_job(job)

    assert result.outcome == "completed"
    # 报告原文：父 turn 收到后决定可见气泡的内容
    assert result.worker_message == job.body
    # 空 receipts = 待定（ADR-0268 §6）：worker 不写投递回执，由 handoff turn 闭环
    assert result.receipts == ()


def test_card_serialize_parse_roundtrip() -> None:
    card = CronTaskCardWidgetPayload(
        job_id="rt-1",
        title="t",
        body="b",
        schedule_label="一次性",
    )
    text = f"提醒正文\n{serialize_cron_task_card_widget(card)}"
    parsed = parse_cron_task_card_widget(text)
    assert parsed is not None
    assert parsed == card
    assert parse_cron_task_card_widget("纯文本无卡片") is None
    assert parse_cron_task_card_widget("") is None


async def test_job_context_text_path_executes_and_cleans_up(tmp_path: Path) -> None:
    """经文本上下文触发（scheduler 真实调用路径），用完即删。"""
    store = CronStore(tmp_path / "assistants")
    runner = CronWorkerRunner(store=store)
    job = _make_job(job_id="e2e-cron-card-003")

    store.save_job(job)
    assert store.get_job(job.id) is not None

    result = await runner(f"cron due\n- job_id: {job.id}\n")
    assert result.outcome == "completed"
    assert result.worker_message == job.body
    assert result.receipts == ()

    # 用完即删：不污染 cron 表
    assert store.delete_job(job.id) is True
    assert store.get_job(job.id) is None
    assert store.list_jobs() == []


async def test_worker_unknown_job_id_fails_clean() -> None:
    # 空 store：get_job 返回 None → runtime_failure，不抛异常
    class _EmptyStore:
        def get_job(self, job_id: str) -> None:
            return None

    runner = CronWorkerRunner(store=_EmptyStore())  # type: ignore[arg-type]
    result = await runner("cron due\n- job_id: no-such-job\n")
    assert result.outcome == "runtime_failure"
    # 无父 turn 的解析失败：worker 自写 not_sent 回执
    assert result.receipts[0].state == "not_sent"
