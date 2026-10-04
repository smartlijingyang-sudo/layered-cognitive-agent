from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.contracts.models.observability.activity import (
    ActivityCategory,
    ActivityIntentNamer,
    ActivityStatus,
)
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.observability.activity_feed import ActivityFeed
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import cancel_run
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunCommandReceipt
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_1.routes_assistants import status_screen
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import setup
from tests.support.run_artifacts import (
    run_dir,
    write_journal,
    write_manifest,
    write_spine,
)

if TYPE_CHECKING:
    import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _setup_test_app(tmp_path: Path) -> tuple[Starlette, AssistantCatalogImpl, str]:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(root=tmp_path / "assistants")
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
    def __init__(self, sessions: tuple[_SessionStub, ...] = ()) -> None:
        self._sessions = {session.run_id: session for session in sessions}

    def get(self, run_id: str) -> _SessionStub | None:
        return self._sessions.get(run_id)

    def sessions(self) -> tuple[_SessionStub, ...]:
        return tuple(self._sessions.values())


class _CancelPortStub:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel(self, run_id: str) -> RunCommandReceipt:
        self.cancelled.append(run_id)
        return RunCommandReceipt(accepted=True, status="canceled")


def test_inv_01_single_track_fact_and_pure_projection_determinism(tmp_path: Path) -> None:
    """INV-01: The feed is a pure function of the artifacts on disk.

    Retargeted from ``ActivityProjector``, which folded transport events into a
    mutable process-global store. There is no event track left to be single, so
    the invariant now binds the read: two independent feeds over one
    ``runs_root`` agree, and one feed re-read agree with itself.
    """
    runs_root = tmp_path / "runs"
    list_dir = run_dir(runs_root, "run_a1")
    write_manifest(list_dir, "run_a1")
    write_journal(
        list_dir,
        "run_a1",
        objective="帮我列出文件",
        outcome="completed",
        started_at=1791028800.0,
        closed_at=1791028830.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )
    git_dir = run_dir(runs_root, "run_a2")
    write_manifest(git_dir, "run_a2")
    write_journal(
        git_dir,
        "run_a2",
        objective="查一下最近三次提交",
        outcome="failed",
        started_at=1791018000.0,
        closed_at=1791018050.0,
        tool_calls=(("runCommand", {"command": "git log --oneline -3"}),),
    )

    first = ActivityFeed(runs_root).list_activities()
    second = ActivityFeed(runs_root).list_activities()
    feed = ActivityFeed(runs_root)
    again = feed.list_activities()

    assert first == second == again
    assert [row.run_id for row in first] == ["run_a1", "run_a2"]
    assert first[0].status is ActivityStatus.COMPLETED
    assert first[0].start_time == "2026-10-03T12:00:00+00:00"
    assert first[0].duration_ms == 30000
    assert first[0].summary == "调用 1 个工具：listFiles"
    assert first[1].status is ActivityStatus.FAILED
    assert first[1].duration_ms == 50000
    assert first[1].category is ActivityCategory.COMMAND
    assert first[1].icon == "terminal"


def test_inv_02_action_start_locks_human_title(tmp_path: Path) -> None:
    """INV-02: The row title stays the human objective; the namer supplies icon and live step.

    The title no longer comes from the tool call, because one row now covers a
    whole run rather than one action. ``ActivityIntentNamer`` still owns the
    icon and the ``current_step`` of a running row.
    """
    runs_root = tmp_path / "runs"
    mail_dir = run_dir(runs_root, "run_b1")
    write_manifest(mail_dir, "run_b1")
    write_journal(
        mail_dir,
        "run_b1",
        objective="帮我搜索出行确认邮件 <!-- system-context: 用户偏好 -->",
        outcome="completed",
        started_at=1791028800.0,
        closed_at=1791028830.0,
        tool_calls=(
            (
                "hatch_gws_cli",
                {"action": "search", "query": "travel confirmation", "service": "gmail"},
            ),
        ),
    )
    browse_dir = run_dir(runs_root, "run_b2")
    write_spine(
        browse_dir,
        "run_b2",
        started_ts="2026-10-03T14:00:00+00:00",
        objective="浏览 webhook 文档",
        tool_calls=(
            (
                "browser.spawn_task",
                {"url": "https://docs.github.com", "task": "Search webhook docs"},
            ),
        ),
    )

    rows = ActivityFeed(runs_root).list_activities(live_run_ids=("run_b2",))
    by_id = {row.run_id: row for row in rows}

    mail = by_id["run_b1"]
    assert mail.title == "帮我搜索出行确认邮件"
    assert "hatch_gws_cli" not in mail.title
    assert mail.icon == "mail"
    assert mail.tool_name == "hatch_gws_cli"
    assert mail.current_step is None

    browse = by_id["run_b2"]
    assert browse.title == "浏览 webhook 文档"
    assert browse.status is ActivityStatus.RUNNING
    assert browse.icon == "browser"
    assert browse.current_step == "Browsing docs.github.com"
    assert browse.end_time is None

    title, summary, icon = ActivityIntentNamer.name(
        "hatch_gws_cli", {"action": "search", "query": "travel confirmation", "service": "gmail"}
    )
    assert title == "正在搜索 Gmail 邮件"
    assert "travel confirmation" in summary
    assert icon == "mail"

    title2, summary2, icon2 = ActivityIntentNamer.name(
        "browser.spawn_task", {"url": "https://docs.github.com", "task": "Search webhook docs"}
    )
    assert "docs.github.com" in title2
    assert "Search webhook docs" in summary2
    assert icon2 == "browser"


