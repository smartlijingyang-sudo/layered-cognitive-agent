"""Host sidecar executes Sandbox ops on a real workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from host.exec import handle_exec, resolve_guest_path
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT


def test_mnt_data_maps_to_workspace(tmp_path: Path) -> None:
    assert (
        resolve_guest_path(f"{SANDBOX_MOUNT_ROOT}/notes.txt", tmp_path)
        == (tmp_path / "notes.txt").resolve()
    )


@pytest.mark.asyncio
async def test_write_and_shell(tmp_path: Path) -> None:
    written = await handle_exec(
        "write_files",
        {"base_dir": SANDBOX_MOUNT_ROOT, "files": {"hello.txt": {"b64": "aGk="}}},
        tmp_path,
    )
    assert written["success"]
    assert (tmp_path / "hello.txt").read_text() == "hi"
    ran = await handle_exec("run_terminal", {"command": "cat hello.txt", "timeout_s": 5}, tmp_path)
    assert ran["success"]
    assert ran["stdout"] == "hi"
