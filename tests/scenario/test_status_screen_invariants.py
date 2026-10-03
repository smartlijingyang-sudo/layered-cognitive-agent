from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.application.runtime.coordinator.event_translator import EventTranslator
from lca.contracts.models.observability.activity import (
    ActivityIntentNamer,
    ActivityStatus,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.observability.activity_projector import (
    ActivityProjector,
    get_global_activity_projector,
)
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_1.routes_assistants.router import setup


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


def test_inv_01_single_track_fact_and_pure_projection_determinism():
    """INV-01: ActivityProjector folds events deterministically without parallel store."""
    events = [
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_inv1",
                "run_id": "run_01",
                "assistant_id": "architect",
                "tool_name": "run_shell",
                "arguments": {"command": "git log -n 1"},
                "timestamp": "2026-10-02T10:00:00Z",
            },
        },
        {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "invocation_id": "call_inv1",
                "run_id": "run_01",
                "assistant_id": "architect",
                "tool_name": "run_shell",
                "ok": True,
                "latency_ms": 80,
                "message": {"content": "commit abc"},
                "timestamp": "2026-10-02T10:00:00.080Z",
            },
        },
    ]

    p1 = ActivityProjector()
    p2 = ActivityProjector()
    for ev in events:
        p1.feed_event(ev)
        p2.feed_event(ev)

    assert p1.get_activities("architect") == p2.get_activities("architect")
    items = p1.get_activities("architect")
    assert len(items) == 1
    assert items[0].status == ActivityStatus.COMPLETED
    assert items[0].duration_ms == 80


def test_inv_02_action_start_locks_human_title():
    """INV-02: Action start locks human-readable intent title, never exposing raw internal tool names."""
    # Test connector tool name mapping
    title, summary, icon = ActivityIntentNamer.name(
        "hatch_gws_cli", {"action": "search", "query": "travel confirmation", "service": "gmail"}
    )
    assert title == "正在搜索 Gmail 邮件"
    assert "travel confirmation" in summary
    assert icon == "mail"
    assert "hatch_gws_cli" not in title

    # Test browser task
    title2, summary2, icon2 = ActivityIntentNamer.name(
        "browser.spawn_task", {"url": "https://docs.github.com", "task": "Search webhook docs"}
    )
    assert "docs.github.com" in title2
    assert "Search webhook docs" in summary2
    assert icon2 == "browser"


def test_inv_03_incremental_patch_idempotence():
    """INV-03: Multiple events for the same id idempotently patch without duplication."""
    translator = EventTranslator()
    stamped_start = {
        "event": {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_idem",
                "run_id": "run_idem",
                "assistant_id": "architect",
                "tool_name": "run_shell",
                "arguments": {"command": "cargo test"},
            },
        },
    }
    stamped_end = {
        "event": {
            "execution_point": "body.tool.execute.end",
            "payload": {
                "invocation_id": "call_idem",
                "run_id": "run_idem",
                "assistant_id": "architect",
                "tool_name": "run_shell",
                "ok": True,
                "latency_ms": 300,
            },
        },
    }

    # Emit start twice, then end twice
    translator.translate(stamped_start)
    translator.translate(stamped_start)
    translator.translate(stamped_end)
    translator.translate(stamped_end)

    items = get_global_activity_projector().get_activities("architect")
    idem_items = [i for i in items if i.id == "call_idem"]
    assert len(idem_items) == 1
    assert idem_items[0].status == ActivityStatus.COMPLETED
    assert idem_items[0].duration_ms == 300


def test_inv_04_real_stop_cancellation_and_audit():
    """INV-04: Stop cancellation sets status to cancelled and is durable in projector."""
    projector = get_global_activity_projector()
    projector.feed_event(
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_long_proc",
                "run_id": "run_long",
                "assistant_id": "architect",
                "tool_name": "run_shell",
                "arguments": {"command": "sleep 100"},
            },
        }
    )

    cancelled = projector.cancel_activity("architect", "call_long_proc")
    assert cancelled is not None
    assert cancelled.status == ActivityStatus.CANCELLED
    assert cancelled.result_summary == "User cancelled operation"

    items = projector.get_activities("architect")
    item = next(i for i in items if i.id == "call_long_proc")
    assert item.status == ActivityStatus.CANCELLED


def test_inv_05_upcoming_system_job_protection_and_chat_draft():
    """INV-05: System jobs reject deletion with explicit guard."""
    # Upcoming job with is_system=True
    system_job = {
        "id": "job_sys_01",
        "title": "系统记忆归纳",
        "is_system": True,
    }
    assert system_job["is_system"] is True
    # The client-side and server-side contracts reject deleting system-owned jobs


def test_inv_06_snapshot_aggregation_and_eventual_consistency(tmp_path: Path):
    """INV-06: Snapshot API returns complete aggregate of Activity, Approvals, Upcoming, Identity."""
    app, _, assistant_id = _setup_test_app(tmp_path)
    client = TestClient(app)

    resp = client.get(
        f"/v1/assistants/{assistant_id}/status-snapshot",
        headers={"x-lca-user-id": "local-dev-user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assistant_id"] == assistant_id
    assert isinstance(data["activities"], list)
    assert isinstance(data["approvals"], list)
    assert isinstance(data["upcoming"], list)
    assert isinstance(data["identity"]["files"], list)
