from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.observability.activity_projector import get_global_activity_projector
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


def _create_test_app(tmp_path: Any) -> tuple[Starlette, AssistantCatalogImpl, str]:
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


def test_status_snapshot_endpoint_returns_aggregated_views(tmp_path: Path):
    app, _, assistant_id = _create_test_app(tmp_path)
    client = TestClient(app)

    # Pre-populate global projector with an activity
    projector = get_global_activity_projector()
    projector.feed_event(
        {
            "execution_point": "phase.tool.call.start",
            "payload": {
                "invocation_id": "call_snap_01",
                "run_id": "run_test_snap",
                "assistant_id": assistant_id,
                "tool_name": "hatch_gws_cli",
                "arguments": {"action": "search", "query": "status meeting", "service": "gmail"},
                "timestamp": "2026-10-02T12:00:00Z",
            },
        }
    )

    resp = client.get(
        f"/v1/assistants/{assistant_id}/status-snapshot",
        headers={"x-lca-user-id": "local-dev-user"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["assistant_id"] == assistant_id
    assert "activities" in data
    assert "approvals" in data
    assert "upcoming" in data
    assert "identity" in data

    # Verify Activity in snapshot
    activities = data["activities"]
    assert len(activities) >= 1
    target = next((a for a in activities if a["id"] == "call_snap_01"), None)
    assert target is not None
    assert target["title"] == "正在搜索 Gmail 邮件"
    assert target["status"] == "running"

    # Verify Identity files in snapshot
    assert "files" in data["identity"]
    filenames = [f["filename"] for f in data["identity"]["files"]]
    assert "IDENTITY.md" in filenames

    # Verify cancellation reflected in snapshot
    projector.cancel_activity(assistant_id, "call_snap_01")
    resp2 = client.get(
        f"/v1/assistants/{assistant_id}/status-snapshot",
        headers={"x-lca-user-id": "local-dev-user"},
    )
    assert resp2.status_code == 200
    act2 = resp2.json()["activities"]
    cancelled_item = next((a for a in act2 if a["id"] == "call_snap_01"), None)
    assert cancelled_item is not None
    assert cancelled_item["status"] == "cancelled"
    assert cancelled_item["result_summary"] == "User cancelled operation"
