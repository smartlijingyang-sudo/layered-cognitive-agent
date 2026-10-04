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
from lca.domain.cron.worker_context import CronWorkerResult
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
    # Sessions are keyed by run_id in production, so a live one must already
    # exist for the target. The worker no longer creates one on a miss.
    session_store.sessions["chat-123"] = _FakeSession("chat-123")
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
    session_store.sessions["chat-456"] = _FakeSession("chat-456")

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


@pytest.mark.asyncio
async def test_unreachable_target_records_not_sent_and_creates_no_orphan(temp_env):
    """A topic id with no live session must not be silently created.

    run_56f67fbf52d9's sleep reminder fired on time, logged
    cron.worker_delivered, and recorded outcome=completed with receipts=[].
    The worker had called session_store.create(chat_id) on a miss, but
    sessions are keyed by run_id (session/lifecycle/bind.py:178), so the
    append landed in an orphan no gateway pump, flush listener or WebSocket
    ever read. The user never saw the reminder.
    """
    store, _lock_dir, _tmp = temp_env
    session_store = _FakeSessionStore()
    runner = CronWorkerRunner(
        store=store,
        session_store=session_store,
        clock=lambda: datetime(2026, 10, 4, 6, 33, 38, tzinfo=UTC),
    )

    job = CronJob(
        id="sleep_reminder_20261004",
        title="提醒睡觉",
        body="提醒用户：该睡觉了！",
        schedule=OneShotSchedule(
            at=datetime(2026, 10, 4, 14, 33, 33, tzinfo=ZoneInfo("Asia/Shanghai"))
        ),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_269aafa73e53",
        created_chat_id="tpc_O1w50CiXxcQk",
        delivery_targets=(ChatDelivery(chat_id="tpc_O1w50CiXxcQk"),),
        anchor_at=datetime(2026, 10, 4, 6, 30, 52, tzinfo=UTC),
    )
    store.save_job(job)

    result: CronWorkerResult = await runner(job)

    assert result.outcome == "completed"
    assert [(r.chat_id, r.state) for r in result.receipts] == [("tpc_O1w50CiXxcQk", "not_sent")]
    assert session_store.sessions == {}, "the worker must not create an orphan session"


@pytest.mark.asyncio
async def test_reachable_target_records_delivered(temp_env):
    store, _lock_dir, _tmp = temp_env
    session_store = _FakeSessionStore()
    session_store.sessions["tpc_live"] = _FakeSession("tpc_live")
    runner = CronWorkerRunner(
        store=store,
        session_store=session_store,
        clock=lambda: datetime(2026, 10, 4, 6, 33, 38, tzinfo=UTC),
    )

    job = CronJob(
        id="job-live-1",
        title="提醒",
        body="正文",
        schedule=OneShotSchedule(
            at=datetime(2026, 10, 4, 14, 33, 33, tzinfo=ZoneInfo("Asia/Shanghai"))
        ),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_1",
        created_chat_id="tpc_live",
        delivery_targets=(ChatDelivery(chat_id="tpc_live"),),
        anchor_at=datetime(2026, 10, 4, 6, 30, 52, tzinfo=UTC),
    )
    store.save_job(job)

    result: CronWorkerResult = await runner(job)

    assert [(r.chat_id, r.state) for r in result.receipts] == [("tpc_live", "delivered")]
    assert len(session_store.sessions["tpc_live"].events) == 1
    assert session_store.sessions.keys() == {"tpc_live"}


@pytest.mark.asyncio
async def test_append_failure_records_failed_not_delivered(temp_env):
    store, _lock_dir, _tmp = temp_env

    class _BrokenSession(_FakeSession):
        def append(self, event_type, data, **kwargs):
            raise RuntimeError("session backend down")

    session_store = _FakeSessionStore()
    session_store.sessions["tpc_broken"] = _BrokenSession("tpc_broken")
    runner = CronWorkerRunner(
        store=store,
        session_store=session_store,
        clock=lambda: datetime(2026, 10, 4, 6, 33, 38, tzinfo=UTC),
    )

    job = CronJob(
        id="job-broken-1",
        title="提醒",
        body="正文",
        schedule=OneShotSchedule(
            at=datetime(2026, 10, 4, 14, 33, 33, tzinfo=ZoneInfo("Asia/Shanghai"))
        ),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="asst_1",
        created_chat_id="tpc_broken",
        delivery_targets=(ChatDelivery(chat_id="tpc_broken"),),
        anchor_at=datetime(2026, 10, 4, 6, 30, 52, tzinfo=UTC),
    )
    store.save_job(job)

    result: CronWorkerResult = await runner(job)

    assert [(r.chat_id, r.state) for r in result.receipts] == [("tpc_broken", "failed")]