def test_inv_03_reread_reflects_artifact_change(tmp_path: Path) -> None:
    """INV-03: Re-reading tracks the artifact; re-reading an unchanged artifact is stable.

    Replaces incremental patch idempotence. Nothing is patched any more, so the
    invariant that survives is the one the memo has to honour: a changed
    artifact is visible on the next read, and an unchanged one yields equal
    rows without a second derivation drifting.
    """
    runs_root = tmp_path / "runs"
    c1_dir = run_dir(runs_root, "run_c1")
    write_manifest(c1_dir, "run_c1")
    write_journal(
        c1_dir,
        "run_c1",
        objective="第一版目标",
        outcome="completed",
        started_at=1791000000.0,
        closed_at=1791000030.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )

    feed = ActivityFeed(runs_root)
    first = feed.list_activities()
    assert len(first) == 1
    assert first[0].title == "第一版目标"
    assert first[0].status is ActivityStatus.COMPLETED
    assert first[0].duration_ms == 30000
    assert feed.list_activities() == first

    # Both the objective and the outcome change byte length, so the memo stamp
    # moves on size alone even where mtime resolution is coarse.
    write_journal(
        c1_dir,
        "run_c1",
        objective="第二版目标（更长）",
        outcome="failed",
        started_at=1791000000.0,
        closed_at=1791000060.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )

    third = feed.list_activities()
    assert len(third) == 1
    assert third != first
    assert third[0].title == "第二版目标（更长）"
    assert third[0].status is ActivityStatus.FAILED
    assert third[0].duration_ms == 60000
    assert feed.list_activities() == third


