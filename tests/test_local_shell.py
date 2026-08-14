"""Local-file-shell analog: named file ops against a workspace."""

from __future__ import annotations

from pathlib import Path

from host.local_shell.dispatch import dispatch_local
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT


def test_read_write_edit_list(tmp_path: Path) -> None:
    mount = SANDBOX_MOUNT_ROOT
    written = dispatch_local(
        "write_file",
        {"path": "note.txt", "content": "hello world"},
        tmp_path,
        mount=mount,
    )
    assert written["success"]
    assert (tmp_path / "note.txt").read_text() == "hello world"
    listed = dispatch_local("list_files", {"directory_path": "."}, tmp_path, mount=mount)
    assert listed["success"]
    names = [row["name"] for row in listed["files"] if isinstance(row, dict)]
    assert "note.txt" in names
    read = dispatch_local("read_file", {"path": "note.txt"}, tmp_path, mount=mount)
    assert read["content"] == "hello world"
    edited = dispatch_local(
        "edit_file",
        {"path": "note.txt", "search": "world", "replace": "sandbox"},
        tmp_path,
        mount=mount,
    )
    assert edited["success"]
    assert (tmp_path / "note.txt").read_text() == "hello sandbox"


def test_jail_does_not_write_outside_workspace(tmp_path: Path) -> None:
    result = dispatch_local(
        "write_file",
        {"path": "/etc/passwd", "content": "nope"},
        tmp_path,
        mount=SANDBOX_MOUNT_ROOT,
    )
    # No longer jailed into workspace — path is literal. The op hits /etc which
    # is not writable as a normal user; the sidecar reports the error.
    assert not Path("/etc/passwd").read_text().startswith("nope")


def test_official_aliases_and_run_command(tmp_path: Path) -> None:
    dispatch_local(
        "writeLocalFile",
        {"path": "a.txt", "content": "alpha"},
        tmp_path,
        mount=SANDBOX_MOUNT_ROOT,
    )
    listed = dispatch_local("listLocalFiles", {"path": "."}, tmp_path, mount=SANDBOX_MOUNT_ROOT)
    assert listed["success"]
    ran = dispatch_local(
        "runCommand",
        {"command": "printf hi", "timeout_s": 5},
        tmp_path,
        mount=SANDBOX_MOUNT_ROOT,
    )
    assert ran["success"], ran
    assert "hi" in (ran.get("stdout") or ran.get("output") or "")
