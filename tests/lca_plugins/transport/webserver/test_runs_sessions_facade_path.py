"""HTTP ``create_run`` dispatches through ``RunPort`` (P1 gateway path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    create_run,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
    RunReceipt,
    RunRequest,
)


class _StubRunPort:
    """Stand-in for the production ``RunPort``."""

    def __init__(self, *, accepted: bool = True, run_id: str = "run_legacy") -> None:
        self.accepted = accepted
        self.run_id = run_id
        self.calls: list[RunRequest] = []

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt:
        self.calls.append(request)
        return RunReceipt(
            run_id=self.run_id,
            trace_id="trace_legacy",
            accepted=self.accepted,
            rejection_reason=None if self.accepted else "stub rejection",
        )


def _request(
    *,
    body: dict[str, Any],
    app_state: Any = None,
) -> Request:
    if app_state is None:
        app_state = type("State", (), {})()

    app = Starlette()
    app.state = app_state  # type: ignore[assignment]
    body_bytes = json.dumps(body).encode("utf-8")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/runs",
        "headers": [(b"content-type", b"application/json")],
        "app": app,
    }
    return Request(scope, receive=receive)


def _resolve_mode_stub(ctx: Any, mode: str) -> str:
    return mode or "solo"


@pytest.fixture
def file_store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


@pytest.fixture(autouse=True)
def _patch_create_run_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(command_endpoints, "resolve_profile_mode", _resolve_mode_stub)

    async def _noop_register(*_args: Any, **_kwargs: Any) -> None:
        return None

    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming import (
        gateway_lifecycle,
    )

    monkeypatch.setattr(gateway_lifecycle, "register_gateway_run", _noop_register)
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming import auth

    monkeypatch.setattr(auth, "mint_user_jwt", lambda **_kwargs: "stub.jwt.token")


class TestCreateRunViaRunPort:
    @pytest.mark.asyncio
    async def test_create_run_uses_run_port(
        self,
        file_store: LocalFileStore,
    ) -> None:
        port = _StubRunPort(run_id="run_xyz")

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(
            body={"messages": [{"role": "user", "content": "hi"}]},
            app_state=state,
        )
        response = await create_run(request)
        assert response.status_code == 202
        assert len(port.calls) == 1
        body = json.loads(response.body)
        assert body["run_id"] == "run_xyz"

    @pytest.mark.asyncio
    async def test_decode_error_returns_400_without_dispatch(
        self,
        file_store: LocalFileStore,
    ) -> None:
        port = _StubRunPort()

        state = type("State", (), {})()
        state.file_store = file_store
        state.run_port = port
        request = _request(body={"messages": []}, app_state=state)
        response = await create_run(request)
        assert response.status_code == 400
        assert port.calls == []
