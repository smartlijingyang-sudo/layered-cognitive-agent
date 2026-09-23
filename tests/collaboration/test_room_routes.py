"""Tests for /v1/rooms REST routes (room runtime go-live M1, Task 4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_3 import routes_rooms


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

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


class _FakeRunPort:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self._counter = 0

    async def create_and_dispatch(self, request: Any) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunReceipt,
        )

        self._counter += 1
        self.calls.append(request)
        return RunReceipt(
            run_id=f"run_{self._counter}",
            trace_id=f"trace_{self._counter}",
            accepted=True,
            rejection_reason=None,
        )

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        return {
            "run_id": run_id,
            "trace_id": f"trace_{run_id}",
            "status": "completed",
            "session_status": "completed",
            "mode": "team",
            "agent": {"id": "solo", "name": "助手"},
            "question": "",
            "error": "",
        }


def _build_app(tmp_path: Path, run_port: _FakeRunPort) -> Starlette:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(routes_rooms.setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    app.state.run_port = run_port
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.ctx = None
    return app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(command_endpoints, "resolve_profile_mode", lambda ctx, mode: mode or "solo")
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))
    run_port = _FakeRunPort()
    app = _build_app(tmp_path, run_port)
    client = TestClient(app)
    client._run_port = run_port  # type: ignore[attr-defined]
    return client


def _room_payload(room_id: str = "room_1") -> dict[str, Any]:
    return {
        "room_id": room_id,
        "display_name": "测试室",
        "coordinator_agent_id": "coordinator_sam",
        "member_peer_ids": ["arch_guanlan", "arch_hengyue"],
        "shared_topic_id": "topic_1",
        "routing_policy": "coordinator_first",
    }


def test_routes_rooms_register_expected_count():
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(routes_rooms.setup.setup(ctx, None))

    assert len(router._exact) == len(routes_rooms.ROUTE_SPECS)


def test_routes_rooms_paths_match_catalog():
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(routes_rooms.setup.setup(ctx, None))

    paths = {spec.path for spec in routes_rooms.ROUTE_SPECS}
    assert {
        "/v1/rooms",
        "/v1/rooms/{room_id}",
        "/v1/rooms/{room_id}/messages",
    }.issubset(router._exact.keys())
    assert paths == set(router._exact.keys())


def test_create_and_get_room(client: TestClient):
    response = client.post("/v1/rooms", json=_room_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["room_id"] == "room_1"
    assert body["member_peer_ids"] == ["arch_guanlan", "arch_hengyue"]

    fetched = client.get("/v1/rooms/room_1")
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "测试室"


def test_get_unknown_room_returns_404(client: TestClient):
    response = client.get("/v1/rooms/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "room_not_found"


def test_list_rooms(client: TestClient):
    client.post("/v1/rooms", json=_room_payload("room_a"))
    client.post("/v1/rooms", json=_room_payload("room_b"))

    response = client.get("/v1/rooms")
    assert response.status_code == 200
    room_ids = {r["room_id"] for r in response.json()["rooms"]}
    assert room_ids == {"room_a", "room_b"}


def test_post_invalid_room_spec_returns_400(client: TestClient):
    response = client.post("/v1/rooms", json={"room_id": "room_1"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_room_spec"


def test_post_message_dispatches_run(client: TestClient):
    client.post("/v1/rooms", json=_room_payload())
    response = client.post("/v1/rooms/room_1/messages", json={"content": "请帮我梳理架构"})
    assert response.status_code == 202
    body = response.json()
    assert body["kind"] == "run_started"
    assert body["room_id"] == "room_1"
    assert body["run_id"] == "run_1"
    assert body["payload"]["trace_id"] == "trace_1"
    assert body["payload"]["accepted"] is True

    # USER + RUN_STARTED recorded; Phase 2 lazy revival appends FOLDED
    messages = client.get("/v1/rooms/room_1/messages").json()["messages"]
    assert [m["kind"] for m in messages] == ["user", "run_started", "folded"]
    assert messages[2]["payload"]["consensus_status"] == "unanimous"


def test_post_message_unknown_room_returns_404(client: TestClient):
    response = client.post("/v1/rooms/nope/messages", json={"content": "hello"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "room_not_found"


def test_post_message_empty_content_returns_400(client: TestClient):
    client.post("/v1/rooms", json=_room_payload())
    response = client.post("/v1/rooms/room_1/messages", json={"content": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_content"


def test_list_messages_empty_room(client: TestClient):
    client.post("/v1/rooms", json=_room_payload())
    response = client.get("/v1/rooms/room_1/messages")
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_run_port_missing_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(routes_rooms.setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.ctx = None
    client = TestClient(app)

    client.post("/v1/rooms", json=_room_payload())
    response = client.post("/v1/rooms/room_1/messages", json={"content": "hello"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "run_port_unavailable"
