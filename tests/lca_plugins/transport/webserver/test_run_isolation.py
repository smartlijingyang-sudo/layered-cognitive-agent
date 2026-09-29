"""Tests for multi-tenant run control and streaming isolation (ADR-0252).

Verifies fail-closed enforcement across:
- POST /v1/runs/{run_id}/ws-token
- GET /v1/topics/{topic_id}/running-op
- POST /runs/{run_id}/cancel
- POST /runs/{run_id}/answer
- POST /runs/{run_id}/feedback
- WebSocket /v1/runs/{run_id}/ws auth handshake
"""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    answer_run,
    cancel_run,
    record_run_feedback,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunCommandReceipt
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
    _run_session,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    get_running_operation,
    refresh_ws_token,
)


@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    private_key = rsa.generate_key(public_exponent=65537, key_size=2048) if hasattr(rsa, "generate_key") else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    old_sec = os.environ.get("LCA_JWT_SECRET")
    old_pub = os.environ.get("LCA_JWT_PUBLIC_KEY")
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem
    yield {"private": private_pem, "public": public_pem}
    if old_sec is not None:
        os.environ["LCA_JWT_SECRET"] = old_sec
    else:
        os.environ.pop("LCA_JWT_SECRET", None)
    if old_pub is not None:
        os.environ["LCA_JWT_PUBLIC_KEY"] = old_pub
    else:
        os.environ.pop("LCA_JWT_PUBLIC_KEY", None)


