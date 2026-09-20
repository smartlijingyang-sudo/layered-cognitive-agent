"""RFC 8628 Device Code 配对状态机与端点测试 (ADR-0246 M2)."""

from __future__ import annotations

from lca.plugins.transport.device_hub.pairing.pairing import DevicePairingService


def test_request_pairing_code() -> None:
    service = DevicePairingService()
    req = service.request_code(device_id="m-01", label="Alice-PC", platform="windows")
    assert req.device_code
    assert len(req.user_code.replace("-", "")) == 8
    assert len(req.user_code) == 9
    assert req.expires_in > 0


def test_poll_before_verify() -> None:
    service = DevicePairingService()
    req = service.request_code(device_id="m-01", label="Alice-PC", platform="windows")
    res = service.poll_token(req.device_code)
    assert res.status == "authorization_pending"
    assert res.machine_token is None


def test_verify_and_poll_success() -> None:
    service = DevicePairingService()
    req = service.request_code(device_id="m-01", label="Alice-PC", platform="windows")

    # User enters user_code in UI
    verify_res = service.verify_code(
        user_code=req.user_code,
        user_id="u-alice",
        workspace_id="ws-main",
    )
    assert verify_res.success is True
    assert verify_res.device_id == "m-01"

    # Companion polls token
    poll_res = service.poll_token(req.device_code)
    assert poll_res.status == "success"
    assert poll_res.machine_token is not None
    assert poll_res.machine_token.startswith("mtk-")
    assert poll_res.user_id == "u-alice"
    assert poll_res.workspace_id == "ws-main"


def test_verify_invalid_code() -> None:
    service = DevicePairingService()
    res = service.verify_code(user_code="INVALID1", user_id="u-alice", workspace_id="ws-main")
    assert res.success is False
    assert res.error == "invalid_code"


def test_expired_pairing() -> None:
    service = DevicePairingService(ttl_seconds=-1)
    req = service.request_code(device_id="m-01", label="Alice-PC", platform="windows")

    verify_res = service.verify_code(
        user_code=req.user_code, user_id="u-alice", workspace_id="ws-main"
    )
    assert verify_res.success is False
    assert verify_res.error == "expired"

    poll_res = service.poll_token(req.device_code)
    assert poll_res.status == "expired"


def test_device_pairing_http_flow() -> None:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from lca.plugins.transport.device_hub.routes.routes import (
        pair_code,
        pair_poll,
        pair_verify,
    )

    app = Starlette(
        routes=[
            Route("/api/device/pair/code", pair_code, methods=["POST", "OPTIONS"]),
            Route("/api/device/pair/verify", pair_verify, methods=["POST", "OPTIONS"]),
            Route("/api/device/pair/poll", pair_poll, methods=["POST", "OPTIONS"]),
        ]
    )
    client = TestClient(app)

    # 1. Request code
    resp = client.post(
        "/api/device/pair/code",
        json={"deviceId": "dev-01", "label": "Bob-MacBook", "platform": "darwin"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deviceCode" in data
    assert "userCode" in data
    device_code = data["deviceCode"]
    user_code = data["userCode"]

    # 2. Poll before verification -> authorization_pending
    resp_poll = client.post("/api/device/pair/poll", json={"deviceCode": device_code})
    assert resp_poll.status_code == 200
    assert resp_poll.json()["status"] == "authorization_pending"

    # 3. Verify via user
    resp_verify = client.post(
        "/api/device/pair/verify",
        json={"userCode": user_code, "userId": "user-bob", "workspaceId": "ws-bob"},
    )
    assert resp_verify.status_code == 200
    assert resp_verify.json()["success"] is True
    assert resp_verify.json()["deviceId"] == "dev-01"

    # 4. Poll again -> success with machine token
    resp_poll2 = client.post("/api/device/pair/poll", json={"deviceCode": device_code})
    assert resp_poll2.status_code == 200
    poll2_data = resp_poll2.json()
    assert poll2_data["status"] == "success"
    assert poll2_data["machineToken"].startswith("mtk-")
    assert poll2_data["userId"] == "user-bob"
    assert poll2_data["workspaceId"] == "ws-bob"
