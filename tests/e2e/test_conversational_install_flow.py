"""End-to-end test for Conversational Local Machine Connection & Auto-Install Flow (CONV-INSTALL-5).

Covers:
1. Conversational intent triggers POST /api/device/pair/preauth to generate one-time userCode and commands.
2. Dynamic download of install.ps1 / install.sh with pre-injected server URL and preauth code.
3. Companion Client auto-pairs using --preauth-code, acquiring machineToken with ZERO manual confirmation.
4. WebSocket connection establishment and device online presence registration.
5. Command execution through LocalExecPort (MachineLocalExecAdapter).
6. Auto-binding and state validation.
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
    download_companion,
    install_ps1,
    install_sh,
    pair_code,
    pair_poll,
    pair_preauth,
    pair_verify,
)
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings
from lca.plugins.transport.device_hub.transport.transport import DeviceTransport


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_conversational_auto_install_and_pairing_flow(tmp_path: Path) -> None:
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
            Route("/api/device/pair/preauth", pair_preauth, methods=["POST", "OPTIONS"]),
            Route("/api/device/install.ps1", install_ps1, methods=["GET", "OPTIONS"]),
            Route("/api/device/install.sh", install_sh, methods=["GET", "OPTIONS"]),
            Route(
                "/api/device/download/companion.py", download_companion, methods=["GET", "OPTIONS"]
            ),
            WebSocketRoute("/api/device/ws", connect_device),
        ],
    )
    app.state.devices = registry
    app.state.device_hub = hub
    app.state.device_pairing = pairing
    app.state.device_settings = settings

    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(0.5)

    try:
        base_url = f"http://127.0.0.1:{port}"

        # 1. Frontend requests preauth pairing code
        preauth_resp = httpx.post(
            f"{base_url}/api/device/pair/preauth",
            json={"userId": "user-bob", "workspaceId": "ws-bob"},
            timeout=5.0,
        )
        assert preauth_resp.status_code == 200
        preauth_data = preauth_resp.json()
        assert preauth_data["success"] is True
        user_code = preauth_data["userCode"]
        assert len(user_code.replace("-", "")) == 8
        windows_cmd = preauth_data["installCommands"]["windows"]
        bash_cmd = preauth_data["installCommands"]["bash"]
        assert user_code in windows_cmd
        assert user_code in bash_cmd

        # 2. Verify installer script downloads
        ps1_resp = httpx.get(f"{base_url}/api/device/install.ps1?code={user_code}", timeout=5.0)
        assert ps1_resp.status_code == 200
        assert f'$PreauthCode = "{user_code}"' in ps1_resp.text

        sh_resp = httpx.get(f"{base_url}/api/device/install.sh?code={user_code}", timeout=5.0)
        assert sh_resp.status_code == 200
        assert f'PREAUTH_CODE="{user_code}"' in sh_resp.text

        # 3. Companion Client auto-pairs using the preauth code
        token_file = tmp_path / "companion_token.json"
        companion_cfg = CompanionConfig(
            server_url=base_url,
            device_id="m-bob-laptop",
            label="Bob's Laptop",
            token_file=token_file,
            allowed_paths=(str(tmp_path),),
        )
        client = CompanionClient(companion_cfg)

        loop_comp = asyncio.new_event_loop()
        stop_event = asyncio.Event()

        # Step 3: Companion auto-pair and connect
        machine_token = loop_comp.run_until_complete(client.auto_pair(user_code))
        assert machine_token.startswith("mtk-")
        assert companion_cfg.machine_token == machine_token

        def run_companion():
            asyncio.set_event_loop(loop_comp)
            loop_comp.run_until_complete(client.connect_and_run(stop_event))

        companion_thread = threading.Thread(target=run_companion, daemon=True)
        companion_thread.start()

        # Wait for device to register online in gateway registry
        for _ in range(50):
            d = registry.get("m-bob-laptop")
            if d and d.online:
                break
            time.sleep(0.05)

        device_entry = registry.get("m-bob-laptop")
        assert device_entry is not None
        assert device_entry.online is True
        assert device_entry.user_id == "user-bob"

        # 4. Wire LCA Port, Adapter & MachineComputer
        transport = DeviceTransport.for_device(registry, hub, "m-bob-laptop")
        assert transport is not None

        plane = PlaneRef(
            id="m-bob-laptop",
            label="Bob's Laptop",
            kind=PlaneKind.MACHINE,
            root=str(tmp_path),
            outputs_dir=str(tmp_path / "outputs"),
            capability_summary=("read_file", "write_file", "run_command", "git"),
        )
        file_store = LocalFileStore(tmp_path / "filestore")
        computer = MachineComputer(plane=plane, transport=transport, store=file_store)
        adapter = MachineLocalExecAdapter(computer, machine_id="m-bob-laptop", label="Bob's Laptop")

        grant = CapabilityGrant(
            job_id="job-auto-01",
            idempotency_key="idem-auto-01",
            subject_user_id="user-bob",
            subject_machine_id="m-bob-laptop",
            operation="run_command",
            path_prefixes=[str(tmp_path)],
            command_class="shell",
            command_allowlist=["echo"],
            expires_at=int(time.time()) + 300,
            approval_id=None,
            request_digest="digest-auto-01",
        )

        fut = asyncio.run_coroutine_threadsafe(
            adapter.execute(
                "run_command", {"command": "echo 'conversational install working!'"}, grant
            ),
            app.state.loop,
        )
        receipt: EffectReceipt = fut.result(timeout=10)
        assert isinstance(receipt, EffectReceipt)
        assert receipt.success is True
        assert receipt.exit_code == 0
        assert receipt.stdout_digest is not None
        assert adapter.target.kind == TargetKind.USER_MACHINE

        # 5. File write operation
        test_file = tmp_path / "greeting.txt"
        fut_write = asyncio.run_coroutine_threadsafe(
            adapter.execute(
                "write_file",
                {"path": str(test_file), "content": "Hello from LCA Conversational Auto-Install!"},
                grant,
            ),
            app.state.loop,
        )
        receipt_write: EffectReceipt = fut_write.result(timeout=10)
        assert receipt_write.success is True
        assert (
            test_file.read_text(encoding="utf-8") == "Hello from LCA Conversational Auto-Install!"
        )

        # Teardown companion
        stop_event.set()
        companion_thread.join(timeout=3.0)

    finally:
        server.should_exit = True
        server_thread.join(timeout=3.0)
