from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.models.cron.models import (
    AgentExecution,
    ChatDelivery,
    CronJob,
    DailySchedule,
)
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.domain.cron.store import CronStore
from lca.infrastructure.observability.activity_feed import ActivityFeed
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_1.routes_assistants import status_screen
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import setup

REPO_ROOT = Path(__file__).resolve().parents[4]


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def provide(self, key: str, value: Any) -> None:
        pass

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


def _create_test_app(tmp_path: Path) -> tuple[Starlette, AssistantCatalogImpl, str]:
    router = RouteRegistry()
    ctx = _FakeCtx(router)

    asyncio.run(setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(root=Path(tmp_path) / "assistants")
    app.state.assistant_catalog = catalog

    handle = catalog.create(
        CreateAssistantRequest(
            name="架构小助",
            description="系统架构演化助手",
            template_id="assistant.default",
            seed_user_md="# USER.md\n用户是架构师",
        )
    )
    return app, catalog, handle.assistant_id


_ToolCalls = tuple[tuple[str, dict[str, Any]], ...]


def _run_dir(runs_root: Path, run_id: str) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    return run_dir


def _write_terminated_run(
    runs_root: Path,
    run_id: str,
    *,
    objective: str,
    started_at: float,
    closed_at: float,
    outcome: str = "completed",
    tool_calls: _ToolCalls = (),
) -> Path:
    run_dir = _run_dir(runs_root, run_id)
    (run_dir / "manifest.json").write_text(
        json.dumps({"schema": "lca.run_manifest/1", "run_id": run_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "journal.json").write_text(
        json.dumps(
            {
                "schema": "lca.journal/3.1",
                "run_id": run_id,
                "metadata": {
                    "agent_role": "solo",
                    "strategy_key": "solo",
                    "plan_ref": "sha256:abc",
                    "objective": objective,
                    "attachments": [],
                    "outcome": outcome,
                    "started_at": started_at,
                    "closed_at": closed_at,
                    "total_steps": len(tool_calls),
                    "extra": {},
                },
                "steps": [
                    {
                        "step_index": index,
                        "entered_at": started_at,
                        "tool_calls": [
                            {
                                "invocation_id": f"toolu_{index}",
                                "name": name,
                                "arguments": arguments,
                            }
                        ],
                        "tool_results": [],
                    }
                    for index, (name, arguments) in enumerate(tool_calls, start=1)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return run_dir


def _write_ledger_run(
    runs_root: Path,
    run_id: str,
    *,
    objective: str,
    started_ts: str,
    tool_calls: _ToolCalls = (),
    stop_outcome: str | None = None,
    stop_ts: str | None = None,
) -> Path:
    """Write a run that has only its spine ledger, the shape of a run in flight."""
    records: list[dict[str, Any]] = [
        _record(
            run_id,
            seq=1,
            execution_point="kernel.run.start",
            payload={"run_id": run_id, "trace_id": f"trace_{run_id}"},
            ts=started_ts,
        ),
        _record(
            run_id,
            seq=2,
            execution_point="phase.think.fold",
            payload={
                "incarnation": 1,
                "objective": objective,
                "objective_kind": "user_text",
                "phase": "think",
                "summary": "started",
            },
            ts=started_ts,
        ),
    ]
    seq = 3
    for name, arguments in tool_calls:
        records.append(
            _record(
                run_id,
                seq=seq,
                execution_point="step.tool_call.record",
                payload={
                    "arguments": arguments,
                    "invocation_id": f"toolu_{seq}",
                    "run_id": run_id,
                    "step": seq,
                    "tool_name": name,
                },
                ts=started_ts,
            )
        )
        seq += 1
    if stop_outcome is not None:
        records.append(
            _record(
                run_id,
                seq=seq,
                execution_point="kernel.run.stop",
                payload={"outcome": stop_outcome, "run_id": run_id, "trace_id": f"trace_{run_id}"},
                ts=stop_ts or started_ts,
            )
        )
    run_dir = _run_dir(runs_root, run_id)
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    (run_dir / f"{run_id}.spine.jsonl").write_text(lines, encoding="utf-8")
    return run_dir


def _record(
    run_id: str, *, seq: int, execution_point: str, payload: dict[str, Any], ts: str
) -> dict[str, Any]:
    return {
        "category": f"spine.{execution_point}",
        "causation_id": None,
        "channel": "fact",
        "event_hash": None,
        "event_id": f"{run_id}:{seq}",
        "execution_point": execution_point,
        "payload": payload,
        "prev_event_hash": None,
        "trace_id": None,
        "ts": ts,
    }


def _tree_state(root: Path) -> dict[str, tuple[int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@dataclass(frozen=True)
class _SessionStub:
    run_id: str
    status: RunLifecycleStatus


class _RegistryStub:
    def __init__(self) -> None:
        self._sessions: dict[str, _SessionStub] = {}

    def set_status(self, run_id: str, status: RunLifecycleStatus) -> None:
        self._sessions[run_id] = _SessionStub(run_id=run_id, status=status)

    def sessions(self) -> tuple[_SessionStub, ...]:
        return tuple(self._sessions.values())


@dataclass(frozen=True)
class _SnapshotEnv:
    client: TestClient
    catalog: AssistantCatalogImpl
    assistant_id: str
    runs_root: Path
    registry: _RegistryStub

    def snapshot(self) -> dict[str, Any]:
        response = self.client.get(
            f"/v1/assistants/{self.assistant_id}/status-snapshot",
            headers={"x-lca-user-id": "local-dev-user"},
        )
        assert response.status_code == 200
        return response.json()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _SnapshotEnv:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    app, catalog, assistant_id = _create_test_app(tmp_path)
    registry = _RegistryStub()
    app.state.registry = registry
    monkeypatch.setattr(status_screen, "get_activity_feed", lambda: ActivityFeed(runs_root))
    return _SnapshotEnv(
        client=TestClient(app),
        catalog=catalog,
        assistant_id=assistant_id,
        runs_root=runs_root,
        registry=registry,
    )


def test_status_snapshot_endpoint_returns_aggregated_views(env: _SnapshotEnv) -> None:
    _write_ledger_run(
        env.runs_root,
        "run_snap_live",
        objective="正在浏览 webhook 文档",
        started_ts="2026-10-03T16:00:00Z",
        tool_calls=(
            (
                "browser.spawn_task",
                {"url": "https://docs.github.com", "task": "Search webhook docs"},
            ),
        ),
    )
    env.registry.set_status("run_snap_live", RunLifecycleStatus.RUNNING)
    _write_terminated_run(
        env.runs_root,
        "run_snap_new",
        objective="整理本周架构评审记录",
        started_at=1791028800.0,
        closed_at=1791028830.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )
    _write_terminated_run(
        env.runs_root,
        "run_snap_old",
        objective="检索记忆库中的分层原则",
        started_at=1791018000.0,
        closed_at=1791018005.0,
        tool_calls=(("memory_search", {"query": "分层原则"}),),
    )

    data = env.snapshot()

    activities = data["activities"]
    assert data["assistant_id"] == env.assistant_id
    assert [row["run_id"] for row in activities] == [
        "run_snap_live",
        "run_snap_new",
        "run_snap_old",
    ]
    assert [row["title"] for row in activities] == [
        "正在浏览 webhook 文档",
        "整理本周架构评审记录",
        "检索记忆库中的分层原则",
    ]
    assert [row["status"] for row in activities] == ["running", "completed", "completed"]
    assert [row["start_time"] for row in activities] == [
        "2026-10-03T16:00:00+00:00",
        "2026-10-03T12:00:00+00:00",
        "2026-10-03T09:00:00+00:00",
    ]
    assert activities[0]["current_step"] == "Browsing docs.github.com"
    assert activities[0]["end_time"] is None
    assert activities[1]["duration_ms"] == 30000
    assert activities[1]["summary"] == "调用 1 个工具：listFiles"
    assert activities[2]["icon"] == "memory"
    assert [row["assistant_id"] for row in activities] == ["", "", ""]

    assert data["approvals"] == []
    assert data["upcoming"] == []
    assert "IDENTITY.md" in [f["filename"] for f in data["identity"]["files"]]


def test_status_snapshot_excludes_runs_nobody_is_executing(env: _SnapshotEnv) -> None:
    _write_terminated_run(
        env.runs_root,
        "run_snap_keep",
        objective="已落盘的运行",
        started_at=1791018000.0,
        closed_at=1791018005.0,
    )
    _write_ledger_run(
        env.runs_root,
        "run_snap_finished",
        objective="registry 里已终态的运行",
        started_ts="2026-10-03T16:00:00Z",
        stop_outcome="completed",
        stop_ts="2026-10-03T16:00:09Z",
    )
    env.registry.set_status("run_snap_finished", RunLifecycleStatus.COMPLETED)
    _write_ledger_run(
        env.runs_root,
        "run_snap_abandoned",
        objective="registry 里没有的运行",
        started_ts="2026-10-03T18:00:00Z",
    )

    activities = env.snapshot()["activities"]

    assert [row["run_id"] for row in activities] == ["run_snap_keep"]
    assert activities[0]["title"] == "已落盘的运行"
    assert activities[0]["status"] == "completed"


def test_status_snapshot_does_not_write_outside_the_runs_root(
    env: _SnapshotEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint reads the ledger; it must not resurrect the old activity cache.

    The projector this replaced kept ``traces/runtime/activity_cache.json``
    relative to the process CWD, so a status poll mutated the working tree.
    """
    _write_terminated_run(
        env.runs_root,
        "run_snap_ro",
        objective="只读快照",
        started_at=1791028800.0,
        closed_at=1791028830.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )
    work_dir = tmp_path / "cwd"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    runs_before = _tree_state(env.runs_root)

    activities = env.snapshot()["activities"]

    assert [row["run_id"] for row in activities] == ["run_snap_ro"]
    assert activities[0]["status"] == "completed"
    assert _tree_state(env.runs_root) == runs_before
    assert _tree_state(work_dir) == {}
    assert not (REPO_ROOT / "traces" / "runtime" / "activity_cache.json").exists()


def test_status_snapshot_includes_assistant_owned_cron_jobs(env: _SnapshotEnv) -> None:
    spec = env.catalog.get(env.assistant_id)
    store = CronStore(Path(spec.home_path))
    store.save_job(
        CronJob(
            id="job_reminder_01",
            title="喝水提醒",
            schedule=DailySchedule(kind="daily", hour=10, minute=0),
            timezone="Asia/Shanghai",
            body="提醒喝水",
            execution=AgentExecution(kind="agent"),
            delivery_targets=(ChatDelivery(chat_id="chat_01"),),
            owner=env.assistant_id,
            created_chat_id="chat_01",
            anchor_at=datetime.now(UTC),
        )
    )

    data = env.snapshot()

    assert len(data["upcoming"]) == 1
    assert data["upcoming"][0]["id"] == "job_reminder_01"
    assert data["upcoming"][0]["title"] == "喝水提醒"
