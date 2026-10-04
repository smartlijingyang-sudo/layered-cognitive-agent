"""Cron 提醒 → 前端卡片推送端到端（ADR-0268 交互增强）。

链路：
  CronScheduler 到期 → CronWorkerRunner.execute_job(job)
  → CronTaskCardWidgetPayload → serialize_cron_task_card_widget()
  → ``[widget:cron_task_card]{json}[/widget:cron_task_card]``
  → session_store.append("surface/assistant_message", {...})
  → 前端消息流 patch 解析标签 → <CronTaskCard/>。

断言：
- worker 执行一次性 job 后，目标 session 收到 surface/assistant_message
- content 可被 parse_cron_task_card_widget 解析为合法 CronTaskCardWidgetPayload
- payload 是卡片结构（widget_name/actions/job_id），不是纯文本
- 测试 job 走隔离 tmp CronStore，用完即删，不碰生产 cron 表

不动：不启动真实 scheduler/daemon；session_store 用内存 fake；
  前端渲染不断言（无浏览器），只断言到"前端可解析的契约"为止。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
from lca.infrastructure.cron.worker_runner import (
    SURFACE_ASSISTANT_MESSAGE,
    CronWorkerRunner,
)

CHAT_ID = "e2e-test-chat-card"


class _FakeSession:
    def __init__(self) -> None:
        self.appended: list[tuple[str, dict[str, Any]]] = []

    def append(self, surface: str, payload: dict[str, Any]) -> None:
        self.appended.append((surface, payload))


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, _FakeSession] = {}

    def get(self, chat_id: str) -> _FakeSession | None:
        return self.sessions.get(chat_id)

    def create(self, chat_id: str) -> _FakeSession:
        sess = _FakeSession()
        self.sessions[chat_id] = sess
        return sess


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


async def test_worker_delivers_card_to_session() -> None:
    sessions = _FakeSessionStore()
    runner = CronWorkerRunner(store=None, session_store=sessions)  # type: ignore[arg-type]
    job = _make_job()

    result = await runner.execute_job(job)

    assert result == "completed"
    sess = sessions.sessions.get(CHAT_ID)
    assert sess is not None
    assert len(sess.appended) == 1
    surface, payload = sess.appended[0]
    assert surface == SURFACE_ASSISTANT_MESSAGE
    assert surface == "surface/assistant_message"
    assert payload["role"] == "assistant"
    assert payload["cron"] is True
    assert "[widget:cron_task_card]" in payload["content"]


async def test_card_payload_is_structured_not_plaintext() -> None:
    sessions = _FakeSessionStore()
    runner = CronWorkerRunner(store=None, session_store=sessions)  # type: ignore[arg-type]
    job = _make_job(job_id="e2e-cron-card-002")

    await runner.execute_job(job)

    content = sessions.sessions[CHAT_ID].appended[0][1]["content"]
    card = parse_cron_task_card_widget(content)
    assert card is not None
    assert card.widget_name == "cron_task_card"
    assert card.job_id == "e2e-cron-card-002"
    assert card.title == "喝水提醒"
    assert card.body == "该喝水了"
    assert "snooze" in card.actions
    assert "delete" in card.actions
    assert card.delivery_status == "delivered"
    # 卡片是结构不是纯文本：body 外必须有可解析的 JSON 契约
    assert "[widget:cron_task_card]" in content
    assert "[/widget:cron_task_card]" in content


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
    sessions = _FakeSessionStore()
    runner = CronWorkerRunner(store=store, session_store=sessions)
    job = _make_job(job_id="e2e-cron-card-003")

    store.save_job(job)
    assert store.get_job(job.id) is not None

    result = await runner(f"cron due\n- job_id: {job.id}\n")
    assert result == "completed"
    assert len(sessions.sessions[CHAT_ID].appended) == 1

    # 用完即删：不污染 cron 表
    assert store.delete_job(job.id) is True
    assert store.get_job(job.id) is None
    assert store.list_jobs() == []


async def test_worker_unknown_job_id_fails_clean() -> None:
    # 空 store：get_job 返回 None → runtime_failure，不抛异常
    class _EmptyStore:
        def get_job(self, job_id: str) -> None:
            return None

    runner = CronWorkerRunner(store=_EmptyStore(), session_store=_FakeSessionStore())  # type: ignore[arg-type]
    result = await runner("cron due\n- job_id: no-such-job\n")
    assert result == "runtime_failure"
