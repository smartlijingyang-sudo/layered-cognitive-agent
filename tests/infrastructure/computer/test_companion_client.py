"""Tests for CompanionClient (ADR-0246 M3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.computer.companion.client import CompanionClient, CompanionConfig


def test_companion_config_token_save_and_load(tmp_path: Path) -> None:
    token_file = tmp_path / "companion_token.json"
    cfg = CompanionConfig(
        device_id="dev-test",
        label="Test Machine",
        token_file=token_file,
    )
    assert cfg.load_token() is None

    cfg.save_token("mtk-123456", user_id="user-1", workspace_id="ws-1")
    assert token_file.exists()

    cfg2 = CompanionConfig(token_file=token_file)
    token = cfg2.load_token()
    assert token == "mtk-123456"  # noqa: S105
    assert cfg2.device_id == "dev-test"
    assert cfg2.label == "Test Machine"


@pytest.mark.asyncio
async def test_companion_run_command_success(tmp_path: Path) -> None:
    client = CompanionClient(CompanionConfig(allowed_paths=(str(tmp_path),)))
    res = await client.dispatch_tool(
        "runCommand", {"command": "echo 'hello companion'", "cwd": str(tmp_path)}
    )
    assert res["success"] is True
    assert "hello companion" in res["stdout"]
    assert res["exit_code"] == 0


@pytest.mark.asyncio
async def test_companion_run_command_disabled(tmp_path: Path) -> None:
    client = CompanionClient(CompanionConfig(allow_commands=False))
    res = await client.dispatch_tool("runCommand", {"command": "echo 'fail'", "cwd": str(tmp_path)})
    assert res["success"] is False
    assert res["error"] == "commands_disabled"


@pytest.mark.asyncio
async def test_companion_allowed_paths_enforcement(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_dir = tmp_path / "forbidden"
    forbidden_dir.mkdir()

    client = CompanionClient(CompanionConfig(allowed_paths=(str(allowed_dir),)))

    # Allowed path write
    res = await client.dispatch_tool(
        "writeFile",
        {"path": str(allowed_dir / "foo.txt"), "content": "allowed content"},
    )
    assert res["success"] is True
    assert (allowed_dir / "foo.txt").read_text() == "allowed content"

    # Forbidden path write
    res_err = await client.dispatch_tool(
        "writeFile",
        {"path": str(forbidden_dir / "bad.txt"), "content": "bad"},
    )
    assert res_err["success"] is False
    assert "outside permitted scopes" in res_err["error"]


@pytest.mark.asyncio
async def test_companion_file_operations(tmp_path: Path) -> None:
    client = CompanionClient(CompanionConfig(allowed_paths=(str(tmp_path),)))
    test_file = tmp_path / "sample.txt"

    # Write file
    res_w = await client.dispatch_tool(
        "writeFile", {"path": str(test_file), "content": "line1\nline2\nline3"}
    )
    assert res_w["success"] is True

    # Read file full
    res_r = await client.dispatch_tool("readFile", {"path": str(test_file)})
    assert res_r["success"] is True
    assert res_r["content"] == "line1\nline2\nline3"

    # Read file lines
    res_rl = await client.dispatch_tool(
        "readFile", {"path": str(test_file), "start_line": 2, "end_line": 2}
    )
    assert res_rl["success"] is True
    assert res_rl["content"] == "line2\n"

    # Edit file
    res_e = await client.dispatch_tool(
        "editFile", {"path": str(test_file), "search": "line2", "replace": "LINE_TWO"}
    )
    assert res_e["success"] is True
    assert "LINE_TWO" in test_file.read_text()

    # List files
    res_l = await client.dispatch_tool("listFiles", {"directory": str(tmp_path)})
    assert res_l["success"] is True
    assert "sample.txt" in res_l["files"]


def test_companion_rpc_system_info() -> None:
    client = CompanionClient(CompanionConfig(device_id="dev-rpc", label="RPC Test"))
    info = client.dispatch_rpc("systemInfo", {})
    assert info["device_id"] == "dev-rpc"
    assert info["label"] == "RPC Test"
    assert "platform" in info
    assert "hostname" in info


@pytest.mark.asyncio
async def test_companion_auto_pair_with_preauth_code(tmp_path: Path) -> None:
    token_file = tmp_path / "companion_token.json"
    client = CompanionClient(
        CompanionConfig(
            server_url="http://127.0.0.1:8765",
            device_id="dev-auto",
            label="Auto Laptop",
            token_file=token_file,
        )
    )

    # Mock request_pairing returning immediate machineToken
    async def fake_request_pairing(user_code: str | None = None) -> dict[str, object]:
        assert user_code == "PRE-1234"
        return {
            "deviceCode": "d-123",
            "userCode": "PRE-1234",
            "machineToken": "mtk-auto-999",
            "userId": "alice",
            "workspaceId": "ws-auto",
            "status": "completed",
        }

    client.request_pairing = fake_request_pairing  # type: ignore[method-assign]
    token = await client.auto_pair("PRE-1234")
    assert token == "mtk-auto-999"  # noqa: S105
    assert client.config.machine_token == "mtk-auto-999"  # noqa: S105
    assert token_file.exists()
