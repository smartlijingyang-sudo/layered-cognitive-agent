"""Host sidecar executes Sandbox ops on a real workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from host.exec import handle_exec
from host.paths import resolve_guest_path, rewrite_guest_refs
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


def test_rewrite_guest_refs_in_command(tmp_path: Path) -> None:
    cmd = rewrite_guest_refs("officecli view /mnt/data/report.docx text --json", tmp_path)
    assert "/mnt/data" not in cmd
    assert str(tmp_path / "report.docx") in cmd or f"{tmp_path.as_posix()}/report.docx" in cmd


@pytest.mark.asyncio
async def test_run_command_guest_path_hits_workspace(tmp_path: Path) -> None:
    await handle_exec(
        "write_files",
        {"base_dir": SANDBOX_MOUNT_ROOT, "files": {"n.txt": {"b64": "eQ=="}}},
        tmp_path,
    )
    listed = await handle_exec(
        "run_terminal",
        {"command": "cat /mnt/data/n.txt", "timeout_s": 5},
        tmp_path,
    )
    assert listed["success"], listed
    assert listed["stdout"] == "y"
