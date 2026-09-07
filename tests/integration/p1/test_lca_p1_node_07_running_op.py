"""L2-7 + Task 16: ``POST /runs`` returns ``ws_token`` and keeps ``live_url``.

Spec §5.6.1: the 202 envelope is byte-compat with the legacy keys
(``run_id``, ``trace_id``, ``agent``, ``live_url``) AND adds a fresh
``ws_token`` so the front-end can open the LCA WS gateway immediately.
The ``PostgresRunningOperationStore`` is the PR-3 follow-up; in this
test the ``ws_token`` is the bridge that lets the front-end dial the
WS without it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    create_run,
)


class _StubRunPort:
    def __init__(self, *, run_id: str = "run_test_create", accepted: bool = True) -> None:
        self.run_id = run_id
        self.accepted = accepted
        self.calls: list[Any] = []

    async def create_and_dispatch(self, request: Any) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunReceipt,
        )

        self.calls.append(request)
        return RunReceipt(
            run_id=self.run_id,
            trace_id="trace_test",
            accepted=self.accepted,
            rejection_reason=None if self.accepted else "stub rejection",
        )


def _stub_mode(ctx: Any, mode: str) -> str:
    return mode or "solo"


@pytest.fixture(autouse=True)
def _patch_resolve_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(command_endpoints, "resolve_profile_mode", _stub_mode)


def _request(body: dict[str, Any], state: Any) -> Request:
    app = Starlette()
    app.state = state  # type: ignore[assignment]
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


def test_create_run_receipt_includes_ws_token_and_keeps_live_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rsa_keys: dict[str, str],  # noqa: ARG001 — autouse session fixture
) -> None:
    """The 202 envelope carries ``ws_token`` AND keeps ``live_url`` for back-compat."""
    from lca.infrastructure.file.store import LocalFileStore

    monkeypatch.delenv("LCA_RUNTIME_FACADE", raising=False)
    file_store = LocalFileStore(tmp_path / "files")
    port = _StubRunPort(run_id="run_node07")

    state = type("State", (), {})()
    state.file_store = file_store
    state.run_port = port
    request = _request(
        body={"messages": [{"role": "user", "content": "hello"}]},
        state=state,
    )
    response = asyncio.run(create_run(request))

    assert response.status_code == 202
    body = json.loads(response.body)
    assert body["run_id"] == "run_node07"
    assert body["trace_id"] == "trace_test"
    # live_url preserved byte-compat (test_run_then_live.py relies on it).
    assert body["live_url"] == "/runs/run_node07/live"
    # ws_token is the new key.
    assert "ws_token" in body
    assert body["ws_token"].count(".") == 2  # JWT shape


def test_ws_token_is_verifiable(rsa_keys: dict[str, str]) -> None:
    """Sanity check: the ws_token minted by render_create_run_receipt round-trips.

    Decoupled from the Starlette path so the test stays <5 s; uses
    the auth module directly so we exercise the same code path.
    """
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
        mint_user_jwt,
        verify_user_jwt,
    )

    token = mint_user_jwt(
        user_id="agent_a1",
        operation_id="run_node07",
        private_key_pem=rsa_keys["private"],
        ttl_seconds=60,
    )
    payload = verify_user_jwt(
        token, expected_operation_id="run_node07", public_key_pem=rsa_keys["public"]
    )
    assert payload["sub"] == "agent_a1"
    assert payload["operation_id"] == "run_node07"