def test_inv_04_real_stop_cancellation_and_audit(tmp_path: Path) -> None:
    """INV-04: Cancellation is a control-plane act on the run; the feed only reports it.

    Replaces ``projector.cancel_activity``. The observation plane no longer
    carries a cancellable row, so the invariant splits: the ledger's terminal
    outcome (``kernel.run.stop`` or ``journal.metadata.outcome``) reads back as
    ``CANCELLED``, and the cancel handler returns its receipt without writing
    to any activity store.
    """
    runs_root = tmp_path / "runs"
    stopped_dir = run_dir(runs_root, "run_d1")
    write_manifest(stopped_dir, "run_d1")
    write_journal(
        stopped_dir,
        "run_d1",
        objective="跑一个很长的命令",
        outcome="stopped",
        started_at=1791028800.0,
        closed_at=1791028810.0,
        tool_calls=(("runCommand", {"command": "sleep 100"}),),
    )
    canceled_dir = run_dir(runs_root, "run_d2")
    write_spine(
        canceled_dir,
        "run_d2",
        started_ts="2026-10-03T16:00:00Z",
        objective="另一个很长的命令",
        tool_calls=(("runCommand", {"command": "sleep 100"}),),
        stop_outcome="canceled",
        stop_ts="2026-10-03T16:00:05Z",
    )

    app = Starlette(
        routes=[Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"])]
    )
    port = _CancelPortStub()
    app.state.run_port = port
    app.state.registry = _RegistryStub(
        (_SessionStub(run_id="run_d1", status=RunLifecycleStatus.RUNNING),)
    )
    before = _tree_state(tmp_path)

    response = TestClient(app).post("/runs/run_d1/cancel")

    assert response.status_code == 200
    assert response.json() == {"status": "canceled"}
    assert port.cancelled == ["run_d1"]
    assert _tree_state(tmp_path) == before
    assert not (REPO_ROOT / "traces" / "runtime" / "activity_cache.json").exists()

    rows = ActivityFeed(runs_root).list_activities(live_run_ids=("run_d2",))
    by_id = {row.run_id: row for row in rows}
    assert by_id["run_d1"].status is ActivityStatus.CANCELLED
    assert by_id["run_d1"].end_time == "2026-10-03T12:00:10+00:00"
    assert by_id["run_d2"].status is ActivityStatus.CANCELLED
    assert by_id["run_d2"].end_time == "2026-10-03T16:00:05+00:00"
    assert by_id["run_d2"].duration_ms == 5000


def test_inv_05_snapshot_aggregation_and_eventual_consistency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-05: The snapshot aggregates Activity, Approvals, Upcoming and Identity.

    Reads a ``tmp_path`` runs_root instead of the process-wide feed, which would
    fold whatever real runs happen to sit under ``traces/runs``.
    """
    runs_root = tmp_path / "runs"
    newer = run_dir(runs_root, "run_f1")
    write_manifest(newer, "run_f1")
    write_journal(
        newer,
        "run_f1",
        objective="整理本周架构评审记录",
        outcome="completed",
        started_at=1791028800.0,
        closed_at=1791028830.0,
        tool_calls=(("listFiles", {"path": "."}),),
    )
    older = run_dir(runs_root, "run_f2")
    write_manifest(older, "run_f2")
    write_journal(
        older,
        "run_f2",
        objective="检索记忆库中的分层原则",
        outcome="completed",
        started_at=1791018000.0,
        closed_at=1791018005.0,
        tool_calls=(("memory_search", {"query": "分层原则"}),),
    )

    app, _, assistant_id = _setup_test_app(tmp_path)
    app.state.registry = _RegistryStub()
    monkeypatch.setattr(status_screen, "get_activity_feed", lambda: ActivityFeed(runs_root))
    client = TestClient(app)

    resp = client.get(
        f"/v1/assistants/{assistant_id}/status-snapshot",
        headers={"x-lca-user-id": "local-dev-user"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["assistant_id"] == assistant_id
    assert [row["run_id"] for row in data["activities"]] == ["run_f1", "run_f2"]
    assert [row["title"] for row in data["activities"]] == [
        "整理本周架构评审记录",
        "检索记忆库中的分层原则",
    ]
    assert data["approvals"] == []
    assert data["upcoming"] == []
    assert "IDENTITY.md" in [f["filename"] for f in data["identity"]["files"]]


def test_inv_06_rows_carry_start_time_and_sort_newest_first(tmp_path: Path) -> None:
    """INV-06: No row ships an empty start_time, and rows come back newest first.

    Locks the defect that motivated replacing the projector: rows built from a
    transport-fed cache could carry no timestamp at all, which both blanked the
    timeline and made the sort order arbitrary. A journal whose ``started_at``
    is still ``0.0`` recovers the moment from the ledger's opening record.
    """
    runs_root = tmp_path / "runs"
    stamped = run_dir(runs_root, "run_e1")
    write_manifest(stamped, "run_e1")
    write_journal(
        stamped,
        "run_e1",
        objective="整理归档",
        outcome="completed",
        started_at=1791028800.0,
        closed_at=1791028810.0,
    )
    recovered = run_dir(runs_root, "run_e2")
    write_manifest(recovered, "run_e2")
    write_journal(
        recovered,
        "run_e2",
        objective="启动即失败的运行",
        outcome="failed",
        started_at=0.0,
        closed_at=0.0,
    )
    write_spine(recovered, "run_e2", started_ts="2026-10-03T14:00:00+00:00")
    live = run_dir(runs_root, "run_e3")
    write_spine(live, "run_e3", started_ts="2026-10-03T16:00:00Z", objective="正在进行")

    rows = ActivityFeed(runs_root).list_activities(live_run_ids=("run_e3",))

    assert [row.run_id for row in rows] == ["run_e3", "run_e2", "run_e1"]
    assert [row.start_time for row in rows] == [
        "2026-10-03T16:00:00+00:00",
        "2026-10-03T14:00:00+00:00",
        "2026-10-03T12:00:00+00:00",
    ]
    assert all(row.start_time.strip() for row in rows)
    assert rows[1].status is ActivityStatus.FAILED
    assert rows[1].end_time is None
    assert rows[2].status is ActivityStatus.COMPLETED
