"""员工机工具（ADR-0248 §3.2 BoxAccessor 消费）测试。"""

from pathlib import Path

import pytest

from lca.infrastructure.computer.box_accessor import BoxAccessor
from lca.infrastructure.tools.box.tool import (
    BoxListFilesTool,
    BoxReadFileTool,
    BoxRunCommandTool,
    BoxWriteFileTool,
    build_box_tools,
)


def _box(tmp_path: Path) -> BoxAccessor:
    root = tmp_path / "home_box"
    root.mkdir()
    return BoxAccessor(root_dir=root)


@pytest.mark.asyncio
async def test_box_read_write_roundtrip(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    write = await BoxWriteFileTool(accessor).execute(
        {"path": "workspace/hello.txt", "content": "hello box computer"}
    )
    assert write.success is True
    read = await BoxReadFileTool(accessor).execute({"path": "workspace/hello.txt"})
    assert read.success is True
    assert read.payload["content"] == "hello box computer"


@pytest.mark.asyncio
async def test_box_read_file_missing_returns_failure(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    obs = await BoxReadFileTool(accessor).execute({"path": "missing.txt"})
    assert obs.success is False
    assert "读取员工机文件失败" in obs.error


@pytest.mark.asyncio
async def test_box_write_path_escape_blocked(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    obs = await BoxWriteFileTool(accessor).execute({"path": "../../etc/escape.txt", "content": "x"})
    assert obs.success is False
    assert "越权" in obs.error


@pytest.mark.asyncio
async def test_box_list_files(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    await BoxWriteFileTool(accessor).execute({"path": "a.txt", "content": "a"})
    await BoxWriteFileTool(accessor).execute({"path": "sub/b.txt", "content": "b"})
    obs = await BoxListFilesTool(accessor).execute({"directory_path": "."})
    assert obs.success is True
    assert obs.payload["entries"] == ["a.txt", "sub"]


@pytest.mark.asyncio
async def test_box_run_command_in_box_root(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    await BoxWriteFileTool(accessor).execute({"path": "name.txt", "content": "boxy"})
    obs = await BoxRunCommandTool(accessor).execute({"command": "cat name.txt"})
    assert obs.success is True
    assert "boxy" in obs.payload["stdout"]


@pytest.mark.asyncio
async def test_box_run_command_validation(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    obs = await BoxRunCommandTool(accessor).execute({"command": ""})
    assert obs.success is False
    assert "command 必填" in obs.error


def test_build_box_tools_shell_only_when_requested(tmp_path: Path) -> None:
    accessor = _box(tmp_path)
    file_tools = build_box_tools(accessor)
    names = [t.name for t in file_tools]
    assert names == ["box_read_file", "box_write_file", "box_list_files"]

    with_shell = build_box_tools(accessor, include_shell=True)
    shell_names = [t.name for t in with_shell]
    assert shell_names == [
        "box_read_file",
        "box_write_file",
        "box_list_files",
        "box_run_command",
    ]
