"""Tests for Pre-authorized Pairing State Machine (CONV-INSTALL-1)."""

from __future__ import annotations

import time

from lca.plugins.transport.device_hub.pairing.pairing import (
    DevicePairingService,
    PairingStatus,
)


def test_preauth_code_generation() -> None:
    service = DevicePairingService(ttl_seconds=300)
    req = service.preauth_code(user_id="user-123", workspace_id="ws-456")

    assert req.user_code is not None
    assert len(req.user_code.replace("-", "")) == 8
    assert req.user_id == "user-123"
    assert req.workspace_id == "ws-456"
    assert req.pre_authorized is True
    assert req.status == PairingStatus.AUTHORIZED


def test_preauth_claim_auto_verifies() -> None:
    service = DevicePairingService()
    req = service.preauth_code(user_id="user-123", workspace_id="ws-456")

    claimed = service.claim_preauth(
        user_code=req.user_code,
        device_id="m-testdevice",
        label="Test Laptop",
        platform="Windows",
    )

    assert claimed is not None
    assert claimed.device_id == "m-testdevice"
    assert claimed.label == "Test Laptop"
    assert claimed.platform == "Windows"
    assert claimed.status == PairingStatus.COMPLETED
    assert claimed.machine_token is not None
    assert claimed.machine_token.startswith("mtk-")
    assert claimed.user_id == "user-123"
    assert claimed.workspace_id == "ws-456"

    # Token can authenticate
    auth_req = service.get_by_machine_token(claimed.machine_token)
    assert auth_req is not None
    assert auth_req.device_id == "m-testdevice"


def test_preauth_code_one_time_use() -> None:
    service = DevicePairingService()
    req = service.preauth_code(user_id="user-123", workspace_id="ws-456")

    claimed = service.claim_preauth(
        user_code=req.user_code,
        device_id="m-dev1",
        label="First Laptop",
    )
    assert claimed is not None

    # Second claim attempt must fail
    second_claim = service.claim_preauth(
        user_code=req.user_code,
        device_id="m-dev2",
        label="Second Laptop",
    )
    assert second_claim is None


def test_preauth_code_expiration() -> None:
    service = DevicePairingService(ttl_seconds=1)
    req = service.preauth_code(user_id="user-123", workspace_id="ws-456", expires_in=1)

    time.sleep(1.1)

    claimed = service.claim_preauth(
        user_code=req.user_code,
        device_id="m-dev",
        label="Laptop",
    )
    assert claimed is None
