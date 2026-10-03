"""Tests for CronDaemonService and CronWorkerRunner (Task 2)."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from lca.contracts.models.cron.card import parse_cron_task_card_widget
from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    OneShotSchedule,
)
from lca.domain.cron.store import CronStore
from lca.infrastructure.cron.daemon import CronDaemonService
from lca.infrastructure.cron.worker_runner import CronWorkerRunner


class _FakeSession:
    def __init__(self, session_id: str):
        self.id = session_id
        self.events: list[tuple[str, dict]] = []

    def append(self, event_type: str, data: dict, **kwargs):
        self.events.append((event_type, data))
        return len(self.events)


class _FakeSessionStore:
    def __init__(self):
        self.sessions: dict[str, _FakeSession] = {}

    def get(self, session_id: str):
        return self.sessions.get(session_id)

    def create(self, session_id: str | None = None):
        sid = session_id or "default_session"
        sess = _FakeSession(sid)
        self.sessions[sid] = sess
        return sess


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        store = CronStore(p / "assistant_home")
        lock_dir = p / "locks"
        yield store, lock_dir, p


@pytest.mark.asyncio
async def test_worker_runner_delivers_task_card_to_session(temp_env):
    store, _lock_dir, _tmp = temp_env
    session_store = _FakeSessionStore()
    runner = CronWorkerRunner(
        store=store,
        session_store=session_store,
        clock=lambda: datetime(2026, 10, 3, 21, 30, tzinfo=UTC),
    )

    tz = ZoneInfo("Asia/Shanghai")
    at_time = datetime(2026, 10, 3, 21, 20, tzinfo=tz)  # 10 minutes earlier (delayed)
    job = CronJob(
        id="job-oneshot-1",
        title="喝水提醒",
        body="李超，记得喝水！",
        schedule=OneShotSchedule(at=at_time),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_123",
        created_chat_id="chat-123",
        delivery_targets=(ChatDelivery(chat_id="chat-123"),),
        anchor_at=datetime.now(UTC),
    )
    store.save_job(job)

    # Execute runner
    await runner(job)

    # Check session received message
    sess = session_store.get("chat-123")
    assert sess is not None
    assert len(sess.events) == 1
    event_type, data = sess.events[0]
    assert event_type == "surface/assistant_message"
    assert "李超，记得喝水！" in data["content"]
    assert "[widget:cron_task_card]" in data["content"]

    # Check parsed card payload
    parsed = parse_cron_task_card_widget(data["content"])
    assert parsed is not None
    assert parsed.job_id == "job-oneshot-1"
    assert parsed.title == "喝水提醒"
    assert parsed.delayed_by_seconds is not None
    assert parsed.delayed_by_seconds >= 600  # >= 10 mins


@pytest.mark.asyncio
async def test_daemon_lifecycle_and_tick(temp_env):
    store, lock_dir, tmp = temp_env
    session_store = _FakeSessionStore()

    now_clock = datetime(2026, 10, 3, 22, 0, tzinfo=UTC)
    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp),
        session_store=session_store,
        tick_interval_s=1,
        clock=lambda: now_clock,
    )

    # Start and stop lifecycle
    await daemon.start()
    assert daemon.is_running is True

    await daemon.stop()
    assert daemon.is_running is False


@pytest.mark.asyncio
async def test_daemon_tick_fires_due_job_and_delivers(temp_env):
    store, lock_dir, tmp = temp_env
    session_store = _FakeSessionStore()

    # Create job due at 21:00
    tz = ZoneInfo("Asia/Shanghai")
    at_time = datetime(2026, 10, 3, 21, 0, tzinfo=tz)
    job = CronJob(
        id="job-tick-due-1",
        title="到点测试",
        body="这是测试消息",
        schedule=OneShotSchedule(at=at_time),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_123",
        created_chat_id="chat-456",
        delivery_targets=(ChatDelivery(chat_id="chat-456"),),
        anchor_at=datetime.now(UTC),
    )
    store.save_job(job)

    # Current time is 21:05 (due = True)
    now_clock = datetime(2026, 10, 3, 21, 5, tzinfo=tz).astimezone(UTC)
    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp),
        session_store=session_store,
        tick_interval_s=1,
        clock=lambda: now_clock,
    )

    report = await daemon.tick(now_clock)
    assert report.due == 1
    assert report.started == 1

    # Wait for worker task to complete
    await daemon._scheduler.wait_idle()

    # Verify session received card
    sess = session_store.get("chat-456")
    assert sess is not None
    assert len(sess.events) == 1
    _, data = sess.events[0]
    assert "[widget:cron_task_card]" in data["content"]
    assert "这是测试消息" in data["content"]

    # Verify run record written to store
    runs = store.list_runs("job-tick-due-1")
    assert len(runs) == 1
    assert runs[0].outcome == "completed"