class FakeSession:
    def __init__(self, run_id: str, user_id: str, assistant_id: str = "") -> None:
        self.run_id = run_id
        self.user_id = user_id
        self.assistant_id = assistant_id
        self.status = RunLifecycleStatus.PENDING
        self._log: list[Any] = []

    def append(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeRegistry:
    def __init__(self, sessions: dict[str, FakeSession]) -> None:
        self._sessions = sessions

    def get(self, run_id: str) -> FakeSession | None:
        return self._sessions.get(run_id)


def _make_app_state(*, dev_mode: bool, sessions: dict[str, FakeSession] | None = None) -> Any:
    state = type("AppState", (), {})()
    state.lca_auth_dev_mode = dev_mode
    state.lca_auth_expected_token = "test-token"  # noqa: S105
    state.registry = FakeRegistry(sessions or {})
    return state


def _make_http_request(
    path: str,
    *,
    headers: dict[str, str],
    path_params: dict[str, str],
    app_state: Any,
    body: dict[str, Any] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "path_params": path_params,
        "query_string": b"",
        "app": type("App", (), {"state": app_state})(),
    }
    req = Request(scope)
    if body is not None:
        async def _json() -> dict[str, Any]:
            return body
        req.json = _json  # type: ignore[assignment]
    return req


# ── refresh_ws_token tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_ws_token_missing_user_in_non_dev_mode() -> None:
    app_state = _make_app_state(dev_mode=False)
    req = _make_http_request(
        "/v1/runs/run_1/ws-token",
        headers={},
        path_params={"run_id": "run_1"},
        app_state=app_state,
    )
    # Mock stream manager existence
    mock_mgr = MagicMock()
    mock_mgr.exists = AsyncMock(return_value=True)

    from unittest.mock import patch
    with patch(
        "lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http._stream_manager",
        return_value=mock_mgr,
    ):
        resp = await refresh_ws_token(req)
        assert resp.status_code == 401
        data = resp.body.decode()
        assert "missing_user" in data


@pytest.mark.asyncio
async def test_refresh_ws_token_rejects_cross_tenant_user() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    req = _make_http_request(
        "/v1/runs/run_1/ws-token",
        headers={"x-lca-user-id": "user_attacker"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
    )
    mock_mgr = MagicMock()
    mock_mgr.exists = AsyncMock(return_value=True)

    from unittest.mock import patch
    with patch(
        "lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http._stream_manager",
        return_value=mock_mgr,
    ):
        resp = await refresh_ws_token(req)
        assert resp.status_code == 403
        data = resp.body.decode()
        assert "run_not_owned" in data


@pytest.mark.asyncio
async def test_refresh_ws_token_allows_owner() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    req = _make_http_request(
        "/v1/runs/run_1/ws-token",
        headers={"x-lca-user-id": "user_owner"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
    )
    mock_mgr = MagicMock()
    mock_mgr.exists = AsyncMock(return_value=True)

    from unittest.mock import patch
    with patch(
        "lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http._stream_manager",
        return_value=mock_mgr,
    ):
        resp = await refresh_ws_token(req)
        assert resp.status_code == 200
        import json
        payload = json.loads(resp.body.decode())
        assert payload["token_type"] == "Bearer"  # noqa: S105
        assert payload["token"].count(".") == 2


# ── Run control endpoints (cancel, answer, feedback) ────────────────


@pytest.mark.asyncio
async def test_cancel_run_rejects_cross_tenant_user() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    req = _make_http_request(
        "/runs/run_1/cancel",
        headers={"x-lca-user-id": "user_attacker"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
    )
    resp = await cancel_run(req)
    assert resp.status_code == 403
    assert "run_not_owned" in resp.body.decode()


@pytest.mark.asyncio
async def test_cancel_run_allows_owner() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    mock_run_port = MagicMock()
    mock_run_port.cancel = AsyncMock(return_value=RunCommandReceipt(accepted=True, status="canceled"))
    app_state.run_port = mock_run_port

    req = _make_http_request(
        "/runs/run_1/cancel",
        headers={"x-lca-user-id": "user_owner"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
    )
    resp = await cancel_run(req)
    assert resp.status_code == 200
    assert "canceled" in resp.body.decode()


@pytest.mark.asyncio
async def test_answer_run_rejects_cross_tenant_user() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    req = _make_http_request(
        "/runs/run_1/answer",
        headers={"x-lca-user-id": "user_attacker"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
        body={"approval_id": "app_1", "payload": "yes", "idempotency_key": "k1"},
    )
    resp = await answer_run(req)
    assert resp.status_code == 403
    assert "run_not_owned" in resp.body.decode()


@pytest.mark.asyncio
async def test_record_feedback_rejects_cross_tenant_user() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    req = _make_http_request(
        "/runs/run_1/feedback",
        headers={"x-lca-user-id": "user_attacker"},
        path_params={"run_id": "run_1"},
        app_state=app_state,
        body={"text": "good", "rating": "5"},
    )
    resp = await record_run_feedback(req)
    assert resp.status_code == 403
    assert "run_not_owned" in resp.body.decode()


# ── get_running_operation concealed from cross-tenant user ──────────


@pytest.mark.asyncio
async def test_get_running_operation_concealed_for_other_user() -> None:
    session = FakeSession("run_1", user_id="user_owner")
    app_state = _make_app_state(dev_mode=False, sessions={"run_1": session})
    mock_store = MagicMock()
    mock_store.get_latest_for_topic = AsyncMock(
        return_value={"run_id": "run_1", "topic_id": "top_1", "agent_id": "solo"}
    )
    app_state.running_operation_store = mock_store

    req = _make_http_request(
        "/v1/topics/top_1/running-op",
        headers={"x-lca-user-id": "user_attacker"},
        path_params={"topic_id": "top_1"},
        app_state=app_state,
    )
    resp = await get_running_operation(req)
    assert resp.status_code == 200
    import json
    data = json.loads(resp.body.decode())
    assert data["running_operation"] is None


# ── WebSocket handshake token sub verification ──────────────────────


@pytest.mark.asyncio
async def test_ws_handshake_rejects_token_sub_mismatch() -> None:
    # Mint a valid JWT for run_1, but with user_id = attacker
    token = mint_user_jwt(user_id="user_attacker", operation_id="run_1")

    # Mock ws
    ws = MagicMock()
    ws.client = type("Client", (), {"host": "127.0.0.1"})()
    ws.path_params = {"run_id": "run_1"}
    ws.client_state = 1

    # recv auth frame
    ws.receive_text = AsyncMock(
        return_value='{"type": "auth", "token": "' + token + '"}'
    )
    sent_messages: list[dict[str, Any]] = []

    async def _send_json(data: dict[str, Any]) -> None:
        sent_messages.append(data)

    ws.send_json = _send_json

    # Mock stream_manager whose init event belongs to user_owner
    mock_stream_mgr = MagicMock()
    mock_stream_mgr.get_init_event = AsyncMock(
        return_value={"data": {"userId": "user_owner", "agentId": "solo"}}
    )

    await _run_session(
        ws,
        run_id="run_1",
        stream_manager=mock_stream_mgr,
        run_port=None,
    )

    assert len(sent_messages) == 1
    assert sent_messages[0]["type"] == "auth_failed"
    assert "user_id mismatch" in sent_messages[0]["reason"]
