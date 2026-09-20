"""End-to-end full flow test for User-Machine Side-Effect Plane (ADR-0246 M1-M4).

Covers:
1. Device Code Pairing flow (RFC 8628) between Companion and LCA Gateway.
2. Machine token issuance and validation.
3. WebSocket handshake, heartbeat, and online registration in DeviceRegistry.
4. Side-effect command execution through LocalExecPort (MachineLocalExecAdapter).
5. File write and read operations across the machine boundary.
6. CapabilityGrant boundary enforcement (expiration, scope restriction, device offline).
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute

from lca.contracts.models.core.execution.local_exec import (
    CapabilityGrant,
    EffectReceipt,
    TargetKind,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.computer.companion.client import CompanionClient, CompanionConfig
from lca.infrastructure.computer.machine.adapter import MachineLocalExecAdapter
from lca.infrastructure.computer.machine.machine import MachineComputer
from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.device_hub.hub.hub import DeviceHub
from lca.plugins.transport.device_hub.pairing.pairing import DevicePairingService
from lca.plugins.transport.device_hub.registry.registry import DeviceRegistry
from lca.plugins.transport.device_hub.routes.routes import (
    connect_device,
    pair_code,
    pair_poll,
    pair_verify,
)
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings
from lca.plugins.transport.device_hub.transport.transport import DeviceTransport


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_user_machine_full_pairing_and_execution_flow(tmp_path: Path) -> None:
    port = _get_free_port()
    registry = DeviceRegistry(tmp_path / "devices.db")
    hub = DeviceHub(registry)
    pairing = DevicePairingService()
    settings = DeviceHubSettings(service_token="test-service-token")  # noqa: S106

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.loop = asyncio.get_running_loop()
        yield

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/api/device/pair/code", pair_code, methods=["POST", "OPTIONS"]),
            Route("/api/device/pair/verify", pair_verify, methods=["POST", "OPTIONS"]),
            Route("/api/device/pair/poll", pair_poll, methods=["POST", "OPTIONS"]),
            WebSocketRoute("/api/device/ws", connect_device),
        ],
    )
    app.state.devices = registry
    app.state.device_hub = hub
    app.state.device_pairing = pairing
    app.state.device_settings = settings

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    while not getattr(server, "started", False):
        time.sleep(0.01)

    base_url = f"http://10.36.6.252:{port}"
    device_id = "m-alice-mbp"
    label = "Alice MacBook Pro"

    try:
        # =========================================================================
        # Phase 1: Device Code Pairing (RFC 8628)
        # =========================================================================
        # 1. Companion requests code
        resp_code = httpx.post(
            f"{base_url}/api/device/pair/code",
            json={"deviceId": device_id, "label": label, "platform": "darwin"},
        )
        assert resp_code.status_code == 200
        code_data = resp_code.json()
        device_code = code_data["deviceCode"]
        user_code = code_data["userCode"]
        assert len(user_code.replace("-", "")) == 8

        # 2. Companion polls before verify -> pending
        resp_poll_pending = httpx.post(
            f"{base_url}/api/device/pair/poll",
            json={"deviceCode": device_code},
        )
        assert resp_poll_pending.status_code == 200
        assert resp_poll_pending.json()["status"] == "authorization_pending"

        # 3. User verifies in frontend
        resp_verify = httpx.post(
            f"{base_url}/api/device/pair/verify",
            json={"userCode": user_code, "userId": "user-alice", "workspaceId": "ws-main"},
        )
        assert resp_verify.status_code == 200
        assert resp_verify.json()["success"] is True
        assert resp_verify.json()["deviceId"] == device_id

        # 4. Companion polls again -> success with machine token
        resp_poll_success = httpx.post(
            f"{base_url}/api/device/pair/poll",
            json={"deviceCode": device_code},
        )
        assert resp_poll_success.status_code == 200
        poll_data = resp_poll_success.json()
        assert poll_data["status"] == "success"
        machine_token = poll_data["machineToken"]
        assert machine_token.startswith("mtk-")

        # 5. Save and reload token
        token_file = tmp_path / "companion_token.json"
        comp_cfg = CompanionConfig(
            server_url=base_url,
            device_id=device_id,
            label=label,
            token_file=token_file,
            allowed_paths=(str(tmp_path),),
        )
        comp_cfg.save_token(machine_token, user_id="user-alice", workspace_id="ws-main")
        companion_client = CompanionClient(comp_cfg)
        assert companion_client.config.machine_token == machine_token

        # =========================================================================
        # Phase 2: Live Companion WebSocket Connection
        # =========================================================================
        stop_event = asyncio.Event()
        loop_comp = asyncio.new_event_loop()

        def run_companion():
            asyncio.set_event_loop(loop_comp)
            loop_comp.run_until_complete(companion_client.connect_and_run(stop_event))

        companion_thread = threading.Thread(target=run_companion, daemon=True)
        companion_thread.start()

        # Wait for device to register online in gateway registry
        for _ in range(50):
            d = registry.get(device_id)
            if d and d.online:
                break
            time.sleep(0.05)

        device_entry = registry.get(device_id)
        assert device_entry is not None
        assert device_entry.online is True
        assert device_entry.user_id == "user-alice"

        # =========================================================================
        # Phase 3: Wire LCA Port, Adapter & MachineComputer
        # =========================================================================
        transport = DeviceTransport.for_device(registry, hub, device_id)
        assert transport is not None

        plane = PlaneRef(
            id=device_id,
            label=label,
            kind=PlaneKind.MACHINE,
            root=str(tmp_path),
            outputs_dir=str(tmp_path / "outputs"),
            capability_summary=("read_file", "write_file", "run_command", "git"),
        )
        file_store = LocalFileStore(tmp_path / "files")
        computer = MachineComputer(plane=plane, transport=transport, store=file_store)
        adapter = MachineLocalExecAdapter(computer, machine_id=device_id, label=label)

        assert adapter.target.kind == TargetKind.USER_MACHINE
        assert adapter.target.id == device_id

        # =========================================================================
        # Phase 4: Execute Command via LocalExecPort
        # =========================================================================
        grant = CapabilityGrant(
            job_id="job-e2e-01",
            idempotency_key="idem-01",
            subject_user_id="user-alice",
            subject_machine_id=device_id,
            operation="run_command",
            path_prefixes=[str(tmp_path)],
            command_class="shell",
            command_allowlist=["echo"],
            expires_at=int(time.time()) + 300,
            approval_id=None,
            request_digest="digest-e2e-01",
        )

        fut = asyncio.run_coroutine_threadsafe(
            adapter.execute("run_command", {"command": "echo 'HELLO_LCA_E2E'"}, grant),
            app.state.loop,
        )
        receipt: EffectReceipt = fut.result(timeout=10)

        assert receipt.success is True
        assert receipt.exit_code == 0
        assert receipt.error_kind is None
        assert receipt.stdout_digest is not None
        assert receipt.stdout_digest.startswith("sha256-")

        # =========================================================================
        # Phase 5: Execute File Write and Read
        # =========================================================================
        test_file = tmp_path / "e2e_verified.txt"
        fut_write = asyncio.run_coroutine_threadsafe(
            adapter.execute(
                "write_file",
                {"path": str(test_file), "content": "ADR-0246 E2E Verified!"},
                grant,
            ),
            app.state.loop,
        )
        receipt_write: EffectReceipt = fut_write.result(timeout=10)
        assert receipt_write.success is True
        assert test_file.read_text(encoding="utf-8") == "ADR-0246 E2E Verified!"

        fut_read = asyncio.run_coroutine_threadsafe(
            adapter.execute("read_file", {"path": str(test_file)}, grant),
            app.state.loop,
        )
        receipt_read: EffectReceipt = fut_read.result(timeout=10)
        assert receipt_read.success is True

        # =========================================================================
        # Phase 6: Security & Policy Enforcement
        # =========================================================================
        # 1. Expired grant rejection
        expired_grant = CapabilityGrant(
            job_id="job-exp",
            idempotency_key="idem-exp",
            subject_user_id="user-alice",
            subject_machine_id=device_id,
            operation="run_command",
            path_prefixes=[str(tmp_path)],
            command_class="shell",
            command_allowlist=["echo"],
            expires_at=int(time.time()) - 10,
            approval_id=None,
            request_digest="digest-exp",
        )
        fut_exp = asyncio.run_coroutine_threadsafe(
            adapter.execute("run_command", {"command": "echo bad"}, expired_grant),
            app.state.loop,
        )
        rec_exp = fut_exp.result(timeout=5)
        assert rec_exp.success is False
        assert rec_exp.error_kind == "grant_expired"

        # 2. Scope boundary violation (path outside granted prefixes)
        fut_scope = asyncio.run_coroutine_threadsafe(
            adapter.execute("read_file", {"path": "/etc/shadow"}, grant),
            app.state.loop,
        )
        rec_scope = fut_scope.result(timeout=5)
        assert rec_scope.success is False
        assert rec_scope.error_kind == "scope_violation"

        # =========================================================================
        # Phase 7: Disconnect & Offline Device Handling
        # =========================================================================
        loop_comp.call_soon_threadsafe(stop_event.set)
        companion_thread.join(timeout=3)

        # Allow gateway to detect offline
        for _ in range(50):
            d = registry.get(device_id)
            if d and not d.online:
                break
            time.sleep(0.05)

        fut_off = asyncio.run_coroutine_threadsafe(
            adapter.execute("run_command", {"command": "echo offline"}, grant),
            app.state.loop,
        )
        rec_off = fut_off.result(timeout=5)
        assert rec_off.success is False
        assert rec_off.error_kind == "device_offline"

    finally:
        server.should_exit = True
        server_thread.join(timeout=3)
