"""E2E smoke test: room API closed loop with a fake RunPort (Task 5).

Covers: create room → POST message → RoomDispatcher starts a real run via
the wired ``run_starter`` → gateway registration → transcript persisted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.testclient import TestClient

if TYPE_CHECKING:
    import pytest

from lca.contracts.capabilities import RUN_MODE_REGISTRY
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


class _FakeModeRegistry:
    def resolve(self, key: str) -> Any:
        return SimpleNamespace(key=key or "solo", role="")


class _FakeAppCtx:
    def require(self, key: str) -> Any:
        if key == RUN_MODE_REGISTRY.key:
            return _FakeModeRegistry()
        raise KeyError(key)

    def inject(self, key: str, default: Any = None) -> Any:
        return default


class _FakeRunPort:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def create_and_dispatch(self, request: Any) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunReceipt,
        )

        self.requests.append(request)
        return RunReceipt(
            run_id="run_e2e_1",
            trace_id="trace_e2e_1",
            accepted=True,
            rejection_reason=None,
        )

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        return {
            "run_id": run_id,
            "trace_id": "trace_e2e_1",
            "status": "completed",
            "session_status": "completed",
            "mode": "team",
            "agent": {"id": "solo", "name": "助手"},
            "question": "",
            "error": "",
            "output": "完整结论文本",
        }


def _build_app(tmp_path: Path) -> tuple[Starlette, _FakeRunPort]:
    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(routes_rooms.setup.setup(ctx, None))
    app = Starlette()
    router.install(app)
    run_port = _FakeRunPort()
    app.state.run_port = run_port
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.ctx = _FakeAppCtx()
    return app, run_port


def test_room_api_closed_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    gateway_calls: list[dict[str, Any]] = []

    async def _fake_register_gateway_run(
        request: Any, *, run_id: str, topic_id: str, agent_id: str, body: dict[str, Any]
    ) -> None:
        gateway_calls.append(
            {"run_id": run_id, "topic_id": topic_id, "agent_id": agent_id, "body": body}
        )

    monkeypatch.setattr(routes_rooms, "register_gateway_run", _fake_register_gateway_run)
    monkeypatch.setenv("LCA_HOME", str(tmp_path / ".lca"))

    app, run_port = _build_app(tmp_path)
    client = TestClient(app)

    # 1. create room
    room_payload = {
        "room_id": "room_e2e",
        "display_name": "E2E 室",
        "coordinator_agent_id": "coordinator_sam",
        "member_peer_ids": ["arch_guanlan", "arch_hengyue"],
        "shared_topic_id": "topic_e2e",
        "routing_policy": "coordinator_first",
    }
    create_resp = client.post("/v1/rooms", json=room_payload)
    assert create_resp.status_code == 201

    # 2. dispatch a message
    message_resp = client.post(
        "/v1/rooms/room_e2e/messages", json={"content": "请评估当前架构风险"}
    )
    assert message_resp.status_code == 202
    body = message_resp.json()
    assert body["kind"] == "run_started"
    assert body["run_id"] == "run_e2e_1"

    # 3. run_port received the real RunRequest (team mode, objective preserved)
    assert len(run_port.requests) == 1
    run_request = run_port.requests[0]
    assert run_request.user_text == "请评估当前架构风险"
    assert run_request.mode == "team"
    assert run_request.profile == "web-assistant"

    # 4. gateway registration fired with the room as topic
    assert len(gateway_calls) == 1
    assert gateway_calls[0]["run_id"] == "run_e2e_1"
    assert gateway_calls[0]["topic_id"] == "room_e2e"

    # 5. transcript persisted both facts; lazy revival appends FOLDED
    transcript = client.get("/v1/rooms/room_e2e/messages").json()["messages"]
    assert [m["kind"] for m in transcript] == ["user", "run_started", "folded"]
    assert transcript[0]["sender_id"] == "user"
    assert transcript[1]["sender_id"] == "coordinator_sam"
    assert transcript[1]["payload"]["selected_peers"] == ["coordinator_sam"]
    assert transcript[2]["payload"]["consensus_status"] == "unanimous"
    assert transcript[2]["content"] == "完整结论文本"
