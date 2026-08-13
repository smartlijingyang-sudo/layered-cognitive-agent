"""Presence + Console HTTP/WS surface on the real Starlette app."""

from __future__ import annotations

from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.console.sessions import ConsoleBook
from gateway.presence.registry import PresenceRegistry
from gateway.presence.settings import PresenceSettings
from gateway.presence.wire import HELLO, PTY_INPUT, PTY_OPEN, PTY_OUTPUT, WELCOME
from tests.support.gateway_scripted import ScriptedLLMResolver

_TOKEN = "test-host-token"  # noqa: S105


def _app() -> tuple[object, PresenceRegistry, ConsoleBook]:
    presence = PresenceRegistry()
    consoles = ConsoleBook()
    app = create_app(
        llm_resolver=ScriptedLLMResolver(),
        presence=presence,
        consoles=consoles,
        presence_settings=PresenceSettings(token=_TOKEN, subject="dev"),
    )
    return app, presence, consoles


def test_list_devices_empty() -> None:
    app, _presence, _book = _app()
    with TestClient(app) as client:
        resp = client.get("/presence/devices")
        assert resp.status_code == 200
        assert resp.json() == {"devices": []}


def test_create_session_offline_409() -> None:
    app, _presence, _book = _app()
    with TestClient(app) as client:
        resp = client.post("/console/sessions", json={"device_id": "local-host"})
        assert resp.status_code == 409


def test_host_hello_and_console_roundtrip() -> None:
    app, presence, _book = _app()
    with TestClient(app) as client, client.websocket_connect("/presence/connect") as host_ws:
        host_ws.send_json(
            {
                "type": HELLO,
                "device_id": "local-host",
                "token": _TOKEN,
                "name": "test-box",
                "capabilities": ["console"],
            }
        )
        welcome = host_ws.receive_json()
        assert welcome["type"] == WELCOME
        listed = client.get("/presence/devices").json()["devices"]
        assert listed[0]["device_id"] == "local-host"
        assert listed[0]["status"] == "online"
        assert presence.summary()["online"] == 1

        created = client.post("/console/sessions", json={"device_id": "local-host"})
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        opened = host_ws.receive_json()
        assert opened["type"] == PTY_OPEN
        assert opened["session_id"] == session_id

        with client.websocket_connect(f"/console/sessions/{session_id}") as term:
            term.send_json({"type": "input", "data": "pwd\n"})
            forwarded = host_ws.receive_json()
            assert forwarded["type"] == PTY_INPUT
            assert forwarded["data"] == "pwd\n"
            host_ws.send_json({"type": PTY_OUTPUT, "session_id": session_id, "data": "ok\n"})
            out = term.receive_json()
            assert out == {"type": "output", "data": "ok\n"}


def test_reconnect_does_not_offline_new_channel() -> None:
    app, presence, _book = _app()
    with TestClient(app) as client, client.websocket_connect("/presence/connect") as first:
        first.send_json(
            {
                "type": HELLO,
                "device_id": "local-host",
                "token": _TOKEN,
                "name": "a",
                "capabilities": ["console"],
            }
        )
        assert first.receive_json()["type"] == WELCOME
        with client.websocket_connect("/presence/connect") as second:
            second.send_json(
                {
                    "type": HELLO,
                    "device_id": "local-host",
                    "token": _TOKEN,
                    "name": "b",
                    "capabilities": ["console"],
                }
            )
            assert second.receive_json()["type"] == WELCOME
            first.close()
            listed = client.get("/presence/devices").json()["devices"]
            assert listed[0]["status"] == "online"
            assert presence.channel("local-host") is not None


def test_host_bad_token_rejected() -> None:
    app, _presence, _book = _app()
    with TestClient(app) as client, client.websocket_connect("/presence/connect") as host_ws:
        host_ws.send_json({"type": HELLO, "device_id": "x", "token": "wrong", "name": "x"})
        try:
            host_ws.receive_json()
            raised = False
        except Exception:
            raised = True
        assert raised
