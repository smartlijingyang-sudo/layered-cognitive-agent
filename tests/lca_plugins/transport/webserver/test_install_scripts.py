"""Tests for dynamic installer scripts and preauth endpoints (CONV-INSTALL-2)."""

from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from lca.plugins.transport.device_hub.pairing.pairing import DevicePairingService
from lca.plugins.transport.device_hub.routes.routes import (
    install_ps1,
    install_sh,
    pair_preauth,
)


class _FakeApp:
    def __init__(self) -> None:
        class _State:
            pass

        self.state = _State()
        self.state.device_pairing = DevicePairingService()


def _make_request(
    path: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    body: bytes = b"",
) -> Request:
    raw_headers = [
        (k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": "&".join(f"{k}={v}" for k, v in (query_params or {}).items()).encode(
            "utf-8"
        )
        if query_params
        else b"",
        "app": _FakeApp(),
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_pair_preauth_returns_commands() -> None:
    req = _make_request(
        "/api/device/pair/preauth",
        method="POST",
        headers={"host": "10.36.6.252:8765"},
        body=b'{"userId": "alice", "workspaceId": "ws-1"}',
    )
    resp = await pair_preauth(req)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    import json

    data = json.loads(resp.body.decode("utf-8"))
    assert data["success"] is True
    assert "userCode" in data
    assert "installCommands" in data
    cmds = data["installCommands"]
    assert "windows" in cmds
    assert "bash" in cmds
    assert "10.36.6.252:8765" in cmds["windows"]
    assert data["userCode"] in cmds["windows"]
    assert "10.36.6.252:8765" in cmds["bash"]
    assert data["userCode"] in cmds["bash"]


@pytest.mark.asyncio
async def test_install_ps1_renders_template() -> None:
    req = _make_request(
        "/api/device/install.ps1",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
        query_params={"code": "TEST-1234"},
    )
    resp = await install_ps1(req)
    assert isinstance(resp, Response)
    assert resp.status_code == 200
    text = resp.body.decode("utf-8")
    assert '$Server = "http://10.36.6.252:8765"' in text
    assert '$PreauthCode = "TEST-1234"' in text
    assert "Start-Process" in text

    # Behavioral invariants: Python auto-detection & auto-install
    assert "function Test-PythonCandidate" in text
    assert "function Update-SessionPath" in text
    assert "function Find-Python" in text
    assert "HKCU:\\Software\\Python\\PythonCore" in text
    assert "Programs\\Python" in text
    assert "winget install --id Python.Python.3.11 --source winget" in text
    assert "python-3.11.9" in text
    assert "InstallAllUsers=0" in text
    assert "--user" in text


@pytest.mark.asyncio
async def test_install_sh_renders_template() -> None:
    req = _make_request(
        "/api/device/install.sh",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
        query_params={"code": "TEST-1234"},
    )
    resp = await install_sh(req)
    assert isinstance(resp, Response)
    assert resp.status_code == 200
    text = resp.body.decode("utf-8")
    assert 'SERVER="http://10.36.6.252:8765"' in text
    assert 'PREAUTH_CODE="TEST-1234"' in text
    assert "nohup" in text

    # Behavioral invariants: Linux/macOS Python detection & auto-install
    assert "find_python()" in text
    assert "sys.version_info >= (3, 10)" in text
    assert "apt-get" in text
    assert "brew" in text
    assert "--user" in text


@pytest.mark.asyncio
async def test_install_ps1_contains_fast_path_and_autostart() -> None:
    req = _make_request(
        "/api/device/install.ps1",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
        query_params={"code": "FAST-TEST"},
    )
    resp = await install_ps1(req)
    assert resp.status_code == 200
    text = resp.body.decode("utf-8")
    assert "Fast-Path" in text
    assert "companion_token.json" in text
    assert "Startup" in text


@pytest.mark.asyncio
async def test_download_runner_bat_endpoint() -> None:
    from lca.plugins.transport.device_hub.routes.routes import download_runner_bat

    req = _make_request(
        "/api/device/download/runner.bat",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
        query_params={"code": "BAT-TEST"},
    )
    resp = await download_runner_bat(req)
    assert resp.status_code == 200
    assert 'attachment; filename="lca-runner.bat"' in resp.headers.get("content-disposition", "")
    text = resp.body.decode("utf-8")
    assert "BAT-TEST" in text
    assert "powershell" in text.lower()


@pytest.mark.asyncio
async def test_download_runner_command_endpoint() -> None:
    from lca.plugins.transport.device_hub.routes.routes import download_runner_command

    req = _make_request(
        "/api/device/download/runner.command",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
        query_params={"code": "CMD-TEST"},
    )
    resp = await download_runner_command(req)
    assert resp.status_code == 200
    assert 'attachment; filename="lca-runner.command"' in resp.headers.get("content-disposition", "")
    text = resp.body.decode("utf-8")
    assert "CMD-TEST" in text
    assert "/bin/bash" in text


@pytest.mark.asyncio
async def test_download_runner_auto_generates_code_when_omitted() -> None:
    from lca.plugins.transport.device_hub.routes.routes import (
        download_runner_bat,
        download_runner_command,
    )

    req_bat = _make_request(
        "/api/device/download/runner.bat",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
    )
    resp_bat = await download_runner_bat(req_bat)
    assert resp_bat.status_code == 200
    text_bat = resp_bat.body.decode("utf-8")
    assert "?code=" in text_bat
    assert "?code='" not in text_bat  # not empty!

    req_cmd = _make_request(
        "/api/device/download/runner.command",
        method="GET",
        headers={"host": "10.36.6.252:8765"},
    )
    resp_cmd = await download_runner_command(req_cmd)
    assert resp_cmd.status_code == 200
    text_cmd = resp_cmd.body.decode("utf-8")
    assert "?code=" in text_cmd
    assert '?code="' not in text_cmd  # not empty!

