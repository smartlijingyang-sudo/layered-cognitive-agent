"""Tests for new /v1/sessions/* API routes (B.4)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from lca.contracts.harness.command import (
    AnswerCommand,
    CancelCommand,
    CommandReceipt,
    MessageSendCommand,
    SessionCreateCommand,
    SteerCommand,
)
from lca.contracts.harness.projection import ProjectionChange, ProjectionSnapshot
from lca.plugins.gateway_starlette.session_routes import create_session_router


def _make_receipt(**overrides) -> CommandReceipt:
    defaults = {
        "command_id": "cmd-1",
        "session_id": "sess-1",
        "seq": 1,
        "accepted": True,
        "rejection_reason": None,
    }
    defaults.update(overrides)
    return CommandReceipt(**defaults)


class _FakeGateway:
    """Minimal in-memory stand-in for CommandGateway."""

    def __init__(self) -> None:
        self.handle_create_session = AsyncMock(return_value=_make_receipt())
        self.handle_send_message = AsyncMock(return_value=_make_receipt())
        self.get_snapshot = AsyncMock(
            return_value=ProjectionSnapshot(as_of_seq=7, values={"foo": "bar"})
        )
        self.handle_answer = AsyncMock(return_value=_make_receipt())
        self.handle_cancel = AsyncMock(return_value=_make_receipt())
        self.handle_steer = AsyncMock(return_value=_make_receipt())
        self.subscribe_changes = AsyncMock()  # replaced in SSE test


def _make_app(gateway=None):
    gw = gateway or _FakeGateway()
    router = create_session_router(gw)
    app = Starlette(routes=[Mount("/v1", routes=router.routes)])
    app.state.command_gateway = gw
    return app, gw


def _wrap_gateway_for_sse_test() -> tuple[_FakeGateway, list[str]]:
    """Return gateway whose subscribe_changes records call args and yields."""
    gw = _FakeGateway()
    calls: list[tuple[str, int]] = []

    async def _stream(session_id: str, last_seq: int) -> AsyncIterator[ProjectionChange]:
        calls.append((session_id, last_seq))
        yield ProjectionChange(
            session_id=session_id,
            key="messages",
            version=1,
            seq=last_seq + 1,
            value={"text": "hi"},
        )

    gw.subscribe_changes = _stream  # type: ignore[assignment]
    return gw, calls  # type: ignore[return-value]


class TestSessionRoutesRegistered:
    """All 7 routes are registered on the router."""

    def test_create_session_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any(p.endswith("/sessions") for p in paths)

    def test_send_message_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("messages" in p for p in paths)

    def test_snapshot_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("snapshot" in p for p in paths)

    def test_events_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("events" in p for p in paths)

    def test_answer_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("commands/answer" in p for p in paths)

    def test_cancel_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("commands/cancel" in p for p in paths)

    def test_steer_route_exists(self) -> None:
        app, _ = _make_app()
        paths = self._collect_paths(app)
        assert any("commands/steer" in p for p in paths)

    @staticmethod
    def _collect_paths(app: Starlette) -> list[str]:
        out: list[str] = []

        def _walk(routes) -> None:
            for r in routes:
                if hasattr(r, "path"):
                    out.append(r.path)
                if hasattr(r, "routes"):
                    _walk(r.routes)

        _walk(app.routes)
        return out


class TestSessionRoutesDispatch:
    """Routes dispatch to the gateway and return correct payloads."""

    def test_create_session_dispatches(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.post(
            "/v1/sessions",
            json={
                "idempotency_key": "idem-1",
                "profile": "web-standard",
                "preset": "default",
            },
        )
        assert response.status_code == 201
        assert response.json() == {
            "session_id": "sess-1",
            "seq": 1,
            "accepted": True,
        }
        gw.handle_create_session.assert_awaited_once()
        cmd: SessionCreateCommand = gw.handle_create_session.call_args.args[0]
        assert isinstance(cmd, SessionCreateCommand)
        assert cmd.idempotency_key == "idem-1"
        assert cmd.profile == "web-standard"

    def test_send_message_dispatches(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.post(
            "/v1/sessions/sess-1/messages",
            json={"content": "hello", "idempotency_key": "idem-2"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "session_id": "sess-1",
            "seq": 1,
            "accepted": True,
        }
        gw.handle_send_message.assert_awaited_once()
        cmd: MessageSendCommand = gw.handle_send_message.call_args.args[0]
        assert cmd.session_id == "sess-1"
        assert cmd.content == "hello"
        assert cmd.role == "user"

    def test_snapshot_returns_values(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.get("/v1/sessions/sess-1/snapshot")
        assert response.status_code == 200
        assert response.json() == {"as_of_seq": 7, "values": {"foo": "bar"}}
        gw.get_snapshot.assert_awaited_once_with("sess-1")

    def test_events_streams_sse(self) -> None:
        gw, calls = _wrap_gateway_for_sse_test()
        app, _ = _make_app(gw)
        client = TestClient(app)
        with client.stream(
            "GET", "/v1/sessions/sess-1/events?last_seq=5"
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = b"".join(response.iter_bytes()).decode("utf-8")
        assert "event: projection" in body
        parsed = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0])
        assert parsed["seq"] == 6
        assert calls == [("sess-1", 5)]

    def test_answer_dispatches(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.post(
            "/v1/sessions/sess-1/commands/answer",
            json={"answer": "yes"},
        )
        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        gw.handle_answer.assert_awaited_once()
        cmd: AnswerCommand = gw.handle_answer.call_args.args[0]
        assert cmd.answer == "yes"

    def test_cancel_dispatches(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.post(
            "/v1/sessions/sess-1/commands/cancel",
            json={"keep_inbox": False},
        )
        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        gw.handle_cancel.assert_awaited_once()
        cmd: CancelCommand = gw.handle_cancel.call_args.args[0]
        assert cmd.keep_inbox is False

    def test_steer_dispatches(self) -> None:
        app, gw = _make_app()
        client = TestClient(app)
        response = client.post(
            "/v1/sessions/sess-1/commands/steer",
            json={"content": "focus on X"},
        )
        assert response.status_code == 200
        assert response.json() == {"accepted": True}
        gw.handle_steer.assert_awaited_once()
        cmd: SteerCommand = gw.handle_steer.call_args.args[0]
        assert cmd.content == "focus on X"
