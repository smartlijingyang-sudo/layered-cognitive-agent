"""End-to-end scenario invariant test suite for Cron Daemon and Interactive UI.

Validates INV-CRON-01 through INV-CRON-06:
- INV-CRON-01: 常驻守护与崩溃重启自愈 (Daemon Persistence & Recovery)
- INV-CRON-02: 到期精准触发与执行记录落盘 (Accurate Tick & Run Persistence)
- INV-CRON-03: 关机/挂机自愈防轰炸 (Self-Healing & Anti-Bombing)
- INV-CRON-04: 会话日志原生注入与卡片契约 (Session Log Injection & Card Contract)
- INV-CRON-05: 交互式操作原地响应 (Interactive Actions API Response: Run Now & Snooze)
- INV-CRON-06: 并发与文件锁安全 (Concurrency & Lock Safety)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from starlette.requests import Request

from lca.contracts.models.cron.card import (
    CronTaskCardAction,
    CronTaskCardWidgetPayload,
    parse_cron_task_card_widget,
)
from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    IntervalSchedule,
    OneShotSchedule,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore, MultiAssistantCronStore
from lca.infrastructure.cron.daemon import CronDaemonService
from lca.plugins.transport.webserver.routes_1.routes_assistants.jobs import (
    run_assistant_job,
    snooze_assistant_job,
)


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


class _FakeCatalog:
    def __init__(self, home: Path):
        self.home = home

    def get(self, assistant_id: str):
        return type("Spec", (), {"home_path": str(self.home), "owner": "user-1"})()

    def home_path_for(self, assistant_id: str) -> Path:
        return self.home


def _make_http_request(
    method: str, path_params: dict, body: dict | None = None, home: Path | None = None
):
    scope = {
        "type": "http",
        "method": method,
        "path_params": path_params,
        "headers": [(b"x-lca-user-id", b"user-1"), (b"content-type", b"application/json")],
        "app": type(
            "App", (), {"state": type("State", (), {"assistant_catalog": _FakeCatalog(home)})()}
        ),
    }
    req = Request(scope)
    if body is not None:
        req._body = json.dumps(body).encode("utf-8")
    else:
        req._body = b"{}"
    return req


# ---------------------------------------------------------------------------
# INV-CRON-01: 常驻守护与崩溃重启自愈 (Daemon Persistence & Recovery)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_01_daemon_persistence_and_recovery(tmp_path: Path) -> None:
    """Test daemon starts, gracefully shuts down, and recovers persisted jobs on restart."""
    asst_id = "asst_inv01"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)
    lock_dir = tmp_path / "locks"

    future_time = datetime.now(UTC) + timedelta(hours=1)
    job = CronJob(
        id="job_persist_1",
        title="持久化提醒测试",
        body="守护进程重启自愈验证",
        schedule=OneShotSchedule(at=future_time),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner=asst_id,
        created_chat_id="session_inv01",
        delivery_targets=(ChatDelivery(chat_id="session_inv01"),),
        anchor_at=datetime.now(UTC),
        enabled=True,
    )
    store.save_job(job)

    # 1. 启动第一个 Daemon 实例
    multi_store = MultiAssistantCronStore(assistants_dir=tmp_path / "assistants")
    daemon1 = CronDaemonService(
        store=multi_store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        tick_interval_s=1,
    )

    await daemon1.start()
    assert daemon1.is_running is True

    # 模拟停机/优雅退出
    await daemon1.stop()
    assert daemon1.is_running is False

    # 2. 模拟系统崩溃后重新启动新的 Daemon 实例，验证数据完整恢复
    multi_store_restarted = MultiAssistantCronStore(assistants_dir=tmp_path / "assistants")
    all_jobs = multi_store_restarted.list_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].id == "job_persist_1"
    assert all_jobs[0].title == "持久化提醒测试"

    daemon2 = CronDaemonService(
        store=multi_store_restarted,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        tick_interval_s=1,
    )
    await daemon2.start()
    assert daemon2.is_running is True
    await daemon2.stop()
    assert daemon2.is_running is False


# ---------------------------------------------------------------------------
# INV-CRON-02: 到期精准触发与执行记录落盘 (Accurate Tick & Run Persistence)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_02_accurate_tick_and_run_persistence(tmp_path: Path) -> None:
    """Test due job triggers accurately on tick and persists CronRun record to disk."""
    asst_id = "asst_inv02"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)
    lock_dir = tmp_path / "locks"
    session_store = _FakeSessionStore()

    # 创建一个刚好到期的任务
    now = datetime(2026, 10, 3, 21, 30, tzinfo=UTC)
    job = CronJob(
        id="job_due_now",
        title="到期打卡任务",
        body="请记得打卡",
        schedule=OneShotSchedule(at=now - timedelta(seconds=10)),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner=asst_id,
        created_chat_id="session_inv02",
        delivery_targets=(ChatDelivery(chat_id="session_inv02"),),
        anchor_at=now,
        enabled=True,
    )
    store.save_job(job)

    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        session_store=session_store,
        tick_interval_s=1,
        clock=lambda: now,
    )

    # 触发单次 Tick
    report = await daemon.tick()
    assert report.due >= 1
    assert report.started >= 1

    # 等待异步任务完成
    await daemon._scheduler.wait_idle()

    # 验证执行记录已写盘
    runs = store.list_runs(job_id="job_due_now")
    assert len(runs) >= 1
    run = runs[0]
    assert run.run_id.startswith("job_due_now-")
    assert run.outcome == "completed"

    # 验证磁盘物理文件存在
    runs_dir = asst_dir / "cron" / "job_due_now" / "runs"
    assert runs_dir.exists()
    run_files = list(runs_dir.glob("*.json"))
    assert len(run_files) >= 1


# ---------------------------------------------------------------------------
# INV-CRON-03: 关机/挂机自愈防轰炸 (Self-Healing & Anti-Bombing)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_03_self_healing_anti_bombing(tmp_path: Path) -> None:
    """Test oneshot job sends delayed compensation, and interval job aligns to future without bombing."""
    asst_id = "asst_inv03"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)
    lock_dir = tmp_path / "locks"
    session_store = _FakeSessionStore()
    session_store.create("session_inv03")

    now = datetime(2026, 10, 3, 21, 30, tzinfo=UTC)

    # A. 过去 2 小时前的一次性任务（挂机补偿）
    two_hours_ago = now - timedelta(hours=2)
    oneshot_job = CronJob(
        id="job_missed_oneshot",
        title="关机期间错过的会议提醒",
        body="部门例会已开始",
        schedule=OneShotSchedule(at=two_hours_ago),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner=asst_id,
        created_chat_id="session_inv03",
        delivery_targets=(ChatDelivery(chat_id="session_inv03"),),
        anchor_at=two_hours_ago,
        enabled=True,
    )
    store.save_job(oneshot_job)

    # B. 每 15 分钟的周期任务（过去2小时理应有8次，但绝不应轰炸8次）
    interval_job = CronJob(
        id="job_missed_interval",
        title="周期体检",
        body="心跳巡检",
        schedule=IntervalSchedule(every_seconds=900),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner=asst_id,
        created_chat_id="session_inv03",
        delivery_targets=(ChatDelivery(chat_id="session_inv03"),),
        anchor_at=two_hours_ago,
        enabled=True,
    )
    store.save_job(interval_job)

    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        session_store=session_store,
        tick_interval_s=1,
        clock=lambda: now,
    )

    # 第一轮 Tick（开机恢复）
    report1 = await daemon.tick()
    assert report1.due >= 1

    await daemon._scheduler.wait_idle()

    # 验证 oneshot 消息被投递到 session，且解析 Widget Payload 确认 delayed_by_seconds >= 7000
    sess = session_store.get("session_inv03")
    assert sess is not None
    matching_events = [data for et, data in sess.events if "部门例会已开始" in data["content"]]
    assert len(matching_events) == 1

    content = matching_events[0]["content"]
    payload = parse_cron_task_card_widget(content)
    assert payload is not None
    assert payload.delayed_by_seconds is not None
    assert payload.delayed_by_seconds >= 7000

    # 验证第二轮 Tick 不会再轰炸 oneshot 任务
    report2 = await daemon.tick()
    # 此时 oneshot 已有 run 记录，不会再触发
    assert report2.due == 0 or report2.started == 0

    # 验证 interval 任务不会连续堆积多次 run 记录
    interval_runs = store.list_runs(job_id="job_missed_interval")
    assert len(interval_runs) <= 1


# ---------------------------------------------------------------------------
# INV-CRON-04: 会话日志原生注入与卡片契约 (Session Log Injection & Card Contract)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_04_session_log_card_contract(tmp_path: Path) -> None:
    """Test injected session message satisfies CronTaskCardWidgetPayload contract."""
    asst_id = "asst_inv04"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)
    lock_dir = tmp_path / "locks"
    session_store = _FakeSessionStore()
    session_store.create("session_inv04")

    now = datetime(2026, 10, 3, 21, 30, tzinfo=UTC)
    job = CronJob(
        id="job_contract_check",
        title="契约验证提醒",
        body="包含操作指令与上下文",
        schedule=OneShotSchedule(at=now - timedelta(seconds=10)),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner=asst_id,
        created_chat_id="session_inv04",
        delivery_targets=(ChatDelivery(chat_id="session_inv04"),),
        anchor_at=now,
        enabled=True,
    )
    store.save_job(job)

    daemon = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        session_store=session_store,
        tick_interval_s=1,
        clock=lambda: now,
    )

    await daemon.tick()
    await daemon._scheduler.wait_idle()

    sess = session_store.get("session_inv04")
    assert sess is not None
    assert len(sess.events) == 1
    event_type, event_data = sess.events[0]
    assert event_type == "surface/assistant_message"
    raw_content = event_data["content"]
    assert "[widget:cron_task_card]" in raw_content
    assert "[/widget:cron_task_card]" in raw_content

    # 强类型反序列化校验
    payload = parse_cron_task_card_widget(raw_content)
    assert payload is not None
    assert isinstance(payload, CronTaskCardWidgetPayload)
    assert payload.job_id == "job_contract_check"
    assert payload.title == "契约验证提醒"
    assert payload.body == "包含操作指令与上下文"
    assert payload.delivery_status == "delivered"

    # 包含预设交互动作
    assert CronTaskCardAction.SNOOZE in payload.actions
    assert CronTaskCardAction.EDIT in payload.actions
    assert CronTaskCardAction.DELETE in payload.actions
    assert CronTaskCardAction.TOGGLE_PAUSE in payload.actions


# ---------------------------------------------------------------------------
# INV-CRON-05: 交互式操作原地响应 (Interactive Actions API Response)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_05_interactive_actions_run_and_snooze(tmp_path: Path) -> None:
    """Test /run and /snooze endpoints respond accurately and update persistence."""
    asst_id = "asst_inv05"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)

    tz = ZoneInfo("Asia/Shanghai")
    base_time = datetime(2026, 10, 5, 10, 0, 0, tzinfo=tz)
    job = CronJob(
        id="job_action_test",
        title="交互操作任务",
        body="动作响应验证",
        schedule=OneShotSchedule(at=base_time),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="user-1",
        created_chat_id="session_inv05",
        delivery_targets=(ChatDelivery(chat_id="session_inv05"),),
        anchor_at=datetime.now(UTC),
        enabled=True,
    )
    store.save_job(job)

    # 1. 模拟 Snooze 推迟 15 分钟
    req_snooze = _make_http_request(
        "POST",
        path_params={"assistant_id": asst_id, "job_id": "job_action_test"},
        body={"minutes": 15},
        home=asst_dir,
    )
    now_before = datetime.now(tz)
    resp_snooze = await snooze_assistant_job(req_snooze)
    now_after = datetime.now(tz)
    assert resp_snooze.status_code == 200

    data_snooze = json.loads(resp_snooze.body.decode("utf-8"))
    assert data_snooze["snoozed_minutes"] == 15

    # 验证更新写盘，new_at 应当是以当前时间推迟 15 分钟
    service = CronService(store)
    updated_job = service.get_job("job_action_test")
    assert updated_job is not None
    assert isinstance(updated_job.schedule, OneShotSchedule)
    expected_min = now_before + timedelta(minutes=15) - timedelta(seconds=2)
    expected_max = now_after + timedelta(minutes=15) + timedelta(seconds=2)
    assert expected_min <= updated_job.schedule.at <= expected_max

    # 2. 模拟立即运行 (Run Now)
    req_run = _make_http_request(
        "POST",
        path_params={"assistant_id": asst_id, "job_id": "job_action_test"},
        home=asst_dir,
    )
    resp_run = await run_assistant_job(req_run)
    assert resp_run.status_code == 200

    data_run = json.loads(resp_run.body.decode("utf-8"))
    assert data_run["job_id"] == "job_action_test"
    assert data_run["outcome"] == "completed"

    # 验证立即运行产生新的 run 记录
    runs = store.list_runs(job_id="job_action_test")
    assert len(runs) >= 1
    assert runs[0].outcome == "completed"


# ---------------------------------------------------------------------------
# INV-CRON-06: 并发与文件锁安全 (Concurrency & Lock Safety)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inv_cron_06_file_lock_safety(tmp_path: Path) -> None:
    """Test cron file lock ensures mutual exclusion between processes/coroutines."""
    asst_id = "asst_inv06"
    asst_dir = tmp_path / "assistants" / asst_id
    asst_dir.mkdir(parents=True, exist_ok=True)
    store = CronStore(asst_dir)
    lock_dir = tmp_path / "locks"

    now = datetime(2026, 10, 3, 21, 30, tzinfo=UTC)
    daemon1 = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        tick_interval_s=1,
        clock=lambda: now,
    )
    daemon2 = CronDaemonService(
        store=store,
        lock_dir=lock_dir,
        workspace_path=str(tmp_path),
        tick_interval_s=1,
        clock=lambda: now,
    )

    now_ms = int(now.timestamp() * 1000)

    # 1. 实例 1 获取锁应当成功
    assert daemon1._scheduler._acquire_lock(now_ms) is True

    # 2. 锁被持有期间，实例 2 尝试获取同一锁必须失败
    assert daemon2._scheduler._acquire_lock(now_ms) is False

    # 3. 实例 1 释放锁
    daemon1._scheduler.release_lock()

    # 4. 释放后，实例 2 再次获取锁应当成功
    assert daemon2._scheduler._acquire_lock(now_ms) is True
    daemon2._scheduler.release_lock()
