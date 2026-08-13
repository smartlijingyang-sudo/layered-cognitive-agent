"""HostSandbox RPCs through ExecHub onto handle_exec."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gateway.host_sandbox import HostSandbox
from gateway.presence.models import CAP_SANDBOX, Device
from gateway.presence.registry import PresenceRegistry
from gateway.presence.rpc import ExecHub
from gateway.presence.wire import EXEC_CALL, EXEC_RESULT
from host.exec import handle_exec


class _Loopback:
    def __init__(self, hub: ExecHub, workspace: Path) -> None:
        self._hub = hub
        self._workspace = workspace

    async def send(self, payload: dict[str, Any]) -> None:
        if payload.get("type") != EXEC_CALL:
            return
        body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        result = await handle_exec(str(payload.get("op") or ""), body, self._workspace)
        self._hub.complete(
            {
                "type": EXEC_RESULT,
                "call_id": payload.get("call_id"),
                "ok": result.get("success", False),
                "result": result,
            }
        )


@pytest.mark.asyncio
async def test_run_terminal_on_host(tmp_path: Path) -> None:
    presence = PresenceRegistry()
    hub = ExecHub()
    presence.online(
        Device(device_id="local-host", subject="u", name="box", capabilities=(CAP_SANDBOX,)),
        _Loopback(hub, tmp_path),
    )
    sandbox = HostSandbox.from_presence(presence, hub)
    assert sandbox is not None
    result = await sandbox.run_terminal("printf hi", timeout_s=5)
    assert result.success
    assert result.stdout == "hi"


def test_from_presence_none_when_offline() -> None:
    assert HostSandbox.from_presence(PresenceRegistry(), ExecHub()) is None
