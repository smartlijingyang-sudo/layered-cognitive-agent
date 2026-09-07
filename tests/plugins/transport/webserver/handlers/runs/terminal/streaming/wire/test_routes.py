"""Tests for the LcaAgentGateway wire route catalog and WS mount."""
from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.routes import (
    ROUTE_SPECS,
    RUNNING_OP_PATH,
    WS_PATH,
    WS_TOKEN_PATH,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.ws import (
    mount_ws_route,
)


@pytest.fixture(scope="module", autouse=True)
def rsa_keys_module():
    """Generate a fresh RSA key pair for the test module (mirrors L2 pattern)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem
    return {"private": private_pem, "public": public_pem}


def test_ws_path_is_in_route_specs() -> None:
    """The WS path appears in ROUTE_SPECS for documentation / discovery."""
    paths = [spec.path for spec in ROUTE_SPECS]
    assert WS_PATH in paths, paths
    assert WS_PATH == "/v1/runs/{run_id}/ws"


def test_ws_token_path_is_in_route_specs() -> None:
    assert WS_TOKEN_PATH in [spec.path for spec in ROUTE_SPECS]
    assert WS_TOKEN_PATH == "/v1/runs/{run_id}/ws-token"  # noqa: S105 (path literal)


def test_running_op_path_is_in_route_specs() -> None:
    assert RUNNING_OP_PATH in [spec.path for spec in ROUTE_SPECS]
    assert RUNNING_OP_PATH == "/v1/topics/{topic_id}/running-op"


def test_mount_ws_route_makes_ws_reachable() -> None:
    """mount_ws_route appends a WebSocketRoute that the Starlette TestClient can dial."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    received: list[str] = []

    async def fake_handler(ws: WebSocket) -> None:
        await ws.accept()
        msg = await ws.receive_text()
        received.append(msg)
        await ws.send_text(f"echo:{msg}")
        await ws.close()

    async def probe(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/probe", probe, methods=["GET"])])
    mount_ws_route(app, handler=fake_handler)

    with TestClient(app) as client, client.websocket_connect("/v1/runs/abc/ws") as ws:
        ws.send_text("hello")
        assert ws.receive_text() == "echo:hello"

    assert received == ["hello"]


def test_mount_ws_route_duplicate_path_raises() -> None:
    """Mounting the same WS path twice must raise at setup time.

    The implementation checks existing routes before appending; a dup
    mount is a boot misconfiguration and must be visible immediately.
    """
    from starlette.applications import Starlette

    async def handler(ws: WebSocket) -> None:
        await ws.accept()
        await ws.close()

    app = Starlette()
    mount_ws_route(app, handler=handler)
    with pytest.raises(RuntimeError, match="already mounted"):
        mount_ws_route(app, handler=handler)
