"""Host sidecar executes ops on a real workspace. No /mnt/data remap."""

from __future__ import annotations

from pathlib import Path

import pytest

from host.exec import handle_exec
from host.paths import resolve_host_path


def test_absolute_mnt_data_is_not_remapped(tmp_path: Path) -> None:
    resolved = resolve_host_path("/mnt/data/notes.txt", tmp_path)
    assert resolved == Path("/mnt/data/notes.txt")
    assert resolved != (tmp_path / "notes.txt").resolve()


@pytest.mark.asyncio
async def test_write_and_shell(tmp_path: Path) -> None:
    written = await handle_exec(
        "write_files",
        {"base_dir": str(tmp_path), "files": {"hello.txt": {"b64": "aGk="}}},
        tmp_path,
    )
    assert written["success"]
    assert (tmp_path / "hello.txt").read_text() == "hi"
    ran = await handle_exec("run_terminal", {"command": "cat hello.txt", "timeout_s": 5}, tmp_path)
    assert ran["success"]
    assert ran["stdout"] == "hi"


@pytest.mark.asyncio
async def test_mnt_data_command_does_not_hit_workspace(tmp_path: Path) -> None:
    await handle_exec(
        "write_files",
        {"base_dir": str(tmp_path), "files": {"n.txt": {"b64": "eQ=="}}},
        tmp_path,
    )
    listed = await handle_exec(
        "run_terminal",
        {"command": "cat /mnt/data/n.txt", "timeout_s": 5},
        tmp_path,
    )
    assert not listed["success"] or "No such file" in (listed.get("stderr") or "")
