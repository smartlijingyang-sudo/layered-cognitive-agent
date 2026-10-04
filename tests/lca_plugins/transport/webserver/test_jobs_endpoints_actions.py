"""Test /run and /snooze endpoints for assistant jobs (Task 4)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from starlette.requests import Request

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    OneShotSchedule,
    TargetReceipt,
)
from lca.domain.cron.service import CronService
from lca.domain.cron.store import CronStore
from lca.domain.cron.worker_context import CronWorkerResult
from lca.infrastructure.cron.worker_runner import CronWorkerRunner
from lca.plugins.transport.webserver.routes_1.routes_assistants.jobs import (
    run_assistant_job,
    snooze_assistant_job,
)


class _FakeCatalog:
    def __init__(self, home: Path):
        self.home = home

    def get(self, assistant_id: str):
        return type("Spec", (), {"home_path": str(self.home), "owner": "user-1"})()

    def home_path_for(self, assistant_id: str) -> Path:
        return self.home


def _make_request(
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
        import json

        req._body = json.dumps(body).encode("utf-8")
    else:
        req._body = b"{}"
    return req


def _make_job(job_id: str, *, at: datetime) -> CronJob:
    """One-shot agent job owned by ``user-1`` with a single chat target."""
    return CronJob(
        id=job_id,
        title="测试任务",
        body="测试内容",
        schedule=OneShotSchedule(at=at),
        timezone="Asia/Shanghai",
        execution=AgentExecution(),
        owner="user-1",
        created_chat_id="chat-1",
        delivery_targets=(ChatDelivery(chat_id="chat-1"),),
        anchor_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_snooze_assistant_job(tmp_path: Path):
    store = CronStore(tmp_path)
    tz = ZoneInfo("Asia/Shanghai")
    at_time = datetime.now(tz)
    store.save_job(_make_job("job-snooze-1", at=at_time))

    req = _make_request(
        "POST",
        path_params={"assistant_id": "asst-1", "job_id": "job-snooze-1"},
        body={"minutes": 15},
        home=tmp_path,
    )

    resp = await snooze_assistant_job(req)
    assert resp.status_code == 200
    import json

    data = json.loads(resp.body.decode("utf-8"))
    assert data["snoozed_minutes"] == 15
    assert "new_at" in data

    # Verify updated in store
    service = CronService(store)
    updated = service.get_job("job-snooze-1")
    assert updated is not None
    assert isinstance(updated.schedule, OneShotSchedule)
    diff = updated.schedule.at - at_time
    assert abs(diff.total_seconds() - 15 * 60) < 5


@pytest.mark.asyncio
async def test_run_assistant_job_now(tmp_path: Path):
    store = CronStore(tmp_path)
    store.save_job(_make_job("job-run-now-1", at=datetime.now(UTC) + timedelta(hours=1)))

    req = _make_request(
        "POST",
        path_params={"assistant_id": "asst-1", "job_id": "job-run-now-1"},
        home=tmp_path,
    )

    resp = await run_assistant_job(req)
    assert resp.status_code == 200
    import json

    data = json.loads(resp.body.decode("utf-8"))
    assert data["job_id"] == "job-run-now-1"
    assert data["outcome"] == "completed"
    # The fake app carries no session_store, so the only target is unreachable
    # and the worker writes not_sent. Both the response and the record carry
    # that receipt, since "completed" on its own reads as delivered.
    unreachable = (TargetReceipt(chat_id="chat-1", state="not_sent"),)
    assert data["receipts"] == [receipt.model_dump() for receipt in unreachable]

    runs = store.list_runs("job-run-now-1")
    assert len(runs) == 1
    assert runs[0].outcome == "completed"
    assert runs[0].receipts == unreachable
    assert runs[0].run_id == data["run_id"]


@pytest.mark.asyncio
async def test_run_assistant_job_records_worker_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The run record carries the worker's own outcome.

    Regression: ``run_assistant_job`` hardcoded ``outcome="completed"`` and
    dropped ``result.receipts``, so a failed manual run was recorded as a
    successful one and the payload put the whole ``CronWorkerResult`` dataclass
    into JSON (TypeError at response render).
    """
    store = CronStore(tmp_path)
    store.save_job(_make_job("job-run-fail-1", at=datetime.now(UTC) + timedelta(hours=1)))

    failure = CronWorkerResult(
        outcome="runtime_failure",
        receipts=(TargetReceipt(chat_id=None, state="not_sent"),),
    )

    async def _fake_execute_job(self: CronWorkerRunner, job: CronJob) -> CronWorkerResult:
        return failure

    monkeypatch.setattr(CronWorkerRunner, "execute_job", _fake_execute_job)

    req = _make_request(
        "POST",
        path_params={"assistant_id": "asst-1", "job_id": "job-run-fail-1"},
        home=tmp_path,
    )

    resp = await run_assistant_job(req)
    assert resp.status_code == 200
    import json

    data = json.loads(resp.body.decode("utf-8"))
    assert data["outcome"] == "runtime_failure"
    assert data["receipts"] == [{"chat_id": None, "state": "not_sent"}]

    runs = store.list_runs("job-run-fail-1")
    assert len(runs) == 1
    assert runs[0].outcome == "runtime_failure"
    assert runs[0].receipts == failure.receipts
    assert runs[0].run_id == data["run_id"]
